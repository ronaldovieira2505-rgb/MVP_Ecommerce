import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.companies.models import Company, CompanyMember
from apps.core.models import PlatformParameters
from apps.core.tests.factories import make_company

pytestmark = pytest.mark.django_db

CNPJ = "11222333000181"  # dígitos verificadores válidos
PASSWORD = "senha-forte-123"


def payload(**overrides):
    data = {
        "cnpj": CNPJ,
        "legal_name": "Empresa Teste LTDA",
        "trade_name": "Teste",
        "registration_status": "ATIVA",
        "street": "Rua A",
        "number": "10",
        "city": "São Paulo",
        "state": "SP",
        "zip_code": "01001-000",
        "state_registration": "isento",
        "tax_regime": "SIMPLES",
        "phone": "11999998888",
        "preferred_payment_method": "PIX",
        "owner_name": "Maria Souza",
        "email": "Maria@Example.com",
        "password": PASSWORD,
    }
    data.update(overrides)
    return data


def register(client, **overrides):
    return client.post("/api/companies/register/", payload(**overrides), format="json")


# --- consulta de CNPJ -------------------------------------------------------------------


def test_consulta_preenche_dados_pela_brasilapi_fake(fake_cnpj_lookup):
    response = APIClient().get(f"/api/cnpj/{CNPJ}/")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    data = body["data"]
    assert data["legal_name"] == "Empresa Simulada 11222333 LTDA"
    assert data["trade_name"] == "Simulada 11222333"
    assert data["registration_status"] == "ATIVA"
    assert data["street"] == "Rua das Flores"
    assert data["city"] == "São Paulo"
    assert fake_cnpj_lookup.calls == [(CNPJ, 5)]


def test_limite_da_consulta_vem_de_platform_parameters(fake_cnpj_lookup):
    params = PlatformParameters.get()
    params.cnpj_lookup_timeout_seconds = 2
    params.save()

    APIClient().get(f"/api/cnpj/{CNPJ}/")

    assert fake_cnpj_lookup.calls == [(CNPJ, 2)]


def test_cnpj_com_digitos_invalidos_nao_consulta(fake_cnpj_lookup):
    response = APIClient().get("/api/cnpj/11222333000182/")

    assert response.status_code == 400
    assert response.json()["detail"] == "CNPJ inválido"
    assert fake_cnpj_lookup.calls == []


def test_consulta_de_cnpj_ja_cadastrado_avisa(fake_cnpj_lookup):
    Company.objects.create(cnpj=CNPJ, legal_name="X", tax_regime="SIMPLES")

    response = APIClient().get(f"/api/cnpj/{CNPJ}/")

    assert response.status_code == 409
    assert response.json()["detail"] == "Já existe uma conta para este CNPJ"
    assert fake_cnpj_lookup.calls == []


def test_brasilapi_fora_do_ar_devolve_aviso_para_preencher_manualmente(fake_cnpj_lookup):
    fake_cnpj_lookup.fail = True

    response = APIClient().get(f"/api/cnpj/{CNPJ}/")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body["available"] is False
    assert "manualmente" in body["detail"]


# --- cadastro ---------------------------------------------------------------------------


def test_cadastro_cria_empresa_pendente_e_membro_owner():
    response = register(APIClient())

    assert response.status_code == 201
    company = Company.objects.get(cnpj=CNPJ)
    assert company.verification_status == "PENDENTE"
    assert company.data_unverified is False
    assert company.state_registration == "ISENTO"
    assert company.tax_regime == "SIMPLES"
    assert company.preferred_payment_method == "PIX"
    assert company.zip_code == "01001000"
    member = CompanyMember.objects.get(company=company)
    assert member.role == "OWNER"
    assert member.user.role == Role.COMPANY
    assert member.user.email == "maria@example.com"
    assert member.user.first_name == "Maria Souza"
    assert member.user.check_password(PASSWORD)


def test_cadastro_aceita_cnpj_com_mascara():
    response = register(APIClient(), cnpj="11.222.333/0001-81")

    assert response.status_code == 201
    assert Company.objects.filter(cnpj=CNPJ).exists()


def test_cadastro_com_cnpj_invalido_e_rejeitado():
    response = register(APIClient(), cnpj="11222333000182")

    assert response.status_code == 400
    assert response.json()["detail"] == "CNPJ inválido"
    assert not Company.objects.exists()


def test_cadastro_de_cnpj_ja_existente_e_rejeitado():
    existing = make_company()
    existing.cnpj = CNPJ
    existing.save()

    response = register(APIClient())

    assert response.status_code == 409
    assert response.json()["detail"] == "Já existe uma conta para este CNPJ"
    assert Company.objects.count() == 1


def test_cadastro_com_email_ja_usado_e_rejeitado():
    make_company()
    from django.contrib.auth import get_user_model

    email = get_user_model().objects.get(role=Role.COMPANY).email

    response = register(APIClient(), email=email.upper())

    assert response.status_code == 409
    assert not Company.objects.filter(cnpj=CNPJ).exists()


def test_cadastro_com_brasilapi_fora_do_ar_marca_dados_nao_conferidos(fake_cnpj_lookup):
    fake_cnpj_lookup.fail = True

    response = register(APIClient())

    assert response.status_code == 201
    assert response.json()["data_unverified"] is True
    company = Company.objects.get(cnpj=CNPJ)
    assert company.data_unverified is True
    assert company.verification_status == "PENDENTE"


def test_marcacao_nao_conferidos_visivel_ao_admin(client):
    from apps.core.tests.factories import make_admin

    fake = Company.objects.create(
        cnpj=CNPJ, legal_name="Manual LTDA", tax_regime="NORMAL", data_unverified=True
    )
    client.force_login(make_admin())

    html = client.get("/admin/companies/company/").content.decode()
    assert fake.legal_name in html
    assert "dados não conferidos" in html.lower()


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "curta12"},
        {"tax_regime": "LUCRO"},
        {"preferred_payment_method": "DINHEIRO"},
        {"state_registration": ""},
        {"phone": ""},
        {"owner_name": ""},
        {"email": "nao-e-email"},
    ],
)
def test_cadastro_valida_campos(overrides):
    response = register(APIClient(), **overrides)

    assert response.status_code == 400
    assert not Company.objects.exists()


def test_cadastro_aceita_inscricao_estadual_numerica_e_senha_de_8_caracteres():
    response = register(APIClient(), state_registration="123.456.789", password="12345678")

    assert response.status_code == 201
    assert Company.objects.get(cnpj=CNPJ).state_registration == "123.456.789"


def test_cadastro_nao_armazena_dados_de_cartao():
    response = register(
        APIClient(), preferred_payment_method="CARTAO", card_number="4111111111111111"
    )

    assert response.status_code == 201
    company = Company.objects.get(cnpj=CNPJ)
    assert company.preferred_payment_method == "CARTAO"
    assert "4111111111111111" not in str(company.__dict__.values())


def test_apos_cadastro_empresa_entra_e_ve_status_pendente():
    client = APIClient()
    register(client)

    login = client.post(
        "/api/auth/login/", {"email": "maria@example.com", "password": PASSWORD}, format="json"
    )

    assert login.status_code == 200
    assert login.json()["role"] == "COMPANY"
    assert login.json()["verification_status"] == "PENDENTE"
