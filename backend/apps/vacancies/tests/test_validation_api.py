"""US56 (empresa confere e aprova as horas) e US59 (aprovação automática por silêncio)."""

from datetime import timedelta

import pytest
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters, StateTransition
from apps.core.tests.factories import LAT, LNG, make_assignment, make_company, make_worker
from apps.payments.models import Custody
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Assignment, Vacancy

pytestmark = pytest.mark.django_db

PENDING_URL = "/api/company/assignments/pending/"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def company_client(company):
    return client_for(company.members.first().user)


def awaiting_assignment(**kw):
    """Alocação AGUARDANDO_VALIDACAO com check-in/check-out registrados há pouco."""
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48, **kw)
    vacancy = assignment.vacancy
    vacancy.starts_at = now - timedelta(hours=4)
    vacancy.ends_at = now
    vacancy.save()
    assignments.check_in(assignment, lat=LAT + 0.0007, lng=LNG, now=vacancy.starts_at)
    assignments.check_out(assignment, now=now)
    assignment.refresh_from_db()
    return assignment


def approve(client, assignment):
    return client.post(f"/api/assignments/{assignment.pk}/approve/")


def entries(custody):
    return dict(custody.entries.values_list("kind", "amount_cents"))


def test_pending_list_shows_planned_vs_recorded_and_remaining_time():
    assignment = awaiting_assignment()
    company = assignment.vacancy.company

    response = company_client(company).get(PENDING_URL)

    assert response.status_code == 200
    (item,) = response.json()["results"]
    assert item["id"] == assignment.pk
    assert item["worker_first_name"] == assignment.worker.full_name.split()[0]
    assert item["starts_at"] and item["ends_at"]
    assert item["check_in_at"] and item["check_out_at"]
    assert 0 < item["check_in_distance_m"] <= 150
    assert item["check_out_auto"] is False
    window = PlatformParameters.get().contest_window_minutes * 60
    assert window - 60 <= item["auto_approve_in_seconds"] <= window


def test_pending_list_flags_automatic_check_out():
    assignment = awaiting_assignment()
    assignment.check_out_auto = True
    assignment.save()
    (item,) = company_client(assignment.vacancy.company).get(PENDING_URL).json()["results"]
    assert item["check_out_auto"] is True


def test_pending_list_remaining_time_uses_platform_parameters():
    assignment = awaiting_assignment()
    PlatformParameters.objects.update(contest_window_minutes=60)
    (item,) = company_client(assignment.vacancy.company).get(PENDING_URL).json()["results"]
    assert 3500 <= item["auto_approve_in_seconds"] <= 3600


def test_pending_list_only_has_own_awaiting_assignments_and_filters_by_vacancy():
    mine = awaiting_assignment()
    other = awaiting_assignment()
    confirmed = make_assignment(vacancy=None, now=timezone.now())
    client = company_client(mine.vacancy.company)

    ids = [i["id"] for i in client.get(PENDING_URL).json()["results"]]
    assert ids == [mine.pk]
    assert other.pk not in ids and confirmed.pk not in ids
    assert client.get(f"{PENDING_URL}?vacancy={mine.vacancy_id}").json()["results"]
    assert client.get(f"{PENDING_URL}?vacancy={other.vacancy_id}").json()["results"] == []
    assert client.get(f"{PENDING_URL}?vacancy=abc").status_code == 400


def test_pending_list_requires_company():
    assignment = awaiting_assignment()
    assert APIClient().get(PENDING_URL).status_code == 403
    assert client_for(assignment.worker.user).get(PENDING_URL).status_code == 403


def test_approve_releases_payment_with_97_3_split_and_notifies_worker():
    assignment = awaiting_assignment()
    response = approve(company_client(assignment.vacancy.company), assignment)

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "PAGA"
    assert response.json()["payment_pending"] is False
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert assignment.validated_by is not None and assignment.validated_at is not None
    assert entries(assignment.vacancy.custody) == {
        "RETENCAO": 10000,
        "REPASSE_PRESTADOR": 9700,
        "TAXA_PLATAFORMA": 300,
    }
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="HORAS_APROVADAS"
    ).exists()
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="PAGAMENTO_LIBERADO"
    ).exists()
    states = StateTransition.objects.filter(
        entity_type="Assignment", entity_id=assignment.pk
    ).values_list("to_state", flat=True)
    assert "APROVADA" in states and "PAGA" in states


