"""Cada transição listada em docs/maquina-de-estados.md e rejeição das demais."""

from datetime import timedelta
from itertools import product

import pytest

from apps.companies import services as company_services
from apps.companies.models import Company
from apps.companies.state_machine import COMPANY_VERIFICATION_MACHINE
from apps.core.exceptions import DomainError, InvalidTransition
from apps.core.models import StateTransition, VerificationReview
from apps.core.tests.factories import (
    LAT,
    LNG,
    NOW,
    make_admin,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.payments.state_machine import CUSTODY_MACHINE
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Application, Assignment, Vacancy
from apps.vacancies.state_machine import (
    APPLICATION_MACHINE,
    ASSIGNMENT_MACHINE,
    VACANCY_MACHINE,
)
from apps.workers import services as worker_services
from apps.workers.models import Worker, WorkerDocument
from apps.workers.state_machine import WORKER_VERIFICATION_MACHINE

pytestmark = pytest.mark.django_db

LISTED = {
    "vacancy": (
        VACANCY_MACHINE,
        {
            ("AGUARDANDO_PAGAMENTO", "PUBLICADA"),
            ("AGUARDANDO_PAGAMENTO", "CANCELADA"),
            ("PUBLICADA", "CANCELADA"),
            ("PUBLICADA", "CANDIDATURAS_ENCERRADAS"),
            ("CANDIDATURAS_ENCERRADAS", "EM_ANDAMENTO"),
            ("CANDIDATURAS_ENCERRADAS", "CANCELADA"),
            ("EM_ANDAMENTO", "FINALIZADA"),
        },
    ),
    "application": (
        APPLICATION_MACHINE,
        {("PENDENTE", s) for s in ("APROVADA", "RECUSADA", "DESISTENCIA", "EXPIRADA")},
    ),
    "assignment": (
        ASSIGNMENT_MACHINE,
        {
            ("CONFIRMADA", "EM_EXECUCAO"),
            ("CONFIRMADA", "FALTA"),
            ("CONFIRMADA", "CANCELADA_PRESTADOR"),
            ("CONFIRMADA", "CANCELADA_EMPRESA"),
            ("EM_EXECUCAO", "AGUARDANDO_VALIDACAO"),
            ("AGUARDANDO_VALIDACAO", "APROVADA"),
            ("AGUARDANDO_VALIDACAO", "CONTESTADA"),
            ("CONTESTADA", "APROVADA"),
            ("CONTESTADA", "ESTORNADA"),
            ("APROVADA", "PAGA"),
        },
    ),
    "custody": (
        CUSTODY_MACHINE,
        {
            ("PENDENTE", "RETIDA"),
            ("PENDENTE", "CANCELADA"),
            ("RETIDA", "RETIDA"),
            ("RETIDA", "ENCERRADA"),
        },
    ),
    "company": (
        COMPANY_VERIFICATION_MACHINE,
        {("PENDENTE", "APROVADA"), ("PENDENTE", "REJEITADA"), ("REJEITADA", "PENDENTE")},
    ),
    "worker": (
        WORKER_VERIFICATION_MACHINE,
        {
            ("PENDENTE_DOCUMENTOS", "EM_ANALISE"),
            ("EM_ANALISE", "APROVADO"),
            ("EM_ANALISE", "REJEITADO"),
            ("REJEITADO", "EM_ANALISE"),
        },
    ),
}


@pytest.mark.parametrize("name", LISTED)
def test_tables_contain_exactly_the_listed_transitions(name):
    machine, listed = LISTED[name]
    allowed = {(o, d) for o, dests in machine.transitions.items() for d in dests}
    assert allowed == listed
    states = set(machine.transitions) | {d for _, d in allowed}
    for origin, dest in product(states, states):
        if (origin, dest) in listed:
            machine.validate(origin, dest)
        else:
            with pytest.raises(InvalidTransition):
                machine.validate(origin, dest)


# --- Vaga ---------------------------------------------------------------


def test_vacancy_requires_approved_company_and_lead_time():
    from apps.core.tests.factories import vacancy_fields
    from apps.vacancies import services as vacancies

    with pytest.raises(DomainError):
        vacancies.create_vacancy(
            company=make_company(approved=False),
            now=NOW,
            **vacancy_fields(NOW + timedelta(days=2)),
        )
    with pytest.raises(DomainError):
        vacancies.create_vacancy(
            company=make_company(), now=NOW, **vacancy_fields(NOW + timedelta(hours=11))
        )
    assert Vacancy.objects.count() == 0


def test_vacancy_creation_is_audited():
    vacancy = make_published_vacancy()
    states = list(
        StateTransition.objects.filter(entity_type="Vacancy", entity_id=vacancy.pk)
        .order_by("id")
        .values_list("from_state", "to_state")
    )
    assert states == [("", "AGUARDANDO_PAGAMENTO"), ("AGUARDANDO_PAGAMENTO", "PUBLICADA")]


# --- Candidatura --------------------------------------------------------


def test_application_rules():
    vacancy = make_published_vacancy()
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(vacancy, make_worker(approved=False), now=NOW)
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(
            vacancy, make_worker(suspended_until=NOW + timedelta(days=1)), now=NOW
        )
    worker = make_worker()
    applications.apply_to_vacancy(vacancy, worker, now=NOW)
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(vacancy, worker, now=NOW)


def test_application_blocked_after_applications_closed_and_on_overlap():
    first = make_assignment(starts_in_hours=48)
    worker = first.worker
    overlapping = make_published_vacancy(starts_in_hours=49)
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(overlapping, worker, now=NOW)

    from apps.core.deadlines import process_deadlines

    closed = make_published_vacancy(starts_in_hours=100)
    process_deadlines(closed.starts_at - timedelta(hours=2))
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(closed, make_worker(), now=NOW)


def test_approve_creates_assignment_and_notifies_and_respects_positions():
    vacancy = make_published_vacancy()
    a1 = applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)
    a2 = applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)

    assignment = applications.approve_application(a1, now=NOW)

    assert assignment.status == Assignment.Status.CONFIRMED
    a1.refresh_from_db()
    assert a1.status == Application.Status.APPROVED and a1.decided_at == NOW
    assert assignment.worker.user.notifications.filter(kind="CANDIDATURA_APROVADA").exists()
    with pytest.raises(DomainError):
        applications.approve_application(a2, now=NOW)
    a2.refresh_from_db()
    assert a2.status == Application.Status.PENDING


