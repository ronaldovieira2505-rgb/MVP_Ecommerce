"""US50 (check-in por localização) e US54 (check-out)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.models import PlatformParameters, StateTransition
from apps.core.tests.factories import LAT, LNG, make_assignment, make_worker
from apps.vacancies.models import Assignment

pytestmark = pytest.mark.django_db


def client_for(worker):
    client = APIClient()
    client.force_login(worker.user)
    return client


def assignment_starting_in(minutes, **kw):
    """Alocação CONFIRMADA cujo turno começa daqui a `minutes` (pode ser negativo)."""
    now = timezone.now()
    # Cria com antecedência (regras de publicação/candidatura) e desloca o turno para a janela.
    assignment = make_assignment(now=now, starts_in_hours=48, **kw)
    vacancy = assignment.vacancy
    vacancy.starts_at = now + timedelta(minutes=minutes)
    vacancy.ends_at = vacancy.starts_at + timedelta(hours=4)
    vacancy.save()
    return assignment


def check_in(client, assignment, lat=LAT, lng=LNG):
    return client.post(
        f"/api/assignments/{assignment.pk}/check-in/",
        {"lat": lat, "lng": lng, "accuracy": 12},
        format="json",
    )


def job(client, assignment):
    groups = client.get("/api/workers/me/jobs/").json()["groups"]
    items = [i for g in groups.values() for i in g if i["kind"] == "assignment"]
    return next(i for i in items if i["id"] == assignment.pk)


def test_check_in_button_available_inside_window():
    assignment = assignment_starting_in(20)
    assert job(client_for(assignment.worker), assignment)["can_check_in"] is True


def test_check_in_window_edges_use_platform_parameters():
    client_assignment = assignment_starting_in(31)
    client = client_for(client_assignment.worker)
    item = job(client, client_assignment)
    assert item["can_check_in"] is False
    assert item["check_in_opens_at"] < item["starts_at"]
    params = PlatformParameters.get()
    params.checkin_open_minutes_before = 45
    params.save()
    assert job(client, client_assignment)["can_check_in"] is True


def test_button_hidden_after_tolerance_and_for_other_statuses():
    late = assignment_starting_in(-31)
    assert job(client_for(late.worker), late)["can_check_in"] is False


def test_check_in_within_radius_starts_execution():
    assignment = assignment_starting_in(0)
    client = client_for(assignment.worker)
    response = check_in(client, assignment, lat=LAT + 0.0007)  # ~78 m
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["status"] == "EM_EXECUCAO"
    assert data["check_in_at"]
    assert data["can_check_out"] is True and data["can_check_in"] is False
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.IN_PROGRESS
    assert assignment.check_in_at is not None
    assert float(assignment.check_in_lat) == pytest.approx(LAT + 0.0007, abs=1e-6)
    assert 0 < assignment.check_in_distance_m <= 150
    assert StateTransition.objects.filter(
        entity_type="Assignment", entity_id=assignment.pk, to_state="EM_EXECUCAO"
    ).exists()


def test_check_in_beyond_radius_is_rejected_on_the_server():
    assignment = assignment_starting_in(0)
    response = check_in(client_for(assignment.worker), assignment, lat=LAT + 0.002)  # ~222 m
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail.startswith("Você está a ")
    assert "m do local. Aproxime-se para registrar a chegada" in detail
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED
    assert assignment.check_in_at is None


def test_radius_comes_from_platform_parameters():
    assignment = assignment_starting_in(0)
    params = PlatformParameters.get()
    params.geofence_radius_m = 300
    params.save()
    assert check_in(client_for(assignment.worker), assignment, lat=LAT + 0.002).status_code == 200


def test_check_in_outside_window_is_rejected():
    assignment = assignment_starting_in(120)
    response = check_in(client_for(assignment.worker), assignment)
    assert response.status_code == 409
    assert "janela" in response.json()["detail"]
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


@pytest.mark.parametrize(
    "lat,lng",
    [(91, LNG), (-91, LNG), (LAT, 181), (LAT, -181), ("abc", LNG), (LAT, "nan")],
)
def test_invalid_coordinates_are_rejected(lat, lng):
    assignment = assignment_starting_in(0)
    response = check_in(client_for(assignment.worker), assignment, lat=lat, lng=lng)
    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_missing_location_is_rejected():
    assignment = assignment_starting_in(0)
    response = client_for(assignment.worker).post(
        f"/api/assignments/{assignment.pk}/check-in/", {}, format="json"
    )
    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_cannot_check_in_twice():
    assignment = assignment_starting_in(0)
    client = client_for(assignment.worker)
    assert check_in(client, assignment).status_code == 200
    assert check_in(client, assignment).status_code == 409


def test_other_worker_and_anonymous_cannot_act():
    assignment = assignment_starting_in(0)
    assert check_in(client_for(make_worker()), assignment).status_code == 404
    assert check_in(APIClient(), assignment).status_code == 403
    other = client_for(make_worker())
    assert other.post(f"/api/assignments/{assignment.pk}/check-out/").status_code == 404
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_check_out_moves_to_awaiting_validation():
    assignment = assignment_starting_in(0)
    client = client_for(assignment.worker)
    assert check_in(client, assignment).status_code == 200
    response = client.post(f"/api/assignments/{assignment.pk}/check-out/")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["status"] == "AGUARDANDO_VALIDACAO"
    assert data["check_in_at"] and data["check_out_at"]
    assert data["check_out_auto"] is False
    assert data["can_check_out"] is False
    assignment.refresh_from_db()
    assert assignment.check_out_at is not None and not assignment.check_out_auto


def test_check_out_requires_execution():
    assignment = assignment_starting_in(0)
    response = client_for(assignment.worker).post(f"/api/assignments/{assignment.pk}/check-out/")
    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.CONFIRMED


def test_forgotten_check_out_is_registered_automatically():
    assignment = assignment_starting_in(0)
    assert check_in(client_for(assignment.worker), assignment).status_code == 200
    ends_at = assignment.vacancy.ends_at
    params = PlatformParameters.get()
    limit = ends_at + timedelta(minutes=params.auto_checkout_minutes_after_end)
    assert "checkouts_automaticos" not in process_deadlines(limit)
    done = process_deadlines(limit + timedelta(minutes=1))
    assert done["checkouts_automaticos"] == 1
    assignment.refresh_from_db()
    assert assignment.status == Assignment.Status.AWAITING_VALIDATION
    assert assignment.check_out_auto is True
    assert assignment.check_out_at == ends_at
