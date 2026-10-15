from datetime import timedelta

import pytest
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
from apps.vacancies.models import Application, Vacancy, VacancyChange

pytestmark = pytest.mark.django_db

LOCKED = "Não é possível alterar: já há prestador aprovado"


def login_as(company):
    client = APIClient()
    client.force_login(company.members.first().user)
    return client


def published(company=None):
    return make_published_vacancy(company=company, now=timezone.now())


def test_edita_campos_e_audita():
    vacancy = published()
    client = login_as(vacancy.company)
    response = client.patch(
        f"/api/vacancies/{vacancy.pk}/",
        {"title": "Novo título", "description": "Nova descrição", "city": "Campinas"},
        format="json",
    )
    assert response.status_code == 200
    vacancy.refresh_from_db()
    assert vacancy.title == "Novo título"
    changes = {c.field: c for c in VacancyChange.objects.filter(vacancy=vacancy)}
    assert set(changes) == {"title", "description", "city"}
    assert changes["title"].old_value == "Carga e descarga"
    assert changes["title"].new_value == "Novo título"
    assert changes["title"].user == vacancy.company.members.first().user


@pytest.mark.parametrize("field, value", [("pay_per_person_cents", 20000), ("positions", 5)])
def test_valor_e_posicoes_nao_sao_editaveis(field, value):
    vacancy = published()
    response = login_as(vacancy.company).patch(
        f"/api/vacancies/{vacancy.pk}/", {field: value}, format="json"
    )
    assert response.status_code == 400
    assert "remova o anúncio" in response.data["detail"]
    vacancy.refresh_from_db()
    assert vacancy.pay_per_person_cents == 10000
    assert vacancy.positions == 1
    assert not VacancyChange.objects.exists()


def test_novo_inicio_respeita_antecedencia_minima():
    vacancy = published()
    start = timezone.now() + timedelta(hours=2)
    response = login_as(vacancy.company).patch(
        f"/api/vacancies/{vacancy.pk}/",
        {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=4)).isoformat()},
        format="json",
    )
    assert response.status_code == 400
    assert "antecedência" in response.data["detail"]
    assert not VacancyChange.objects.exists()


def test_novo_inicio_valido_e_salvo():
    vacancy = published()
    start = timezone.now() + timedelta(hours=72)
    response = login_as(vacancy.company).patch(
        f"/api/vacancies/{vacancy.pk}/",
        {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=5)).isoformat()},
        format="json",
    )
    assert response.status_code == 200
    assert set(VacancyChange.objects.values_list("field", flat=True)) == {"starts_at", "ends_at"}


def test_fim_antes_do_inicio_e_recusado():
    vacancy = published()
    response = login_as(vacancy.company).patch(
        f"/api/vacancies/{vacancy.pk}/",
        {"ends_at": (vacancy.starts_at - timedelta(hours=1)).isoformat()},
        format="json",
    )
    assert response.status_code == 400


def test_vaga_com_aprovado_nao_edita_nem_remove():
    assignment = make_assignment(now=timezone.now())
    vacancy = assignment.vacancy
    client = login_as(vacancy.company)

    patch = client.patch(f"/api/vacancies/{vacancy.pk}/", {"title": "X"}, format="json")
    remove = client.post(f"/api/vacancies/{vacancy.pk}/remove/")

    assert patch.status_code == 409
    assert patch.data["detail"] == LOCKED
    assert remove.status_code == 409
    assert remove.data["detail"] == LOCKED
    vacancy.refresh_from_db()
    assert vacancy.title == "Carga e descarga"
    assert vacancy.status == Vacancy.Status.PUBLISHED
    assert not VacancyChange.objects.exists()


def test_vaga_com_candidaturas_encerradas_nao_edita_nem_remove():
    vacancy = published()
    Vacancy.objects.filter(pk=vacancy.pk).update(status=Vacancy.Status.APPLICATIONS_CLOSED)
    client = login_as(vacancy.company)
    patch = client.patch(f"/api/vacancies/{vacancy.pk}/", {"title": "X"}, format="json")
    assert patch.status_code == 400
    assert client.post(f"/api/vacancies/{vacancy.pk}/remove/").status_code == 409


def test_remove_estorna_expira_pendentes_e_notifica():
    vacancy = published()
    worker = make_worker()
    applications.apply_to_vacancy(vacancy, worker, now=timezone.now())

    response = login_as(vacancy.company).post(f"/api/vacancies/{vacancy.pk}/remove/")

    assert response.status_code == 200
    assert response.data["status"] == "CANCELADA"
    vacancy.refresh_from_db()
    assert vacancy.custody.status == "ENCERRADA"
    assert sorted(vacancy.custody.entries.values_list("kind", "amount_cents")) == [
        ("ESTORNO_CONTRATANTE", 10000),
        ("RETENCAO", 10000),
    ]
    assert vacancy.applications.get().status == Application.Status.EXPIRED
    assert Notification.objects.filter(user=worker.user, kind="VAGA_REMOVIDA").exists()


def test_outra_empresa_nao_edita_nem_remove():
    vacancy = published()
    client = login_as(make_company())
    patch = client.patch(f"/api/vacancies/{vacancy.pk}/", {"title": "X"}, format="json")
    assert patch.status_code == 404
    assert client.post(f"/api/vacancies/{vacancy.pk}/remove/").status_code == 404
    vacancy.refresh_from_db()
    assert vacancy.status == Vacancy.Status.PUBLISHED