def test_approved_assignment_leaves_the_pending_list():
    assignment = awaiting_assignment()
    client = company_client(assignment.vacancy.company)
    assert approve(client, assignment).status_code == 200
    assert client.get(PENDING_URL).json()["results"] == []


def test_approve_twice_is_rejected_without_duplicating_entries():
    assignment = awaiting_assignment()
    client = company_client(assignment.vacancy.company)
    assert approve(client, assignment).status_code == 200
    assert approve(client, assignment).status_code == 409
    assert assignment.vacancy.custody.entries.count() == 3


def test_approve_requires_awaiting_validation():
    assignment = make_assignment()
    response = approve(company_client(assignment.vacancy.company), assignment)
    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_other_company_cannot_approve():
    assignment = awaiting_assignment()
    response = approve(company_client(make_company()), assignment)
    assert response.status_code == 404
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION


def test_worker_and_anonymous_cannot_approve():
    assignment = awaiting_assignment()
    assert approve(client_for(assignment.worker.user), assignment).status_code == 403
    assert approve(APIClient(), assignment).status_code == 403
    assert approve(client_for(make_worker().user), assignment).status_code == 403
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION


def test_psp_failure_keeps_approved_and_next_processing_retries_without_duplicates(fake_gateway):
    assignment = awaiting_assignment()
    client = company_client(assignment.vacancy.company)
    fake_gateway.fail = True

    response = approve(client, assignment)

    assert response.status_code == 200
    assert response.json()["status"] == "APROVADA"
    assert response.json()["payment_pending"] is True
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.APPROVED
    assert assignment.vacancy.custody.entries.count() == 1

    assert "liquidacoes" not in process_deadlines()
    fake_gateway.fail = False
    assert process_deadlines()["liquidacoes"] == 1
    assert "liquidacoes" not in process_deadlines()

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert assignment.vacancy.custody.entries.count() == 3


def test_silence_after_contest_window_auto_approves_pays_and_notifies_both():
    assignment = awaiting_assignment()
    window = PlatformParameters.get().contest_window_minutes
    check_out = assignment.check_out_at

    assert "aprovacoes_automaticas" not in process_deadlines(
        check_out + timedelta(minutes=window - 1)
    )
    done = process_deadlines(check_out + timedelta(minutes=window + 1))

    assert done["aprovacoes_automaticas"] == 1
    assert done["liquidacoes"] == 1
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    assert assignment.validated_by is None and assignment.validated_at is not None
    assert entries(assignment.vacancy.custody)["REPASSE_PRESTADOR"] == 9700
    transition = StateTransition.objects.get(
        entity_type="Assignment", entity_id=assignment.pk, to_state="APROVADA"
    )
    assert transition.reason == "aprovação por decurso de prazo"
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="HORAS_APROVADAS"
    ).exists()
    company_user = assignment.vacancy.company.members.first().user
    assert Notification.objects.filter(user=company_user, kind="HORAS_APROVADAS").exists()
    assert Notification.objects.filter(
        user=assignment.worker.user, kind="PAGAMENTO_LIBERADO"
    ).exists()


def test_auto_approval_window_comes_from_platform_parameters():
    assignment = awaiting_assignment()
    PlatformParameters.objects.update(contest_window_minutes=10)
    done = process_deadlines(assignment.check_out_at + timedelta(minutes=11))
    assert done["aprovacoes_automaticas"] == 1


def test_vacancy_is_finalized_refunding_unused_positions_and_closing_custody():
    assignment = awaiting_assignment(positions=3)
    vacancy = assignment.vacancy
    assert approve(company_client(vacancy.company), assignment).status_code == 200

    process_deadlines()

    vacancy.refresh_from_db()
    custody = vacancy.custody
    custody.refresh_from_db()
    assert vacancy.status == Vacancy.Status.FINISHED
    assert custody.status == Custody.Status.CLOSED

    def total(kind):
        return custody.entries.filter(kind=kind).aggregate(t=Sum("amount_cents"))["t"] or 0

    assert total("RETENCAO") == 30000
    assert total("REPASSE_PRESTADOR") == 9700
    assert total("TAXA_PLATAFORMA") == 300
    assert total("ESTORNO_CONTRATANTE") == 20000
    assert (
        total("REPASSE_PRESTADOR") + total("TAXA_PLATAFORMA") + total("ESTORNO_CONTRATANTE")
        == total("RETENCAO")
    )

    process_deadlines()  # repetição: nada novo
    assert custody.entries.count() == 4
