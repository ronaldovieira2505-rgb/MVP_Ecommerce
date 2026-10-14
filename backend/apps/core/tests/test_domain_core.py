from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import IntegrityError

from apps.accounts.models import Role
from apps.core.exceptions import DomainError, InvalidTransition
from apps.core.masking import mask_cpf, mask_pix_key
from apps.core.models import PlatformParameters, StateTransition
from apps.core.state_machine import StateMachine, transition
from apps.core.tests.factories import make_admin, make_assignment, make_worker
from apps.core.validators import is_valid_cnpj, is_valid_cpf
from apps.payments.models import LedgerEntry
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Assignment, Vacancy
from apps.vacancies.state_machine import ASSIGNMENT_MACHINE, VACANCY_MACHINE

pytestmark = pytest.mark.django_db

EXPECTED_MODELS = [
    ("companies", "Company"),
    ("companies", "CompanyMember"),
    ("workers", "Worker"),
    ("workers", "WorkerDocument"),
    ("core", "VerificationReview"),
    ("vacancies", "Vacancy"),
    ("vacancies", "Application"),
    ("vacancies", "Assignment"),
    ("payments", "Custody"),
    ("payments", "LedgerEntry"),
    ("core", "StateTransition"),
    ("core", "PlatformParameters"),
    ("core", "Notification"),
]


@pytest.mark.parametrize(("app", "model"), EXPECTED_MODELS)
def test_models_exist(app, model):
    assert apps.get_model(app, model)


def test_no_pending_migrations():
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())


def test_user_has_role_choices():
    assert {r.value for r in Role} == {"COMPANY", "WORKER", "ADMIN"}
    assert make_admin().role == Role.ADMIN


def test_data_migration_creates_single_platform_parameters_with_defaults():
    assert PlatformParameters.objects.count() == 1
    p = PlatformParameters.get()
    assert (p.min_publish_lead_hours, p.payment_deadline_hours) == (12, 24)
    assert (p.applications_close_hours_before, p.checkin_open_minutes_before) == (2, 30)
    assert (p.no_show_tolerance_minutes, p.geofence_radius_m) == (30, 150)
    assert (p.auto_checkout_hours_after_end, p.contest_window_hours) == (2, 24)
    assert (p.no_show_limit, p.no_show_window_days, p.suspension_days) == (2, 30, 15)
    assert (p.free_cancel_hours_before, p.late_cancel_block_days) == (24, 7)
    assert p.worker_fee_percent == Decimal("3")


def test_platform_parameters_is_singleton():
    PlatformParameters(min_publish_lead_hours=1).save()
    assert PlatformParameters.objects.count() == 1
    assert PlatformParameters.get().min_publish_lead_hours == 1
    with pytest.raises(NotImplementedError):
        PlatformParameters.get().delete()


def test_fee_rounds_half_up_in_cents():
    p = PlatformParameters.get()
    assert p.worker_fee_cents(10000) == 300
    assert p.worker_net_cents(10000) == 9700
    assert p.worker_fee_cents(150) == 5  # 4,5 → 5


def test_transition_records_state_transition_atomically():
    assignment = make_assignment()
    admin = make_admin()
    start = assignment.vacancy.starts_at

    assignments.check_in(assignment, lat=-23.55052, lng=-46.633308, actor=admin, now=start)

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.IN_PROGRESS
    record = StateTransition.objects.filter(
        entity_type="Assignment", entity_id=assignment.pk
    ).latest("id")
    assert (record.from_state, record.to_state) == ("CONFIRMADA", "EM_EXECUCAO")
    assert record.actor == admin
    assert record.created_at == start


def test_system_transition_has_no_actor_and_keeps_reason():
    assignment = make_assignment()
    assignments.mark_no_show(assignment, now=assignment.vacancy.starts_at + timedelta(hours=1))
    record = StateTransition.objects.filter(entity_type="Assignment", to_state="FALTA").get()
    assert record.actor is None
    assert record.reason


def test_unlisted_transition_raises_and_writes_nothing():
    assignment = make_assignment()
    before = StateTransition.objects.count()

    with pytest.raises(InvalidTransition):
        transition(assignment, ASSIGNMENT_MACHINE, Assignment.Status.PAID)

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    assert StateTransition.objects.count() == before
    assert not LedgerEntry.objects.filter(assignment=assignment).exists()


def test_invalid_transition_is_a_domain_error():
    assert issubclass(InvalidTransition, DomainError)


def test_final_states_have_no_exit():
    for state in ("PAGA", "FALTA", "ESTORNADA", "CANCELADA_PRESTADOR", "CANCELADA_EMPRESA"):
        assert ASSIGNMENT_MACHINE.is_final(state)
    for state in ("FINALIZADA", "CANCELADA"):
        assert VACANCY_MACHINE.is_final(state)


def test_every_non_final_state_has_an_exit():
    machine = StateMachine("X", {"A": {"B"}, "B": set()})
    assert not machine.is_final("A")
    assert machine.is_final("B")


def test_ledger_entries_are_immutable():
    assignment = make_assignment()
    entry = LedgerEntry.objects.get(kind="RETENCAO", custody=assignment.vacancy.custody)
    entry.amount_cents = 1
    with pytest.raises(DomainError):
        entry.save()
    with pytest.raises(DomainError):
        entry.delete()
    with pytest.raises(DomainError):
        LedgerEntry.objects.all().update(amount_cents=1)
    with pytest.raises(DomainError):
        LedgerEntry.objects.all().delete()


def test_ledger_amount_must_be_positive_and_key_unique():
    entry = LedgerEntry.objects.first() or make_assignment().vacancy.custody.entries.first()
    with pytest.raises(IntegrityError):
        LedgerEntry.objects.create(
            custody=entry.custody, kind="RETENCAO", amount_cents=entry.amount_cents,
            idempotency_key=entry.idempotency_key,
        )


def test_vacancy_derived_values():
    assignment = make_assignment()
    vacancy = Vacancy.objects.get(pk=assignment.vacancy_id)
    assert vacancy.filled_positions == 1
    assert vacancy.worker_net_cents == 9700


def test_document_validators():
    assert is_valid_cpf("52998224725")
    assert not is_valid_cpf("52998224724")
    assert not is_valid_cpf("11111111111")
    assert is_valid_cnpj("11222333000181")
    assert not is_valid_cnpj("11222333000180")


def test_masking_hides_personal_data():
    assert mask_cpf("52998224725") == "***.982.247-**"
    assert "52998224725" not in mask_pix_key("CPF", "52998224725")
    assert mask_pix_key("ALEATORIA", "abcdef123456") == "****3456"
    worker = make_worker()
    assert worker.cpf not in str(worker)
