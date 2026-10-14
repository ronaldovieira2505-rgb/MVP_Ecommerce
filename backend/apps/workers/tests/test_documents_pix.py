import os

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.core.models import PlatformParameters, StateTransition
from apps.workers.models import Worker, WorkerDocument

pytestmark = pytest.mark.django_db

CPF = "12345678909"
OTHER_CPF = "52998224725"
PASSWORD = "senha-forte-123"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
PDF = b"%PDF-1.4\n" + b"0" * 100


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def make_worker(
    email="joao@example.com", cpf=CPF, status=Worker.VerificationStatus.PENDING_DOCUMENTS
):
    user = get_user_model().objects.create_user(
        username=email, email=email, password=PASSWORD, role=Role.WORKER
    )
    return Worker.objects.create(
        user=user,
        full_name="João da Silva",
        cpf=cpf,
        phone="11999998888",
        birth_date="1990-05-20",
        verification_status=status,
    )


def login(worker):
    client = APIClient()
    client.force_login(worker.user)
    return client


def upload(name, content):
    return SimpleUploadedFile(name, content)


def send_documents(client, **overrides):
    files = {
        "document_front": upload("frente.jpg", JPEG),
        "document_back": upload("verso.pdf", PDF),
        "selfie": upload("selfie.png", PNG),
    }
    files.update(overrides)
    files = {k: v for k, v in files.items() if v is not None}
    return client.post("/api/workers/me/documents/", files, format="multipart")


# ---------- documentos ----------


def test_envio_valido_guarda_em_armazenamento_privado_e_vai_para_em_analise(settings):
    worker = make_worker()

    response = send_documents(login(worker))

    assert response.status_code == 200
    worker.refresh_from_db()
    assert worker.verification_status == "EM_ANALISE"
    assert response.json()["verification_status"] == "EM_ANALISE"
    assert worker.documents.count() == 3
    for document in worker.documents.all():
        assert document.file.path.startswith(str(settings.PRIVATE_MEDIA_ROOT))
        with pytest.raises(ValueError):
            _ = document.file.url
    assert StateTransition.objects.filter(
        entity_type="WorkerVerification", entity_id=worker.pk, to_state="EM_ANALISE"
    ).exists()


def test_reenvio_depois_de_rejeitado_vai_para_em_analise_e_troca_arquivos():
    worker = make_worker(status=Worker.VerificationStatus.REJECTED)
    old = WorkerDocument.objects.create(
        worker=worker, kind="SELFIE", file=upload("velha.png", PNG)
    )
    old_path = old.file.path

    response = send_documents(login(worker))

    assert response.status_code == 200
    worker.refresh_from_db()
    assert worker.verification_status == "EM_ANALISE"
    assert worker.documents.count() == 3
    assert not os.path.exists(old_path)


@pytest.mark.parametrize("status", ["EM_ANALISE", "APROVADO"])
def test_envio_nao_permitido_em_outros_status(status):
    worker = make_worker(status=status)

    response = send_documents(login(worker))

    assert response.status_code == 409
    assert worker.documents.count() == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"document_front": SimpleUploadedFile("frente.gif", b"GIF89a" + b"0" * 50)},
        {"document_back": SimpleUploadedFile("verso.exe", b"MZ" + b"0" * 50)},
        {"selfie": SimpleUploadedFile("selfie.pdf", PDF)},
        # extensão certa, conteúdo errado
        {"document_front": SimpleUploadedFile("frente.jpg", b"nao sou uma imagem")},
        {"selfie": SimpleUploadedFile("selfie.png", b"")},
    ],
)
def test_tipo_invalido_mostra_erro_e_nao_salva_nada(overrides):
    worker = make_worker()

    response = send_documents(login(worker), **overrides)

    assert response.status_code == 400
    assert response.json()["detail"]
    worker.refresh_from_db()
    assert worker.verification_status == "PENDENTE_DOCUMENTOS"
    assert worker.documents.count() == 0


def test_tipo_invalido_traz_mensagem_clara():
    worker = make_worker()

    response = send_documents(
        login(worker), document_front=SimpleUploadedFile("frente.gif", b"GIF89a" + b"0" * 50)
    )

    assert response.json()["detail"] == "Tipo de arquivo inválido. Envie JPG, PNG ou PDF."


