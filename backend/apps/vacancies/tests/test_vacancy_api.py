from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.deadlines import process_deadlines
from apps.core.tests.factories import make_company, make_worker
from apps.payments.models import Custody, LedgerEntry
from apps.vacancies.models import Vacancy

pytestmark = pytest.mark.django_db


def payload(**overrides):
    start = timezone.now() + timedelta(hours=48)
    data = {
        "title": "Carga e descarga",
        "category": "CARGA_DESCARGA",
        "description": "Descarregar caminhão",
        "street": "Praça da Sé",
        "city": "São Paulo",
        "state": "SP",
        "latitude": "-23.550520",
        "longitude": "-46.633308",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=4)).isoformat(),
        "pay_per_person_cents": 10000,
        "positions": 3,
    }
    data.update(overrides)
    return data


def login_as(company):
    client = APIClient()
    client.force_login(company.members.first().user)
    return client


def create(client, **overrides):
    return client.post("/api/vacancies/", payload(**overrides), format="json")


def test_empresa_aprovada_cria_vaga_aguardando_pagamento_com_total():
    company = make_company()
    response = create(login_as(company))
    assert response.status_code == 201
    assert response.data["status"] == "AGUARDANDO_PAGAMENTO"
    assert response.data["total_cents"] == 30000  # valor × pessoas
    assert Custody.objects.get().status == "PENDENTE"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"starts_at": (timezone.now() + timedelta(hours=2)).isoformat()}, "antecedência"),
        ({"pay_per_person_cents": 99}, "R$ 1,00"),
        ({"positions": 0}, "ao menos 1"),
    ],
)
def test_dados_invalidos_nao_criam_vaga(overrides, message):
    response = create(login_as(make_company()), **overrides)
    assert response.status_code == 400
    assert message in response.data["detail"]
    assert not Vacancy.objects.exists()


def test_fim_antes_do_inicio_nao_cria_vaga():
    start = timezone.now() + timedelta(hours=48)
    response = create(
        login_as(make_company()),
        starts_at=start.isoformat(),
        ends_at=(start - timedelta(hours=1)).isoformat(),
    )
    assert response.status_code == 400
    assert "depois do início" in response.data["detail"]
    assert not Vacancy.objects.exists()


def test_empresa_pendente_ve_cadastro_em_analise():
    response = create(login_as(make_company(approved=False)))
    assert response.status_code == 403
    assert response.data["detail"] == "Cadastro em análise"
    assert not Vacancy.objects.exists()


def test_prestador_nao_cria_vaga():
    client = APIClient()
    client.force_login(make_worker().user)
    assert create(client).status_code == 403


def test_pagar_retem_custodia_e_publica():
    company = make_company()
    client = login_as(company)
    vacancy_id = create(client).data["id"]
    response = client.post(f"/api/vacancies/{vacancy_id}/pay/")
    assert response.status_code == 200
    assert response.data["status"] == "PUBLICADA"
    assert response.data["retained_cents"] == 30000
    custody = Custody.objects.get()
    assert custody.status == "RETIDA"
    entry = LedgerEntry.objects.get()
    assert (entry.kind, entry.amount_cents) == ("RETENCAO", 30000)


def test_pagar_duas_vezes_nao_duplica_lancamento():
    client = login_as(make_company())
    vacancy_id = create(client).data["id"]
    client.post(f"/api/vacancies/{vacancy_id}/pay/")
    assert client.post(f"/api/vacancies/{vacancy_id}/pay/").status_code == 409
    assert LedgerEntry.objects.count() == 1


def test_outra_empresa_nao_paga_nem_ve_a_vaga():
    vacancy_id = create(login_as(make_company())).data["id"]
    other = login_as(make_company())
    assert other.post(f"/api/vacancies/{vacancy_id}/pay/").status_code == 404
    assert other.get(f"/api/vacancies/{vacancy_id}/").status_code == 404
    assert other.get("/api/company/vacancies/").data["results"] == []


def test_vaga_nao_paga_em_24h_e_cancelada_sem_cobranca():
    client = login_as(make_company())
    start = timezone.now() + timedelta(days=5)
    vacancy_id = create(
        client, starts_at=start.isoformat(), ends_at=(start + timedelta(hours=4)).isoformat()
    ).data["id"]
    process_deadlines(now=timezone.now() + timedelta(hours=25))
    vacancy = Vacancy.objects.get(pk=vacancy_id)
    assert vacancy.status == "CANCELADA"
    assert vacancy.custody.status == "CANCELADA"
    assert not LedgerEntry.objects.exists()


def test_minhas_vagas_lista_status_posicoes_e_total_retido():
    client = login_as(make_company())
    paid = create(client, positions=2).data["id"]
    client.post(f"/api/vacancies/{paid}/pay/")
    create(client, title="Sem pagar")
    data = client.get("/api/company/vacancies/").data
    assert len(data["results"]) == 2
    by_id = {r["id"]: r for r in data["results"]}
    assert by_id[paid]["status"] == "PUBLICADA"
    assert by_id[paid]["filled_positions"] == 0
    assert by_id[paid]["positions"] == 2
    assert by_id[paid]["retained_cents"] == 20000
    assert data["total_retained_cents"] == 20000
