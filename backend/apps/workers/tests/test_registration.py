import logging
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.workers.models import Worker

pytestmark = pytest.mark.django_db

CPF = "12345678909"  # dígitos verificadores válidos
PASSWORD = "senha-forte-123"


def years_ago(years):
    today = date.today()
    return today.replace(year=today.year - years, day=1).isoformat()


def payload(**overrides):
    data = {
        "full_name": "João da Silva",
        "cpf": CPF,
        "phone": "11999998888",
        "birth_date": "1990-05-20",
        "email": "Joao@Example.com",
        "password": PASSWORD,
    }
    data.update(overrides)
    return data


def register(client, **overrides):
    return client.post("/api/workers/register/", payload(**overrides), format="json")


def test_cadastro_cria_prestador_pendente_de_documentos_e_ja_logado():
    client = APIClient()

    response = register(client)

    assert response.status_code == 201
    worker = Worker.objects.get(cpf=CPF)
    assert worker.verification_status == "PENDENTE_DOCUMENTOS"
    assert worker.full_name == "João da Silva"
    assert worker.phone == "11999998888"
    assert worker.user.role == Role.WORKER
    assert worker.user.email == "joao@example.com"
    assert worker.user.check_password(PASSWORD)
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["role"] == "WORKER"
    assert me.json()["verification_status"] == "PENDENTE_DOCUMENTOS"


def test_cadastro_aceita_cpf_com_mascara():
    response = register(APIClient(), cpf="123.456.789-09")

    assert response.status_code == 201
    assert Worker.objects.filter(cpf=CPF).exists()


@pytest.mark.parametrize("cpf", ["12345678900", "11111111111", "123", ""])
def test_cpf_invalido_e_rejeitado(cpf):
    response = register(APIClient(), cpf=cpf)

    assert response.status_code == 400
    assert response.json()["errors"]["cpf"]
    assert not Worker.objects.exists()
    assert not get_user_model().objects.exists()


def test_mensagem_de_cpf_invalido():
    response = register(APIClient(), cpf="12345678900")

    assert response.json()["detail"] == "CPF inválido"


def test_cpf_ja_cadastrado_e_rejeitado():
    assert register(APIClient()).status_code == 201

    response = register(APIClient(), email="outro@example.com")

    assert response.status_code == 409
    assert response.json()["detail"] == "Já existe uma conta para este CPF"
    assert Worker.objects.count() == 1
    assert get_user_model().objects.count() == 1


def test_email_ja_cadastrado_e_rejeitado_sem_diferenciar_maiusculas():
    assert register(APIClient()).status_code == 201

    response = register(APIClient(), cpf="52998224725", email="JOAO@example.com")

    assert response.status_code == 409
    assert response.json()["detail"] == "Já existe uma conta com este e-mail"
    assert Worker.objects.count() == 1


def test_menor_de_18_anos_e_rejeitado():
    response = register(APIClient(), birth_date=years_ago(17))

    assert response.status_code == 400
    assert response.json()["detail"] == "É preciso ter 18 anos ou mais"
    assert not Worker.objects.exists()
    assert not get_user_model().objects.exists()


def test_exatamente_18_anos_e_aceito():
    response = register(APIClient(), birth_date=years_ago(18))

    assert response.status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "curta12"},
        {"full_name": ""},
        {"phone": ""},
        {"email": "nao-e-email"},
        {"birth_date": "20/05/1990"},
    ],
)
def test_cadastro_valida_campos(overrides):
    response = register(APIClient(), **overrides)

    assert response.status_code == 400
    assert not Worker.objects.exists()


def test_senha_de_8_caracteres_e_aceita():
    assert register(APIClient(), password="12345678").status_code == 201


def test_resposta_traz_cpf_mascarado_e_nunca_em_claro():
    response = register(APIClient())

    body = response.json()
    assert body["cpf"] == "***.456.789-**"
    assert CPF not in response.content.decode()
    assert "11999998888" not in response.content.decode()


def test_cpf_nao_aparece_em_logs(caplog):
    with caplog.at_level(logging.DEBUG):
        register(APIClient())
        register(APIClient(), email="outro@example.com")

    assert CPF not in caplog.text


def test_painel_complete_seu_perfil_mostra_status_das_etapas():
    client = APIClient()
    register(client)

    response = client.get("/api/workers/me/")

    assert response.status_code == 200
    body = response.json()
    assert body["cpf"] == "***.456.789-**"
    assert body["profile_steps"] == [
        {
            "key": "documentos",
            "label": "Documentos e selfie",
            "done": False,
            "status": "PENDENTE_DOCUMENTOS",
        },
        {"key": "pix", "label": "Chave PIX", "done": False},
    ]


def test_painel_exige_login_de_prestador():
    assert APIClient().get("/api/workers/me/").status_code == 403

    client = APIClient()
    user = get_user_model().objects.create_user(
        username="c@example.com", email="c@example.com", password=PASSWORD, role=Role.COMPANY
    )
    client.force_login(user)
    assert client.get("/api/workers/me/").status_code == 403


def test_prestador_pode_entrar_depois_do_cadastro():
    register(APIClient())

    response = APIClient().post(
        "/api/auth/login/", {"email": "joao@example.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["role"] == "WORKER"
    assert response.json()["verification_status"] == "PENDENTE_DOCUMENTOS"