def test_arquivo_acima_de_5_mb_e_rejeitado_e_nada_e_salvo():
    worker = make_worker()
    big = SimpleUploadedFile("selfie.jpg", JPEG + b"0" * (5 * 1024 * 1024))

    response = send_documents(login(worker), selfie=big)

    assert response.status_code == 400
    assert response.json()["detail"] == "O arquivo excede o tamanho máximo de 5 MB."
    assert worker.documents.count() == 0
    worker.refresh_from_db()
    assert worker.verification_status == "PENDENTE_DOCUMENTOS"


def test_arquivo_de_exatamente_5_mb_e_aceito():
    worker = make_worker()
    exact = SimpleUploadedFile("selfie.jpg", JPEG + b"0" * (5 * 1024 * 1024 - len(JPEG)))

    assert send_documents(login(worker), selfie=exact).status_code == 200


def test_limite_de_tamanho_vem_de_platform_parameters():
    params = PlatformParameters.get()
    params.document_max_size_mb = 1
    params.save()
    worker = make_worker()
    two_mb = SimpleUploadedFile("selfie.jpg", JPEG + b"0" * (2 * 1024 * 1024))

    response = send_documents(login(worker), selfie=two_mb)

    assert response.status_code == 400
    assert "1 MB" in response.json()["detail"]


@pytest.mark.parametrize("missing", ["document_front", "document_back", "selfie"])
def test_exige_frente_verso_e_selfie(missing):
    worker = make_worker()

    response = send_documents(login(worker), **{missing: None})

    assert response.status_code == 400
    assert response.json()["detail"] == "Envie documento (frente e verso) e selfie."
    assert worker.documents.count() == 0


def test_envio_exige_login_de_prestador():
    assert send_documents(APIClient()).status_code == 403
    company_user = get_user_model().objects.create_user(
        username="c@example.com", email="c@example.com", password=PASSWORD, role=Role.COMPANY
    )
    client = APIClient()
    client.force_login(company_user)
    assert send_documents(client).status_code == 403


# ---------- acesso aos arquivos ----------


def sent_worker():
    worker = make_worker()
    assert send_documents(login(worker)).status_code == 200
    return worker


def file_url(worker, kind="SELFIE"):
    return f"/api/workers/{worker.pk}/documents/{kind}/"


def test_dono_acessa_o_proprio_arquivo():
    worker = sent_worker()

    response = login(worker).get(file_url(worker))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PNG
    assert "no-store" in response["Cache-Control"]


def test_admin_acessa_o_arquivo():
    worker = sent_worker()
    admin = get_user_model().objects.create_user(
        username="a@example.com", email="a@example.com", password=PASSWORD,
        role=Role.ADMIN, is_staff=True,
    )
    client = APIClient()
    client.force_login(admin)

    assert client.get(file_url(worker)).status_code == 200


def test_outro_prestador_nao_acessa_o_arquivo():
    worker = sent_worker()
    other = make_worker(email="outro@example.com", cpf=OTHER_CPF)

    assert login(other).get(file_url(worker)).status_code == 404


def test_empresa_e_anonimo_nao_acessam_o_arquivo():
    worker = sent_worker()
    company_user = get_user_model().objects.create_user(
        username="c@example.com", email="c@example.com", password=PASSWORD, role=Role.COMPANY
    )
    client = APIClient()
    client.force_login(company_user)

    assert client.get(file_url(worker)).status_code == 404
    assert APIClient().get(file_url(worker)).status_code in (401, 403)


def test_resposta_do_perfil_nao_expoe_caminho_nem_url_dos_arquivos():
    worker = sent_worker()

    body = login(worker).get("/api/workers/me/").content.decode()

    assert "worker_documents" not in body
    assert "private" not in body


# ---------- chave PIX ----------


def put_pix(client, **data):
    return client.put("/api/workers/me/pix/", data, format="json")


@pytest.mark.parametrize(
    ("key_type", "key", "stored", "masked"),
    [
        ("CPF", "123.456.789-09", CPF, "***.456.789-**"),
        ("EMAIL", "Joao@Example.com", "joao@example.com", "j***@example.com"),
        ("TELEFONE", "(11) 99999-8888", "11999998888", "****8888"),
        ("TELEFONE", "+5511999998888", "11999998888", "****8888"),
        (
            "ALEATORIA",
            "123E4567-E89B-12D3-A456-426614174000",
            "123e4567-e89b-12d3-a456-426614174000",
            "****4000",
        ),
    ],
)
def test_chave_valida_e_salva_e_exibida_mascarada(key_type, key, stored, masked):
    worker = make_worker()

    response = put_pix(login(worker), key_type=key_type, key=key)

    assert response.status_code == 200
    body = response.json()
    assert body["pix_key_type"] == key_type
    assert body["pix_key"] == masked
    assert stored not in response.content.decode()
    worker.refresh_from_db()
    assert worker.pix_key == stored
    assert worker.pix_key_type == key_type


