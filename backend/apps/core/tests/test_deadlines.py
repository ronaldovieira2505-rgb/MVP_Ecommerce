from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from apps.core.deadlines import process_deadlines
from apps.core.models import StateTransition
from apps.core.tests.factories import (
    LAT,
    LNG,
    NOW,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
    vacancy_fields,
)
from apps.payments.models import Custody, LedgerEntry
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies import services as vacancies
from apps.vacancies.models import Application, Assignment, Vacancy

pytestmark = pytest.mark.django_db


def snapshot():
    return (StateTransition.objects.count(), LedgerEntry.objects.count())


def run_twice(now):
    first = process_deadlines(now)
    before = snapshot()
    second = process_deadlines(now)
    assert second == {}
    assert snapshot() == before
    return first


def test_cancels_unpaid_vacancy_after_payment_deadline():
    vacancy = vacancies.create_vacancy(
        company=make_company(), now=NOW, **vacancy_fields(NOW + timedelta(hours=72))
    )
    assert process_deadlines(NOW + timedelta(hours=23)) == {}

    done = run_twice(NOW + timedelta(hours=25))

    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.CANCELLED
    assert vacancy.custody.status == Custody.Status.CANCELLED
    assert done == {"vagas_canceladas_por_falta_de_pagamento": 1}


def test_cancels_unpaid_vacancy_when_lead_time_is_no_longer_possible():
    vacancy = vacancies.create_vacancy(
        company=make_company(), now=NOW, **vacancy_fields(NOW + timedelta(hours=13))
    )
    run_twice(NOW + timedelta(hours=2))
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.CANCELLED


def test_closes_applications_two_hours_before_start():
    vacancy = make_published_vacancy()
    assert process_deadlines(vacancy.starts_at - timedelta(hours=3)) == {}
    done = run_twice(vacancy.starts_at - timedelta(hours=2))
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.APPLICATIONS_CLOSED
    assert done == {"candidaturas_encerradas": 1}


def test_starts_vacancy_with_assignment():
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    done = run_twice(start)
    assignment.vacancy.refresh_from_db()
    assert assignment.vacancy.status == Vacancy.Status.IN_PROGRESS
    assert done["vagas_iniciadas"] == 1


def test_cancels_vacancy_without_assignment_refunds_and_expires_applications():
    vacancy = make_published_vacancy()
    pending = applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)

    done = run_twice(vacancy.starts_at)

    vacancy.refresh_from_db()
    pending.refresh_from_db()
    assert vacancy.status == Vacancy.Status.CANCELLED
    assert pending.status == Application.Status.EXPIRED
    assert vacancy.custody.status == Custody.Status.CLOSED
    assert vacancy.custody.entries.filter(kind="ESTORNO_CONTRATANTE", amount_cents=10000).exists()
    assert done["vagas_canceladas_sem_alocacao"] == 1
    assert vacancy.company.members.first().user.notifications.filter(kind="VAGA_CANCELADA").exists()


def test_no_show_reopens_vacancy_and_suspends_after_two_in_30_days():
    worker = make_worker()
    first = make_assignment(worker=worker, starts_in_hours=48)
    second = make_assignment(worker=worker, starts_in_hours=200)

    done = run_twice(first.vacancy.starts_at + timedelta(minutes=31))
    first.refresh_from_db()
    worker.refresh_from_db()
    assert first.status == Assignment.Status.NO_SHOW
    assert done["faltas"] == 1
    assert worker.suspended_until is None
    first.vacancy.refresh_from_db()
    assert first.vacancy.reopened

    now = second.vacancy.starts_at + timedelta(minutes=31)
    done = run_twice(now)
    worker.refresh_from_db()
    assert done["suspensoes_automaticas"] == 1
    assert worker.suspended_until == now + timedelta(days=15)
    assert worker.user.notifications.filter(kind="SUSPENSAO").exists()


