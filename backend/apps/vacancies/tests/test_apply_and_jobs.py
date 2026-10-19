"""US37 (candidatura com um clique) e US38 (acompanhar o status)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification, PlatformParameters
from apps.core.tests.factories import (
    make_assignment,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import application_services as applications
from apps.vacancies import services as vacancy_services
from apps.vacancies.models import Application

pytestmark = pytest.mark.django_db


def now():
    return timezone.now()


def published(**kw):
    return make_published_vacancy(now=now(), **kw)


def client_for(worker):
    client = APIClient()
    client.force_login(worker.user)
    return client


def apply(client, vacancy):
    return client.post(f"/api/vacancies/{vacancy.pk}/apply/")


def detail(client, vacancy):
    response = client.get(f"/api/vacancies/{vacancy.pk}/")
    assert response.status_code == 200, response.content
    return response.json()


def test_apply_creates_pending_application():
    vacancy, worker = published(), make_worker()
    response = apply(client_for(worker), vacancy)
    assert response.status_code == 201
    assert response.json()["status"] == "PENDENTE"
    assert response.json()["net_cents"] == 9700
    application = Application.objects.get(vacancy=vacancy, worker=worker)
    assert application.status == Application.Status.PENDING


def test_second_attempt_returns_error_and_detail_shows_sent():
    vacancy, worker = published(), make_worker()
    client = client_for(worker)
    assert apply(client, vacancy).status_code == 201
    assert apply(client, vacancy).status_code == 409
    assert Application.objects.filter(vacancy=vacancy, worker=worker).count() == 1
    data = detail(client, vacancy)
    assert data["can_apply"] is False
    assert data["my_application"]["status"] == "PENDENTE"
    assert "já se candidatou" in data["apply_blocker"]


def test_overlapping_assignment_blocks_with_message():
    first = make_assignment(starts_in_hours=48, now=now())
    overlapping = published(starts_in_hours=49)
    client = client_for(first.worker)
    response = apply(client, overlapping)
    assert response.status_code == 409
    assert response.json()["detail"] == "Você já tem um turno nesse horário."
    assert detail(client, overlapping)["apply_blocker"] == "Você já tem um turno nesse horário."


def test_closed_applications_disable_with_reason():
    vacancy = published(starts_in_hours=13)
    params = PlatformParameters.get()
    params.applications_close_minutes_before = 13 * 60
    params.save()
    client = client_for(make_worker())
    data = detail(client, vacancy)
    assert data["can_apply"] is False
    assert "encerradas" in data["apply_blocker"]
    response = apply(client, vacancy)
    assert response.status_code == 409
    assert "encerradas" in response.json()["detail"]


def test_closing_window_comes_from_platform_parameters():
    vacancy = published(starts_in_hours=48)
    client = client_for(make_worker())
    assert detail(client, vacancy)["can_apply"] is True
    params = PlatformParameters.get()
    params.applications_close_minutes_before = 49 * 60
    params.save()
    assert detail(client, vacancy)["can_apply"] is False


def test_full_vacancy_disables_with_reason():
    vacancy = published(positions=1)
    make_assignment(vacancy=vacancy, now=now())
    client = client_for(make_worker())
    data = detail(client, vacancy)
    assert data["can_apply"] is False
    assert "lotada" in data["apply_blocker"]
    assert apply(client, vacancy).status_code == 409


def test_suspended_worker_sees_date_and_cannot_apply():
    vacancy = published()
    worker = make_worker(suspended_until=now() + timedelta(days=3))
    client = client_for(worker)
    expected = worker.suspension_message
    assert expected.startswith("Sua conta está suspensa até ")
    assert detail(client, vacancy)["apply_blocker"] == expected
    response = apply(client, vacancy)
    assert response.status_code == 409
    assert response.json()["detail"] == expected
    assert not Application.objects.exists()


def test_unapproved_or_without_pix_cannot_apply():
    vacancy = published()
    assert apply(client_for(make_worker(approved=False)), vacancy).status_code == 409
    no_pix = make_worker()
    no_pix.pix_key = ""
    no_pix.save()
    assert apply(client_for(no_pix), vacancy).status_code == 409


def test_only_workers_can_apply():
    vacancy = published()
    assert apply(APIClient(), vacancy).status_code == 403
    company_client = APIClient()
    company_client.force_login(vacancy.company.members.first().user)
    assert apply(company_client, vacancy).status_code == 403


def test_withdraw_goes_to_desistencia_without_penalty():
    vacancy, worker = published(), make_worker()
    client = client_for(worker)
    application_id = apply(client, vacancy).json()["id"]
    response = client.post(f"/api/applications/{application_id}/withdraw/")
    assert response.status_code == 200
    assert response.json()["status"] == "DESISTENCIA"
    worker.refresh_from_db()
    assert worker.suspended_until is None
    assert client.post(f"/api/applications/{application_id}/withdraw/").status_code == 409


def test_cannot_withdraw_someone_elses_application():
    vacancy, owner = published(), make_worker()
    application_id = apply(client_for(owner), vacancy).json()["id"]
    response = client_for(make_worker()).post(f"/api/applications/{application_id}/withdraw/")
    assert response.status_code == 404
    assert Application.objects.get(pk=application_id).status == Application.Status.PENDING


def test_my_jobs_groups_by_status():
    worker = make_worker()
    client = client_for(worker)
    pending = published(title="Pendente")
    apply(client, pending)
    approved = published(title="Aprovada", starts_in_hours=60)
    approved_app = applications.apply_to_vacancy(approved, worker, now=now())
    applications.approve_application(approved_app, now=now())
    rejected = published(title="Recusada")
    rejected_app = applications.apply_to_vacancy(rejected, worker, now=now())
    applications.reject_application(rejected_app)
    withdrawn = published(title="Desistida")
    withdrawn_app = applications.apply_to_vacancy(withdrawn, worker, now=now())
    applications.withdraw_application(withdrawn_app)
    expired = published(title="Expirada")
    applications.apply_to_vacancy(expired, worker, now=now())
    vacancy_services.remove_vacancy(expired)

    response = client.get("/api/workers/me/jobs/")
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [i["title"] for i in groups["waiting"]] == ["Pendente"]
    assert [i["title"] for i in groups["upcoming"]] == ["Aprovada"]
    assert groups["in_progress"] == []
    assert groups["completed"] == []
    assert {i["title"]: i["status"] for i in groups["closed"]} == {
        "Recusada": "RECUSADA",
        "Desistida": "DESISTENCIA",
        "Expirada": "EXPIRADA",
    }
    waiting = groups["waiting"][0]
    assert waiting["can_withdraw"] is True
    assert waiting["net_cents"] == 9700
    assert waiting["company_name"] and waiting["starts_at"]
    assert groups["upcoming"][0]["can_withdraw"] is False


def test_my_jobs_in_progress_completed_and_no_show():
    from apps.core.tests.factories import LAT, LNG, make_paid_ready_assignment
    from apps.vacancies import assignment_services as assignments

    assignment = make_paid_ready_assignment(now=now())
    worker = assignment.worker
    in_progress = make_assignment(worker=worker, now=now(), starts_in_hours=200)
    assignments.check_in(in_progress, lat=LAT, lng=LNG, now=in_progress.vacancy.starts_at)
    missed = make_assignment(worker=worker, now=now(), starts_in_hours=400)
    assignments.mark_no_show(missed, now=missed.vacancy.starts_at + timedelta(hours=1))
    assignments.settle(assignment)

    groups = client_for(worker).get("/api/workers/me/jobs/").json()["groups"]
    assert [i["status"] for i in groups["completed"]] == ["PAGA"]
    assert [i["status"] for i in groups["in_progress"]] == ["EM_EXECUCAO"]
    assert [i["status"] for i in groups["closed"]] == ["FALTA"]


def test_my_jobs_is_private_to_the_worker():
    other = make_worker()
    apply(client_for(other), published())
    groups = client_for(make_worker()).get("/api/workers/me/jobs/").json()["groups"]
    assert all(items == [] for items in groups.values())
    assert APIClient().get("/api/workers/me/jobs/").status_code == 403


def test_status_changes_notify_the_worker():
    worker = make_worker()
    approved = published()
    rejected = published(title="Outra")
    expired = published(title="Terceira")
    approved_app = applications.apply_to_vacancy(approved, worker, now=now())
    rejected_app = applications.apply_to_vacancy(rejected, worker, now=now())
    applications.apply_to_vacancy(expired, worker, now=now())
    applications.approve_application(approved_app, now=now())
    applications.reject_application(rejected_app)
    vacancy_services.remove_vacancy(expired)
    kinds = sorted(Notification.objects.filter(user=worker.user).values_list("kind", flat=True))
    assert kinds == ["CANDIDATURA_APROVADA", "CANDIDATURA_RECUSADA", "VAGA_REMOVIDA"]
    links = set(Notification.objects.filter(user=worker.user).values_list("link", flat=True))
    assert links == {"/meus-trabalhos"}


def test_expiry_by_deadline_notifies_the_worker():
    from apps.core.deadlines import process_deadlines

    worker = make_worker()
    vacancy = published(starts_in_hours=100)
    applications.apply_to_vacancy(vacancy, worker, now=now())
    process_deadlines(vacancy.starts_at + timedelta(hours=1))
    assert Application.objects.get().status == Application.Status.EXPIRED
    assert Notification.objects.filter(user=worker.user, kind="CANDIDATURA_EXPIRADA").count() == 1
