import pytest
from django.db.models import Sum

from apps.core.exceptions import DomainError
from apps.core.tests.factories import NOW, make_assignment, make_paid_ready_assignment
from apps.payments import services as payments
from apps.payments.models import Custody, LedgerEntry
from apps.vacancies import assignment_services as assignments
from apps.vacancies import services as vacancies
from apps.vacancies.models import Assignment
from integrations.payments import PaymentGatewayError

pytestmark = pytest.mark.django_db


def kinds(custody):
    return sorted(custody.entries.values_list("kind", "amount_cents"))


def test_payment_retains_custody_and_creates_retention_entry():
    assignment = make_assignment()
    custody = assignment.vacancy.custody
    assert custody.status == Custody.Status.HELD
    assert custody.psp_reference.startswith("fake-hold-")
    assert kinds(custody) == [("RETENCAO", 10000)]


def test_retain_twice_does_not_duplicate_entries():
    custody = make_assignment().vacancy.custody
    payments.retain(custody, now=NOW)
    payments.retain(custody, now=NOW)
    assert custody.entries.filter(kind="RETENCAO").count() == 1


def test_settlement_of_100_reais_pays_9700_and_fee_300():
    assignment = make_paid_ready_assignment()

    assignments.settle(assignment, now=NOW)

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID
    custody = assignment.vacancy.custody
    assert dict(custody.entries.values_list("kind", "amount_cents")) == {
        "RETENCAO": 10000,
        "REPASSE_PRESTADOR": 9700,
        "TAXA_PLATAFORMA": 300,
    }


def test_settle_twice_at_payment_layer_does_not_duplicate():
    assignment = make_paid_ready_assignment()
    custody = assignment.vacancy.custody
    payments.settle_assignment(custody, assignment, now=NOW)
    payments.settle_assignment(custody, assignment, now=NOW)
    assert custody.entries.count() == 3


def test_fee_uses_platform_parameters_not_hardcoded():
    from apps.core.models import PlatformParameters

    PlatformParameters.objects.update(worker_fee_percent=10)
    assignment = make_paid_ready_assignment()
    assignments.settle(assignment, now=NOW)
    entries = dict(assignment.vacancy.custody.entries.values_list("kind", "amount_cents"))
    assert entries["REPASSE_PRESTADOR"] == 9000
    assert entries["TAXA_PLATAFORMA"] == 1000


def test_psp_failure_keeps_assignment_approved_and_writes_nothing(fake_gateway):
    assignment = make_paid_ready_assignment()
    fake_gateway.fail = True

    with pytest.raises(PaymentGatewayError):
        assignments.settle(assignment, now=NOW)

    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.APPROVED
    assert assignment.vacancy.custody.entries.count() == 1

    fake_gateway.fail = False
    assignments.settle(assignment, now=NOW)
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.PAID


def test_refund_assignment_is_idempotent():
    assignment = make_assignment()
    custody = assignment.vacancy.custody
    payments.refund_assignment(custody, assignment, now=NOW)
    payments.refund_assignment(custody, assignment, now=NOW)
    assert custody.entries.filter(kind="ESTORNO_CONTRATANTE").count() == 1


def test_close_refunds_unused_positions_and_keeps_invariant():
    company_vacancy = make_assignment(positions=3).vacancy
    assignment = company_vacancy.assignments.get()
    assignments.check_in(assignment, lat=-23.55052, lng=-46.633308, now=company_vacancy.starts_at)
    assignments.check_out(assignment, now=company_vacancy.starts_at)
    assignments.approve_hours(assignment, now=company_vacancy.starts_at)
    assignments.settle(assignment, now=NOW)

    custody = company_vacancy.custody
    payments.close(custody, now=NOW)
    payments.close(custody, now=NOW)  # repetição

    custody.refresh_from_db()
    assert custody.status == Custody.Status.CLOSED

    def total(kind):
        return custody.entries.filter(kind=kind).aggregate(t=Sum("amount_cents"))["t"] or 0

    distributed = (
        total("REPASSE_PRESTADOR") + total("TAXA_PLATAFORMA") + total("ESTORNO_CONTRATANTE")
    )
    assert total("RETENCAO") == 30000
    assert distributed == 30000
    assert total("ESTORNO_CONTRATANTE") == 20000


def test_removing_published_vacancy_refunds_everything():
    from apps.core.tests.factories import make_published_vacancy

    vacancy = make_published_vacancy()
    vacancies.remove_vacancy(vacancy, now=NOW)
    vacancy.custody.refresh_from_db()
    assert vacancy.custody.status == Custody.Status.CLOSED
    assert kinds(vacancy.custody) == [("ESTORNO_CONTRATANTE", 10000), ("RETENCAO", 10000)]


def test_cannot_remove_vacancy_with_approved_application():
    assignment = make_assignment()
    with pytest.raises(DomainError):
        vacancies.remove_vacancy(assignment.vacancy, now=NOW)


def test_unpaid_vacancy_cancel_cancels_custody_without_charge():
    from datetime import timedelta

    from apps.core.tests.factories import make_company, vacancy_fields

    vacancy = vacancies.create_vacancy(
        company=make_company(), now=NOW, **vacancy_fields(NOW + timedelta(hours=48))
    )
    assert vacancy.custody.status == Custody.Status.PENDING
    vacancies.cancel_unpaid_vacancy(vacancy, now=NOW)
    vacancy.custody.refresh_from_db()
    assert vacancy.custody.status == Custody.Status.CANCELLED
    assert LedgerEntry.objects.count() == 0