def test_reject_and_withdraw():
    vacancy = make_published_vacancy(positions=2)
    rejected = applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)
    withdrawn = applications.apply_to_vacancy(vacancy, make_worker(), now=NOW)
    applications.reject_application(rejected, now=NOW)
    applications.withdraw_application(withdrawn, now=NOW)
    assert rejected.status == Application.Status.REJECTED
    assert withdrawn.status == Application.Status.WITHDRAWN
    with pytest.raises(InvalidTransition):
        applications.approve_application(rejected, now=NOW)


# --- Alocação -----------------------------------------------------------


def test_check_in_geofence_and_window():
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    with pytest.raises(DomainError, match="m do local"):
        assignments.check_in(assignment, lat=LAT + 0.01, lng=LNG, now=start)
    with pytest.raises(DomainError):
        assignments.check_in(assignment, lat=LAT, lng=LNG, now=start - timedelta(minutes=31))
    with pytest.raises(DomainError):
        assignments.check_in(assignment, lat=LAT, lng=LNG, now=start + timedelta(minutes=31))
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED

    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start - timedelta(minutes=30))
    assert assignment.status == Assignment.Status.IN_PROGRESS
    assert assignment.check_in_distance_m == 0
    assert assignment.check_in_lat is not None


def test_check_out_and_manual_approval():
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    admin = make_admin()
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION
    assert assignment.check_out_at == start + timedelta(hours=4)
    assert not assignment.check_out_auto
    assignments.approve_hours(assignment, actor=admin, now=start + timedelta(hours=5))
    assert assignment.status == Assignment.Status.APPROVED
    assert assignment.validated_by == admin