def test_no_show_not_applied_before_tolerance():
    assignment = make_assignment()
    assert process_deadlines(assignment.vacancy.starts_at + timedelta(minutes=29)) == {
        "candidaturas_encerradas": 1,
        "vagas_iniciadas": 1,
    }
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_full_lifecycle_through_deadlines_pays_and_finalizes():
    assignment = make_assignment()
    vacancy = assignment.vacancy
    start, end = vacancy.starts_at, vacancy.ends_at

    process_deadlines(start - timedelta(hours=2))
    process_deadlines(start)
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)

    # Sem check-out: o sistema faz check-out automático, aprova por decurso e liquida.
    done = run_twice(end + timedelta(hours=2, minutes=1))
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION
    assert assignment.check_out_auto
    assert assignment.check_out_at == end
    assert done == {"checkouts_automaticos": 1}

    done = run_twice(end + timedelta(hours=24))
    assignment.refresh_from_db()
    vacancy.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert assignment.validated_by is None and assignment.validated_at
    assert vacancy.status == Vacancy.Status.FINISHED
    assert vacancy.custody.status == Custody.Status.CLOSED
    assert done == {
        "aprovacoes_automaticas": 1,
        "liquidacoes": 1,
        "vagas_finalizadas": 1,
    }
    entries = dict(vacancy.custody.entries.values_list("kind", "amount_cents"))
    assert entries == {"RETENCAO": 10000, "REPASSE_PRESTADOR": 9700, "TAXA_PLATAFORMA": 300}


def test_catching_up_after_downtime_applies_everything_once():
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    process_deadlines(start)

    run_twice(start + timedelta(days=10))

    assignment.refresh_from_db()
    assignment.vacancy.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert assignment.vacancy.status == Vacancy.Status.FINISHED
    assert assignment.vacancy.custody.entries.filter(kind="REPASSE_PRESTADOR").count() == 1


def test_psp_failure_is_retried_on_next_run(fake_gateway):
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    process_deadlines(start)
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=4))
    fake_gateway.fail = True
    later = start + timedelta(hours=5)

    assert process_deadlines(later) == {}
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.APPROVED

    fake_gateway.fail = False
    done = process_deadlines(later)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert done["liquidacoes"] == 1


def test_reopened_vacancy_is_not_finalized_before_it_ends():
    assignment = make_assignment()
    vacancy = assignment.vacancy
    process_deadlines(vacancy.starts_at)
    process_deadlines(vacancy.starts_at + timedelta(minutes=31))
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.IN_PROGRESS and vacancy.reopened

    process_deadlines(vacancy.ends_at - timedelta(minutes=1))
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.IN_PROGRESS

    process_deadlines(vacancy.ends_at)
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.FINISHED
    assert vacancy.custody.entries.filter(kind="ESTORNO_CONTRATANTE", amount_cents=10000).exists()


def test_deadlines_read_platform_parameters():
    from apps.core.models import PlatformParameters

    PlatformParameters.objects.update(payment_deadline_hours=1)
    vacancy = vacancies.create_vacancy(
        company=make_company(), now=NOW, **vacancy_fields(NOW + timedelta(hours=72))
    )
    process_deadlines(NOW + timedelta(hours=2))
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.CANCELLED


def test_command_runs_once_and_is_idempotent():
    make_published_vacancy()
    out = StringIO()
    call_command("processar_prazos", stdout=out)
    call_command("processar_prazos", stdout=out)
    assert "Nenhum prazo a processar." in out.getvalue()


def test_command_loop_option(monkeypatch):
    calls = []

    def fake_sleep(seconds):
        calls.append(seconds)
        if len(calls) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("apps.core.management.commands.processar_prazos.time.sleep", fake_sleep)
    out = StringIO()
    call_command("processar_prazos", "--loop", "15", stdout=out)
    assert calls == [15, 15]
    assert "Encerrado." in out.getvalue()
