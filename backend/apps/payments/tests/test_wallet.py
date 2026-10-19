"""US60 — carteira do prestador: a receber, liberado e taxas retidas."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.models import PlatformParameters
from apps.core.tests.factories import LAT, LNG, make_assignment, make_company, make_worker
from apps.payments.models import LedgerEntry
from apps.vacancies import assignment_services as assignments

pytestmark = pytest.mark.django_db

URL = "/api/workers/me/wallet/"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def worker_client(worker):
    return client_for(worker.user)


def finished_shift(worker=None, **kw):
    """Alocação AGUARDANDO_VALIDACAO (turno de R$ 100,00 terminado agora)."""
    now = timezone.now()
    assignment = make_assignment(now=now, starts_in_hours=48, worker=worker, **kw)
    vacancy = assignment.vacancy
    vacancy.starts_at = now - timedelta(hours=4)
    vacancy.ends_at = now
    vacancy.save()
    assignments.check_in(assignment, lat=LAT + 0.0007, lng=LNG, now=vacancy.starts_at)
    assignments.check_out(assignment, now=now)
    assignment.refresh_from_db()
    return assignment


def test_receivable_totals_and_items_use_net_value_and_forecast():
    worker = make_worker()
    confirmed = make_assignment(worker=worker)
    awaiting = finished_shift(worker=worker)

    data = worker_client(worker).get(URL).json()

    assert data["totals"] == {"receivable_cents": 19400, "released_cents": 0, "fees_cents": 0}
    assert data["fee_percent"] == 3
    window = timedelta(minutes=PlatformParameters.get().contest_window_minutes)
    by_id = {item["assignment_id"]: item for item in data["receivable"]}
    first = by_id[confirmed.pk]
    assert first["title"] == confirmed.vacancy.title
    assert first["company_name"] == confirmed.vacancy.company.legal_name
    assert first["starts_at"] == confirmed.vacancy.starts_at.isoformat()
    assert first["net_cents"] == 9700
    assert first["expected_release_at"] == (confirmed.vacancy.ends_at + window).isoformat()
    assert by_id[awaiting.pk]["expected_release_at"] == (awaiting.check_out_at + window).isoformat()


def test_forecast_follows_platform_parameters():
    worker = make_worker()
    assignment = make_assignment(worker=worker)
    params = PlatformParameters.get()
    params.contest_window_minutes = 2
    params.save()

    item = worker_client(worker).get(URL).json()["receivable"][0]

    expected = assignment.vacancy.ends_at + timedelta(minutes=2)
    assert item["expected_release_at"] == expected.isoformat()


def test_company_approval_moves_value_from_receivable_to_released():
    worker = make_worker()
    assignment = finished_shift(worker=worker)
    company_user = assignment.vacancy.company.members.first().user

    response = client_for(company_user).post(f"/api/assignments/{assignment.pk}/approve/")
    assert response.status_code == 200

    data = worker_client(worker).get(URL).json()
    assert data["totals"] == {"receivable_cents": 0, "released_cents": 9700, "fees_cents": 300}
    assert data["receivable"] == []
    [item] = data["released"]
    assert item["gross_cents"] == 10000
    assert item["fee_cents"] == 300
    assert item["net_cents"] == 9700
    assert item["title"] == assignment.vacancy.title
    assert item["released_at"]
    assert item["pix_destination"] == worker.masked_pix_key
    assert worker.pix_key not in item["pix_destination"]


def test_automatic_approval_also_releases_to_wallet():
    worker = make_worker()
    assignment = finished_shift(worker=worker)
    window = PlatformParameters.get().contest_window_minutes

    process_deadlines(now=assignment.check_out_at + timedelta(minutes=window + 1))

    data = worker_client(worker).get(URL).json()
    assert data["totals"]["receivable_cents"] == 0
    assert data["totals"]["released_cents"] == 9700


def test_totals_match_ledger_and_do_not_depend_on_stored_balance():
    worker = make_worker()
    assignment = finished_shift(worker=worker)
    assignments.approve_hours(assignment, now=timezone.now())
    assignments.settle(assignment)

    data = worker_client(worker).get(URL).json()

    ledger = LedgerEntry.objects.filter(assignment__worker=worker)
    payout = sum(e.amount_cents for e in ledger if e.kind == "REPASSE_PRESTADOR")
    fee = sum(e.amount_cents for e in ledger if e.kind == "TAXA_PLATAFORMA")
    assert data["totals"]["released_cents"] == payout
    assert data["totals"]["fees_cents"] == fee


def test_contested_and_cancelled_assignments_are_not_receivable():
    worker = make_worker()
    contested = finished_shift(worker=worker)
    assignments.contest(contested, reason="Horas divergentes", now=timezone.now())

    data = worker_client(worker).get(URL).json()

    assert data["receivable"] == []
    assert data["totals"]["receivable_cents"] == 0


def test_only_own_data_is_shown():
    mine, other = make_worker(), make_worker()
    make_assignment(worker=other)
    paid = finished_shift(worker=other)
    assignments.approve_hours(paid, now=timezone.now())
    assignments.settle(paid)

    data = worker_client(mine).get(URL).json()

    assert data["totals"] == {"receivable_cents": 0, "released_cents": 0, "fees_cents": 0}
    assert data["receivable"] == [] and data["released"] == []


def test_access_is_restricted_to_authenticated_workers():
    assert APIClient().get(URL).status_code in (401, 403)
    company = make_company()
    assert client_for(company.members.first().user).get(URL).status_code == 403
