import pytest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.accounts.models import Role
from apps.core.models import Notification
from apps.core.notifications import notify
from apps.core.permissions import IsAdminUser, IsCompanyUser, IsObjectOwner, IsWorkerUser
from apps.core.tests.factories import make_admin, make_company, make_user, make_worker

pytestmark = pytest.mark.django_db

PASSWORD = "senha-forte-123"


def post_login(client, email, password):
    return client.post("/api/auth/login/", {"email": email, "password": password}, format="json")


def test_login_cria_sessao_e_me_retorna_dados_do_prestador():
    worker = make_worker()
    client = APIClient()

    response = post_login(client, worker.user.email, PASSWORD)

    assert response.status_code == 200
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json() == {
        "id": worker.user.pk,
        "name": worker.full_name,
        "email": worker.user.email,
        "role": "WORKER",
        "verification_status": "APROVADO",
    }


def test_me_retorna_dados_da_empresa():
    company = make_company(approved=False)
    user = company.members.get().user
    client = APIClient()
    post_login(client, user.email.upper(), PASSWORD)  # e-mail sem diferenciar maiúsculas

    me = client.get("/api/auth/me/").json()

    assert me["role"] == "COMPANY"
    assert me["name"] == company.legal_name
    assert me["verification_status"] == "PENDENTE"


@pytest.mark.parametrize("email_ok,password_ok", [(False, True), (True, False), (False, False)])
def test_credenciais_invalidas_retornam_mesma_mensagem(email_ok, password_ok):
    worker = make_worker()
    email = worker.user.email if email_ok else "outro@example.com"
    password = PASSWORD if password_ok else "errada-123"

    response = post_login(APIClient(), email, password)

    assert response.status_code == 400
    assert response.json() == {"detail": "E-mail ou senha inválidos"}


def test_login_sem_campos_retorna_400():
    response = APIClient().post("/api/auth/login/", {}, format="json")

    assert response.status_code == 400
    assert response.json() == {"detail": "E-mail ou senha inválidos"}


def test_usuario_inativo_nao_entra():
    worker = make_worker()
    worker.user.is_active = False
    worker.user.save()

    assert post_login(APIClient(), worker.user.email, PASSWORD).status_code == 400


def test_logout_encerra_a_sessao():
    worker = make_worker()
    client = APIClient()
    post_login(client, worker.user.email, PASSWORD)

    assert client.post("/api/auth/logout/").status_code == 204

    assert client.get("/api/auth/me/").status_code == 403


def test_me_exige_autenticacao():
    assert APIClient().get("/api/auth/me/").status_code == 403


def test_login_exige_csrf():
    worker = make_worker()
    client = APIClient(enforce_csrf_checks=True)

    assert post_login(client, worker.user.email, PASSWORD).status_code == 403

    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    response = client.post(
        "/api/auth/login/",
        {"email": worker.user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200


def test_logout_exige_csrf_com_sessao_ativa():
    worker = make_worker()
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    client.post(
        "/api/auth/login/",
        {"email": worker.user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert client.post("/api/auth/logout/").status_code == 403


# --- permissões por papel -------------------------------------------------


@api_view(["GET"])
@permission_classes([IsCompanyUser])
def company_only(request):
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsWorkerUser])
def worker_only(request):
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_only(request):
    return Response({"ok": True})


@pytest.mark.parametrize(
    "view,allowed_role",
    [(company_only, Role.COMPANY), (worker_only, Role.WORKER), (admin_only, Role.ADMIN)],
)
def test_permissao_por_papel(view, allowed_role):
    factory = APIRequestFactory()
    for role in Role:
        user = make_admin() if role == Role.ADMIN else make_user(role)
        request = factory.get("/x/")
        force_authenticate(request, user=user)
        status = view(request).status_code
        assert status == (200 if role == allowed_role else 403), role
        if role == Role.ADMIN:
            user.delete()


def test_papel_exige_autenticacao():
    request = APIRequestFactory().get("/x/")
    assert company_only(request).status_code in (401, 403)


# --- permissões por objeto ------------------------------------------------


def test_notificacao_de_outro_usuario_retorna_403():
    owner = make_worker().user
    intruder = make_worker().user
    notification = notify(owner, "teste", "Olá")
    client = APIClient()
    client.force_login(intruder)

    response = client.post(f"/api/notifications/{notification.pk}/read/")

    assert response.status_code == 403
    notification.refresh_from_db()
    assert notification.read_at is None


def test_objeto_de_outra_empresa_retorna_403():
    company_a, company_b = make_company(), make_company()
    member_a = company_a.members.get().user
    permission = IsObjectOwner()
    request = APIRequestFactory().get("/x/")
    request.user = member_a

    class Obj:
        def __init__(self, company):
            self.company = company

    assert permission.has_object_permission(request, None, Obj(company_a)) is True
    assert permission.has_object_permission(request, None, Obj(company_b)) is False


def test_objeto_de_outro_prestador_retorna_403():
    worker_a, worker_b = make_worker(), make_worker()
    request = APIRequestFactory().get("/x/")
    request.user = worker_a.user

    class Obj:
        def __init__(self, worker):
            self.worker = worker

    assert IsObjectOwner().has_object_permission(request, None, Obj(worker_a)) is True
    assert IsObjectOwner().has_object_permission(request, None, Obj(worker_b)) is False


# --- notificações ---------------------------------------------------------


def test_lista_notificacoes_proprias_com_contador_e_marca_como_lida():
    user = make_worker().user
    other = make_worker().user
    first = notify(user, "a", "Primeira")
    notify(user, "b", "Segunda")
    notify(other, "c", "De outro")
    client = APIClient()
    client.force_login(user)

    data = client.get("/api/notifications/").json()
    assert data["unread_count"] == 2
    assert {n["title"] for n in data["results"]} == {"Primeira", "Segunda"}

    assert client.post(f"/api/notifications/{first.pk}/read/").status_code == 200
    assert client.get("/api/notifications/").json()["unread_count"] == 1

    assert client.post("/api/notifications/read-all/").status_code == 204
    assert client.get("/api/notifications/").json()["unread_count"] == 0
    assert Notification.objects.get(user=other).read_at is None


def test_notificacoes_exigem_autenticacao():
    assert APIClient().get("/api/notifications/").status_code == 403