def test_contest_and_admin_resolution_in_favor_of_worker():
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    admin = make_admin()
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    with pytest.raises(DomainError):
        assignments.contest(assignment, reason=" ", now=start)
    assignments.contest(assignment, reason="Saiu mais cedo", now=start + timedelta(hours=5))
    assert assignment.status == Assignment.Status.CONTESTED
    assert admin.notifications.filter(kind="CONTESTACAO").exists()
    with pytest.raises(DomainError):
        assignments.resolve_contest(
            assignment, in_favor_of_worker=True, reason="", actor=admin, now=NOW
        )
    assignments.resolve_contest(
        assignment, in_favor_of_worker=True, reason="Horas conferidas", actor=admin, now=NOW
    )
    assert assignment.status == Assignment.Status.APPROVED


def test_contest_resolved_in_favor_of_company_refunds_position():
    assignment = make_assignment()
    start = assignment.vacancy.starts_at
    admin = make_admin()
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.contest(assignment, reason="Não trabalhou", now=start + timedelta(hours=5))

    assignments.resolve_contest(
        assignment, in_favor_of_worker=False, reason="Procede", actor=admin, now=NOW
    )

    assert assignment.status == Assignment.Status.REFUNDED
    entry = assignment.ledger_entries.get()
    assert (entry.kind, entry.amount_cents) == ("ESTORNO_CONTRATANTE", 10000)


def test_settle_from_wrong_state_is_rejected():
    assignment = make_assignment()
    with pytest.raises(InvalidTransition):
        assignments.settle(assignment, now=NOW)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    assert assignment.ledger_entries.count() == 0


# --- Verificação --------------------------------------------------------


def test_company_verification_flow():
    company = make_company(approved=False)
    admin = make_admin()
    with pytest.raises(DomainError):
        company_services.review_company(company, reviewer=admin, approve=False, reason="")

    company_services.review_company(company, reviewer=admin, approve=False, reason="CNPJ inativo")
    assert company.verification_status == Company.VerificationStatus.REJECTED
    company_services.resubmit_company(company)
    assert company.verification_status == Company.VerificationStatus.PENDING
    company_services.review_company(company, reviewer=admin, approve=True)
    assert company.verification_status == Company.VerificationStatus.APPROVED
    assert VerificationReview.objects.filter(subject_id=company.pk).count() == 2
    with pytest.raises(InvalidTransition):
        company_services.resubmit_company(company)


def test_worker_verification_flow():
    worker = make_worker(approved=False)
    admin = make_admin()
    with pytest.raises(DomainError):
        worker_services.submit_documents(worker)
    for kind in WorkerDocument.Kind:
        WorkerDocument.objects.create(worker=worker, kind=kind, file=f"x/{kind}.jpg")

    worker_services.submit_documents(worker)
    assert worker.verification_status == Worker.VerificationStatus.IN_REVIEW
    with pytest.raises(DomainError):
        worker_services.review_worker(worker, reviewer=admin, approve=False)
    worker_services.review_worker(worker, reviewer=admin, approve=False, reason="Foto ilegível")
    worker_services.submit_documents(worker)
    worker_services.review_worker(worker, reviewer=admin, approve=True)
    assert worker.verification_status == Worker.VerificationStatus.APPROVED
    assert worker.user.notifications.filter(kind="VERIFICACAO").count() == 2
    with pytest.raises(InvalidTransition):
        worker_services.submit_documents(worker)


def test_worker_document_has_no_public_url():
    worker = make_worker()
    document = WorkerDocument.objects.create(worker=worker, kind="SELFIE", file="x/selfie.jpg")
    with pytest.raises(ValueError):
        document.file.url  # noqa: B018
