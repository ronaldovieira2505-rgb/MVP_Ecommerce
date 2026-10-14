"""Verificação do prestador e suspensão automática."""

import os
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters, StateTransition, VerificationReview
from apps.core.notifications import notify
from apps.core.state_machine import transition
from apps.core.validators import is_valid_cpf
from apps.workers.models import Worker, WorkerDocument
from apps.workers.state_machine import WORKER_VERIFICATION_MACHINE

S = Worker.VerificationStatus

CPF_ALREADY_REGISTERED = "Já existe uma conta para este CPF"
EMAIL_ALREADY_REGISTERED = "Já existe uma conta com este e-mail"


class CpfAlreadyRegistered(DomainError):
    pass


class EmailAlreadyRegistered(DomainError):
    pass


def register_worker(*, full_name, cpf, phone, birth_date, email, password):
    """Cria User (WORKER) e Worker em `PENDENTE_DOCUMENTOS`. Documentos e PIX vêm na US05."""
    User = get_user_model()
    if Worker.objects.filter(cpf=cpf).exists():
        raise CpfAlreadyRegistered(CPF_ALREADY_REGISTERED)
    if User.objects.filter(email__iexact=email).exists():
        raise EmailAlreadyRegistered(EMAIL_ALREADY_REGISTERED)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=full_name[:150],
                role=Role.WORKER,
            )
            return Worker.objects.create(
                user=user,
                full_name=full_name,
                cpf=cpf,
                phone=phone,
                birth_date=birth_date,
                verification_status=S.PENDING_DOCUMENTS,
            )
    except IntegrityError as error:  # corrida: outro cadastro com o mesmo CPF/e-mail
        if Worker.objects.filter(cpf=cpf).exists():
            raise CpfAlreadyRegistered(CPF_ALREADY_REGISTERED) from error
        raise EmailAlreadyRegistered(EMAIL_ALREADY_REGISTERED) from error


def profile_steps(worker):
    """Passo a passo "Complete seu perfil" com o status de cada etapa."""
    documents_done = worker.verification_status in (S.IN_REVIEW, S.APPROVED)
    return [
        {
            "key": "documentos",
            "label": "Documentos e selfie",
            "done": documents_done,
            "status": worker.verification_status,
        },
        {"key": "pix", "label": "Chave PIX", "done": bool(worker.pix_key)},
    ]


@transaction.atomic
def submit_documents(worker, *, actor=None, now=None):
    """PENDENTE_DOCUMENTOS → EM_ANALISE (ou REJEITADO → EM_ANALISE no reenvio)."""
    WORKER_VERIFICATION_MACHINE.validate(worker.verification_status, S.IN_REVIEW)
    sent = set(worker.documents.values_list("kind", flat=True))
    if sent != {k.value for k in WorkerDocument.Kind}:
        raise DomainError("Envie documento (frente e verso) e selfie.")
    return transition(
        worker,
        WORKER_VERIFICATION_MACHINE,
        S.IN_REVIEW,
        actor=actor,
        reason="Documentos enviados",
        now=now,
    )


DOCUMENT_ERROR_TYPE = "Tipo de arquivo inválido. Envie JPG, PNG ou PDF."
SELFIE_ERROR_TYPE = "Tipo de arquivo inválido. A selfie deve ser JPG ou PNG."
DOCUMENT_ERROR_EMPTY = "O arquivo está vazio."
DOCUMENTS_NOT_ALLOWED = "O envio de documentos não está disponível no seu status atual."
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PDF_MAGIC = b"%PDF-"
# extensão aceita → assinatura esperada no início do arquivo
ALLOWED_SIGNATURES = {
    ".jpg": JPEG_MAGIC,
    ".jpeg": JPEG_MAGIC,
    ".png": PNG_MAGIC,
    ".pdf": PDF_MAGIC,
}


def validate_document_file(kind, uploaded, *, max_bytes):
    """Valida tipo (extensão + assinatura) e tamanho. Lança `DomainError` com a mensagem."""
    is_selfie = kind == WorkerDocument.Kind.SELFIE
    type_error = SELFIE_ERROR_TYPE if is_selfie else DOCUMENT_ERROR_TYPE
    extension = os.path.splitext(uploaded.name or "")[1].lower()
    signature = ALLOWED_SIGNATURES.get(extension)
    if signature is None or (is_selfie and extension == ".pdf"):
        raise DomainError(type_error)
    if uploaded.size == 0:
        raise DomainError(DOCUMENT_ERROR_EMPTY)
    if uploaded.size > max_bytes:
        raise DomainError(f"O arquivo excede o tamanho máximo de {max_bytes // (1024 * 1024)} MB.")
    uploaded.seek(0)
    head = uploaded.read(len(signature))
    uploaded.seek(0)
    if head != signature:
        raise DomainError(type_error)


def upload_documents(worker, *, files, actor=None, now=None):
    """Recebe `{Kind: arquivo}` com os três itens, valida tudo e só então grava.

    Em `PENDENTE_DOCUMENTOS` ou `REJEITADO`; no reenvio os arquivos antigos são apagados.
    Qualquer erro de validação não salva nada e não muda o status.
    """
    if worker.verification_status not in (S.PENDING_DOCUMENTS, S.REJECTED):
        raise DocumentsNotAllowed(DOCUMENTS_NOT_ALLOWED)
    missing = [k for k in WorkerDocument.Kind if k not in files]
    if missing:
        raise DomainError("Envie documento (frente e verso) e selfie.")
    max_bytes = PlatformParameters.get().document_max_size_mb * 1024 * 1024
    for kind in WorkerDocument.Kind:
        validate_document_file(kind, files[kind], max_bytes=max_bytes)

    old_files = []
    with transaction.atomic():
        locked = Worker.objects.select_for_update().get(pk=worker.pk)
        if locked.verification_status not in (S.PENDING_DOCUMENTS, S.REJECTED):
            raise DocumentsNotAllowed(DOCUMENTS_NOT_ALLOWED)
        for old in locked.documents.all():
            old_files.append(old.file)
        locked.documents.all().delete()
        for kind in WorkerDocument.Kind:
            WorkerDocument.objects.create(worker=locked, kind=kind, file=files[kind])
        worker = submit_documents(locked, actor=actor, now=now)
    for stored in old_files:
        stored.delete(save=False)
    return worker