@pytest.mark.parametrize(
    ("key_type", "key"),
    [
        ("CPF", "12345678900"),
        ("EMAIL", "nao-e-email"),
        ("TELEFONE", "123"),
        ("TELEFONE", "0111999998888"),
        ("ALEATORIA", "abc"),
        ("CHAVE", "x"),
        ("EMAIL", ""),
    ],
)
def test_formato_invalido_para_o_tipo_e_rejeitado(key_type, key):
    worker = make_worker()

    response = put_pix(login(worker), key_type=key_type, key=key)

    assert response.status_code == 400
    worker.refresh_from_db()
    assert worker.pix_key == ""


def test_cpf_diferente_do_cadastrado_viola_titularidade():
    worker = make_worker()

    response = put_pix(login(worker), key_type="CPF", key=OTHER_CPF)

    assert response.status_code == 400
    assert response.json()["detail"] == "A chave PIX do tipo CPF precisa ser o seu próprio CPF"
    worker.refresh_from_db()
    assert worker.pix_key == ""


def test_primeiro_cadastro_nao_exige_senha_e_gera_auditoria():
    worker = make_worker()

    put_pix(login(worker), key_type="EMAIL", key="joao@example.com")

    audit = StateTransition.objects.get(entity_type="WorkerPixKey", entity_id=worker.pk)
    assert audit.actor == worker.user
    assert audit.from_state == ""
    assert audit.to_state == "j***@example.com"


def test_troca_exige_a_senha_atual():
    worker = make_worker()
    client = login(worker)
    put_pix(client, key_type="EMAIL", key="joao@example.com")

    sem_senha = put_pix(client, key_type="TELEFONE", key="11999998888")
    errada = put_pix(client, key_type="TELEFONE", key="11999998888", current_password="errada")

    assert sem_senha.status_code == 403
    assert errada.status_code == 403
    assert errada.json()["detail"] == "Senha atual incorreta"
    worker.refresh_from_db()
    assert worker.pix_key == "joao@example.com"
    assert StateTransition.objects.filter(entity_type="WorkerPixKey").count() == 1


def test_troca_com_senha_correta_salva_e_registra_auditoria_sem_chave_em_claro():
    worker = make_worker()
    client = login(worker)
    put_pix(client, key_type="EMAIL", key="joao@example.com")

    response = put_pix(
        client, key_type="TELEFONE", key="11999998888", current_password=PASSWORD
    )

    assert response.status_code == 200
    worker.refresh_from_db()
    assert worker.pix_key == "11999998888"
    trail = StateTransition.objects.filter(entity_type="WorkerPixKey", entity_id=worker.pk)
    audits = list(trail.order_by("id"))
    assert len(audits) == 2
    assert audits[1].from_state == "j***@example.com"
    assert audits[1].to_state == "****8888"
    assert audits[1].reason == "Chave PIX trocada"
    assert "joao@example.com" not in "".join(a.from_state + a.to_state + a.reason for a in audits)


def test_pix_exige_login_de_prestador():
    assert put_pix(APIClient(), key_type="EMAIL", key="a@b.com").status_code == 403


# ---------- painel ----------


def test_painel_mostra_as_duas_etapas_concluidas_e_aguardando_verificacao():
    worker = make_worker()
    client = login(worker)
    send_documents(client)
    put_pix(client, key_type="CPF", key=CPF)

    body = client.get("/api/workers/me/").json()

    assert [step["done"] for step in body["profile_steps"]] == [True, True]
    assert body["verification_status"] == "EM_ANALISE"
    assert body["verification_message"] == "Aguardando verificação"
    assert body["pix_key"] == "***.456.789-**"
    assert all(d["uploaded"] for d in body["documents"])


def test_painel_sem_pix_nao_mostra_aguardando_verificacao():
    worker = make_worker()
    client = login(worker)
    send_documents(client)

    body = client.get("/api/workers/me/").json()

    assert [step["done"] for step in body["profile_steps"]] == [True, False]
    assert body["verification_message"] == ""
