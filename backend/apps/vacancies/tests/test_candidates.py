"""US42: aprovar ou recusar candidatos da vaga."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Notification
from apps.core.tests.factories import (
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
)
from apps.vacancies import application_services as applications
from apps.vacancies.models import Application, Assignment
from apps.workers.models import WorkerDocument

pytestmark = pytest.mark.django_db


def now():
    return timezone.now()


def company_client(company):
    client = APIClient()
    client.force_login(company.members.first().user)
    return client


def setup(positions=1, **kw):
    vacancy = make_published_vacancy(now=now(), positions=positions, **kw)
    worker = make_worker(phone="11999998888")
    application = applications.apply_to_vacancy(vacancy, worker, now=now())
    return vacancy, worker, application


def approve(client, application):
    return client.post(f"/api/applications/{application.pk}/approve/")


def test_candidate_list_shows_safe_fields_only():
    vacancy, worker, application = setup()
    paid = make_assignment(worker=worker, now=now(), starts_in_hours=200)
    Assignment.objects.filter(pk=paid.pk).update(status=Assignment.Status.PAID)
    WorkerDocument.objects.create(
        worker=worker, kind="SELFIE", file=SimpleUploadedFile("s.png", b"png")
    )
    response = company_client(vacancy.company).get(f"/api/vacancies/{vacancy.pk}/candidates/")
    assert response.status_code == 200
    data = response.json()
    (candidate,) = data["candidates"]
    assert candidate["name"] == worker.full_name.split()[0]
    assert candidate["verified"] is True
    assert candidate["completed_shifts"] == 1
    assert candidate["applied_at"] and candidate["photo_url"]
    body = response.content.decode()
    assert worker.cpf not in body
    assert worker.pix_key not in body
    assert "11999998888" not in body
    assert data["team"] == []


def test_approve_creates_assignment_updates_counter_and_notifies():
    vacancy, worker, application = setup(positions=2)
    response = approve(company_client(vacancy.company), application)
    assert response.status_code == 200
    application.refresh_from_db()
    assert application.status == Application.Status.APPROVED
    assignment = Assignment.objects.get(application=application)
    assert assignment.status == Assignment.Status.CONFIRMED
    assert vacancy.filled_positions == 1
    assert Notification.objects.filter(user=worker.user, kind="CANDIDATURA_APROVADA").count() == 1


def test_full_team_refuses_new_approval_and_flags_team_complete():
    vacancy, _, first = setup(positions=1)
    second = applications.apply_to_vacancy(vacancy, make_worker(), now=now())
    client = company_client(vacancy.company)
    assert approve(client, first).status_code == 200
    response = approve(client, second)
    assert response.status_code == 409
    assert "posição livre" in response.json()["detail"]
    second.refresh_from_db()
    assert second.status == Application.Status.PENDING
    data = client.get(f"/api/vacancies/{vacancy.pk}/candidates/").json()
    assert data["team_complete"] is True


def test_reject_sets_recusada_and_notifies():
    vacancy, worker, application = setup()
    response = company_client(vacancy.company).post(f"/api/applications/{application.pk}/reject/")
    assert response.status_code == 200
    application.refresh_from_db()
    assert application.status == Application.Status.REJECTED
    assert Notification.objects.filter(user=worker.user, kind="CANDIDATURA_RECUSADA").count() == 1
    assert not Assignment.objects.exists()


def test_cannot_decide_twice():
    vacancy, _, application = setup()
    client = company_client(vacancy.company)
    assert client.post(f"/api/applications/{application.pk}/reject/").status_code == 200
    assert approve(client, application).status_code == 409


def test_closed_applications_still_approvable_until_shift_start():
    from apps.core.deadlines import process_deadlines

    vacancy, _, application = setup(starts_in_hours=48)
    process_deadlines(vacancy.starts_at - timedelta(hours=1))
    vacancy.refresh_from_db()
    assert vacancy.status == "CANDIDATURAS_ENCERRADAS"
    assert approve(company_client(vacancy.company), application).status_code == 200


def test_approval_after_shift_start_is_refused_unless_reopened():
    vacancy, _, application = setup(starts_in_hours=48)
    vacancy.starts_at = now() - timedelta(minutes=10)
    vacancy.save(update_fields=["starts_at"])
    client = company_client(vacancy.company)
    response = approve(client, application)
    assert response.status_code == 409
    assert "já começou" in response.json()["detail"]

    vacancy.reopened = True
    vacancy.save(update_fields=["reopened"])
    assert approve(client, application).status_code == 200


def test_contact_released_only_after_assignment():
    vacancy, worker, application = setup()
    client = company_client(vacancy.company)
    before = client.get(f"/api/vacancies/{vacancy.pk}/candidates/").json()
    assert before["team"] == []
    assert "11999998888" not in str(before)
    approve(client, application)
    after = client.get(f"/api/vacancies/{vacancy.pk}/candidates/").json()
    (member,) = after["team"]
    assert member["first_name"] == worker.full_name.split()[0]
    assert member["phone"] == "11999998888"
    assert after["candidates"] == []
    assert worker.cpf not in str(after) and worker.pix_key not in str(after)


def test_other_company_cannot_decide_or_see():
    vacancy, _, application = setup()
    intruder = company_client(make_company())
    assert approve(intruder, application).status_code == 404
    assert intruder.post(f"/api/applications/{application.pk}/reject/").status_code == 404
    assert intruder.get(f"/api/vacancies/{vacancy.pk}/candidates/").status_code == 404
    assert intruder.get(f"/api/applications/{application.pk}/photo/").status_code == 404
    application.refresh_from_db()
    assert application.status == Application.Status.PENDING


def test_workers_and_anonymous_are_denied():
    vacancy, worker, application = setup()
    anonymous = APIClient()
    assert approve(anonymous, application).status_code == 403
    worker_client = APIClient()
    worker_client.force_login(worker.user)
    assert approve(worker_client, application).status_code == 403
    assert worker_client.get(f"/api/vacancies/{vacancy.pk}/candidates/").status_code == 403


def test_photo_is_served_to_vacancy_company():
    vacancy, worker, application = setup()
    WorkerDocument.objects.create(
        worker=worker, kind="SELFIE", file=SimpleUploadedFile("s.png", b"png-bytes")
    )
    response = company_client(vacancy.company).get(f"/api/applications/{application.pk}/photo/")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"png-bytes"