class DocumentsNotAllowed(DomainError):
    pass


class InvalidPixKey(DomainError):
    pass


class WrongPassword(DomainError):
    pass


PIX_CPF_MISMATCH = "A chave PIX do tipo CPF precisa ser o seu próprio CPF"
PIX_INVALID = {
    Worker.PixKeyType.CPF: "CPF inválido",
    Worker.PixKeyType.EMAIL: "E-mail inválido",
    Worker.PixKeyType.PHONE: "Telefone inválido. Informe DDD e número.",
    Worker.PixKeyType.RANDOM: "Chave aleatória inválida",
}


def normalize_pix_key(worker, key_type, key):
    """Valida o formato da chave para o tipo e devolve a forma normalizada."""
    P = Worker.PixKeyType
    key = str(key).strip()
    if key_type == P.CPF:
        digits = "".join(c for c in key if c.isdigit())
        if not is_valid_cpf(digits):
            raise InvalidPixKey(PIX_INVALID[P.CPF])
        if digits != worker.cpf:
            raise InvalidPixKey(PIX_CPF_MISMATCH)
        return digits
    if key_type == P.EMAIL:
        try:
            validate_email(key)
        except DjangoValidationError as error:
            raise InvalidPixKey(PIX_INVALID[P.EMAIL]) from error
        return key.lower()
    if key_type == P.PHONE:
        digits = "".join(c for c in key if c.isdigit())
        if len(digits) in (12, 13) and digits.startswith("55"):
            digits = digits[2:]
        if len(digits) not in (10, 11) or digits[0] == "0":
            raise InvalidPixKey(PIX_INVALID[P.PHONE])
        return digits
    if key_type == P.RANDOM:
        try:
            parsed = uuid.UUID(key)
        except ValueError as error:
            raise InvalidPixKey(PIX_INVALID[P.RANDOM]) from error
        return str(parsed)
    raise InvalidPixKey("Tipo de chave PIX inválido")


@transaction.atomic
def set_pix_key(worker, *, key_type, key, current_password="", actor=None, now=None):
    """Cadastra ou troca a chave PIX. A troca exige a senha atual e gera auditoria."""
    locked = Worker.objects.select_for_update().get(pk=worker.pk)
    normalized = normalize_pix_key(locked, key_type, key)
    replacing = bool(locked.pix_key)
    if replacing and not locked.user.check_password(current_password or ""):
        raise WrongPassword("Senha atual incorreta")
    before = locked.masked_pix_key
    locked.pix_key_type = key_type
    locked.pix_key = normalized
    locked.save(update_fields=["pix_key_type", "pix_key"])
    StateTransition.objects.create(
        entity_type="WorkerPixKey",
        entity_id=locked.pk,
        from_state=before,
        to_state=locked.masked_pix_key,
        actor=actor,
        reason="Chave PIX trocada" if replacing else "Chave PIX cadastrada",
        created_at=now or timezone.now(),
    )
    worker.refresh_from_db()
    return worker


@transaction.atomic
def review_worker(worker, *, reviewer, approve, reason="", now=None):
    if not approve and not reason.strip():
        raise DomainError("O motivo é obrigatório na rejeição.")
    decision = (
        VerificationReview.Decision.APPROVED if approve else VerificationReview.Decision.REJECTED
    )
    worker = transition(
        worker,
        WORKER_VERIFICATION_MACHINE,
        S.APPROVED if approve else S.REJECTED,
        actor=reviewer,
        reason=reason,
        now=now,
    )
    VerificationReview.objects.create(
        subject_type=VerificationReview.SubjectType.WORKER,
        subject_id=worker.pk,
        reviewer=reviewer,
        decision=decision,
        reason=reason,
        created_at=now or timezone.now(),
    )
    notify(
        worker.user,
        "VERIFICACAO",
        "Cadastro aprovado" if approve else "Cadastro rejeitado",
        reason,
    )
    return worker


@transaction.atomic
def apply_automatic_suspension(worker, *, now=None):
    """≥ N faltas na janela: suspende o prestador. Devolve True se suspendeu agora."""
    now = now or timezone.now()
    params = PlatformParameters.get()
    worker = Worker.objects.select_for_update().get(pk=worker.pk)
    if worker.is_suspended(now):
        return False
    since = now - timedelta(days=params.no_show_window_days)
    no_shows = StateTransition.objects.filter(
        entity_type="Assignment",
        to_state="FALTA",
        created_at__gte=since,
        entity_id__in=worker.assignments.values("pk"),
    ).count()
    if no_shows < params.no_show_limit:
        return False
    worker.suspended_until = now + timedelta(days=params.suspension_days)
    worker.save(update_fields=["suspended_until"])
    StateTransition.objects.create(
        entity_type="WorkerSuspension",
        entity_id=worker.pk,
        from_state="ATIVO",
        to_state="SUSPENSO",
        reason=f"{no_shows} faltas em {params.no_show_window_days} dias",
        created_at=now,
    )
    notify(
        worker.user,
        "SUSPENSAO",
        "Conta suspensa",
        f"Suspensa até {worker.suspended_until:%d/%m/%Y} por faltas.",
    )
    return True
