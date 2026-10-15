from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.companies.models import Company
from apps.core.exceptions import DomainError
from apps.core.models import Notification, StateTransition, VerificationReview
from apps.core.tests.factories import (
    NOW,
    make_admin,
    make_company,
    make_published_vacancy,
    make_user,
    make_worker,
)
from apps.vacancies import application_services as applications
from apps.workers.models import Worker, WorkerDocument

pytestmark = pytest.mark.django_db

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 50


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


@pytest.fixture
def admin_client(client):
    client.force_login(make_admin())
    return client


def pending_company():
    return make_company(approved=False)


def in_review_worker():
    worker = make_worker(approved=False)
    worker.verification_status = Worker.VerificationStatus.IN_REVIEW
    worker.save()
    for kind in WorkerDocument.Kind:
        WorkerDocument.objects.create(
            worker=worker, kind=kind, file=SimpleUploadedFile(f"{kind}.jpg", JPEG)
        )
    return worker


def detail_url(slug, pk):
    return reverse("admin:verification_queue_detail", args=[slug, pk])


def test_queue_lists_pending_in_arrival_order(admin_client):
    newer_worker = in_review_worker()
    older_company = pending_company()
    approved = make_company(approved=True)
    pending_docs = make_worker(approved=False)  # PENDENTE_DOCUMENTOS não entra
    Company.objects.filter(pk=older_company.pk).update(created_at=NOW - timedelta(days=2))
    Worker.objects.filter(pk=newer_worker.pk).update(created_at=NOW - timedelta(days=1))

    response = admin_client.get(reverse("admin:verification_queue"))

    assert response.status_code == 200
    items = response.context["items"]
    assert [(i.slug, i.pk) for i in items] == [
        ("empresa", older_company.pk),
        ("prestador", newer_worker.pk),
    ]
    html = response.content.decode()
    assert "Contratante" in html and "Prestador" in html
    assert str(older_company) in html and newer_worker.full_name in html
    assert str(approved) not in html and pending_docs.full_name not in html


def test_resubmission_goes_to_the_end_of_the_queue(admin_client):
    first = in_review_worker()
    second = in_review_worker()
    StateTransition.objects.create(
        entity_type="WorkerVerification",
        entity_id=first.pk,
        from_state="REJEITADO",
        to_state="EM_ANALISE",
        created_at=NOW + timedelta(days=1),
    )
    Worker.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=NOW - timedelta(days=3))

    items = admin_client.get(reverse("admin:verification_queue")).context["items"]

    assert [i.pk for i in items] == [second.pk, first.pk]


def test_queue_requires_staff(client):
    assert client.get(reverse("admin:verification_queue")).status_code == 302
    client.force_login(make_user())
    assert client.get(reverse("admin:verification_queue")).status_code == 302


def test_queue_link_is_shown_in_review_changelist(admin_client):
    response = admin_client.get(reverse("admin:core_verificationreview_changelist"))
    assert "Fila de verificação" in response.content.decode()


def test_worker_detail_shows_data_documents_and_masked_pix(admin_client):
    worker = in_review_worker()
    worker.pix_key_type, worker.pix_key = "CPF", "52998224725"
    worker.save()

    response = admin_client.get(detail_url("prestador", worker.pk))

    html = response.content.decode()
    assert response.status_code == 200
    assert worker.full_name in html
    assert "52998224725" not in html and worker.cpf not in html
    assert worker.masked_pix_key in html and worker.masked_cpf in html
    for kind in WorkerDocument.Kind:
        assert reverse("worker-document-file", args=[worker.pk, kind.value]) in html
    # as imagens abrem para o admin pela rota protegida
    url = reverse("worker-document-file", args=[worker.pk, WorkerDocument.Kind.SELFIE.value])
    assert admin_client.get(url).status_code == 200


def test_company_detail_compares_with_brasilapi(admin_client, fake_cnpj_lookup):
    company = pending_company()
    company.trade_name = "Nome diferente"
    company.save()

    response = admin_client.get(detail_url("empresa", company.pk))

    html = response.content.decode()
    assert response.status_code == 200
    assert (company.cnpj, 5) in fake_cnpj_lookup.calls
    assert company.legal_name in html
    assert "Empresa Simulada" in html  # dado retornado pela BrasilAPI
    assert "differs" in html
    assert "Dados não conferidos" not in html


def test_company_detail_highlights_unverified_data(admin_client, fake_cnpj_lookup):
    company = pending_company()
    company.data_unverified = True
    company.save()
    fake_cnpj_lookup.fail = True

    html = admin_client.get(detail_url("empresa", company.pk)).content.decode()

    assert "Dados não conferidos" in html
    assert "Não foi possível consultar a BrasilAPI" in html


def test_approve_company_records_review_and_notifies(admin_client):
    company = pending_company()

    response = admin_client.post(detail_url("empresa", company.pk), {"action": "approve"})

    assert response.status_code == 302
    company.refresh_from_db()
    assert company.verification_status == Company.VerificationStatus.APPROVED
    review = VerificationReview.objects.get()
    assert (review.subject_type, review.subject_id, review.decision) == (
        "COMPANY",
        company.pk,
        "APROVADO",
    )
    assert review.reviewer.is_superuser
    note = Notification.objects.get(user=company.members.get().user)
    assert note.title == "Cadastro aprovado"
    assert StateTransition.objects.filter(
        entity_type="CompanyVerification", entity_id=company.pk, to_state="APROVADA"
    ).exists()


def test_approve_worker_records_review_and_notifies(admin_client):
    worker = in_review_worker()

    admin_client.post(detail_url("prestador", worker.pk), {"action": "approve"})

    worker.refresh_from_db()
    assert worker.verification_status == Worker.VerificationStatus.APPROVED
    assert VerificationReview.objects.get().decision == "APROVADO"
    assert Notification.objects.get(user=worker.user).title == "Cadastro aprovado"


@pytest.mark.parametrize("slug", ["empresa", "prestador"])
def test_reject_requires_reason(admin_client, slug):
    subject = pending_company() if slug == "empresa" else in_review_worker()
    status_before = subject.verification_status

    response = admin_client.post(
        detail_url(slug, subject.pk), {"action": "reject", "reason": "  "}, follow=True
    )

    assert "O motivo é obrigatório na rejeição." in response.content.decode()
    subject.refresh_from_db()
    assert subject.verification_status == status_before
    assert not VerificationReview.objects.exists()
    assert not Notification.objects.exists()


def test_reject_company_notifies_with_reason(admin_client):
    company = pending_company()

    admin_client.post(
        detail_url("empresa", company.pk), {"action": "reject", "reason": "CNPJ divergente"}
    )

    company.refresh_from_db()
    assert company.verification_status == Company.VerificationStatus.REJECTED
    review = VerificationReview.objects.get()
    assert (review.decision, review.reason) == ("REJEITADO", "CNPJ divergente")
    note = Notification.objects.get(user=company.members.get().user)
    assert (note.title, note.message) == ("Cadastro rejeitado", "CNPJ divergente")


def test_reject_worker_allows_resubmission(admin_client):
    worker = in_review_worker()

    admin_client.post(
        detail_url("prestador", worker.pk), {"action": "reject", "reason": "Selfie ilegível"}
    )

    worker.refresh_from_db()
    assert worker.verification_status == Worker.VerificationStatus.REJECTED
    note = Notification.objects.get(user=worker.user)
    assert (note.title, note.message) == ("Cadastro rejeitado", "Selfie ilegível")
    from apps.workers.services import submit_documents

    submit_documents(worker)
    worker.refresh_from_db()
    assert worker.verification_status == Worker.VerificationStatus.IN_REVIEW


def test_cannot_decide_twice(admin_client):
    company = pending_company()
    admin_client.post(detail_url("empresa", company.pk), {"action": "approve"})

    admin_client.post(detail_url("empresa", company.pk), {"action": "reject", "reason": "x"})

    company.refresh_from_db()
    assert company.verification_status == Company.VerificationStatus.APPROVED
    assert VerificationReview.objects.count() == 1


def test_invalid_action_and_unknown_kind(admin_client):
    company = pending_company()
    assert admin_client.post(detail_url("empresa", company.pk), {"action": "x"}).status_code == 400
    assert admin_client.get(detail_url("outro", 1)).status_code == 404
    assert admin_client.get(detail_url("empresa", 9999)).status_code == 404


def test_approved_company_can_publish_vacancies(admin_client):
    company = pending_company()
    with pytest.raises(DomainError):
        make_published_vacancy(company=company)

    admin_client.post(detail_url("empresa", company.pk), {"action": "approve"})

    company.refresh_from_db()
    vacancy = make_published_vacancy(company=company)
    assert vacancy.status == "PUBLICADA"


def test_approved_worker_with_pix_can_apply(admin_client):
    vacancy = make_published_vacancy()
    worker = in_review_worker()
    worker.pix_key_type, worker.pix_key = "ALEATORIA", "pix-abcdef-1234"
    worker.save()
    with pytest.raises(DomainError):
        applications.apply_to_vacancy(vacancy, worker, now=NOW)

    admin_client.post(detail_url("prestador", worker.pk), {"action": "approve"})

    worker.refresh_from_db()
    assert applications.apply_to_vacancy(vacancy, worker, now=NOW).status == "PENDENTE"
