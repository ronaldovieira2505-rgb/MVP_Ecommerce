"""Verificação do prestador e suspensão automática."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters, StateTransition, VerificationReview
from apps.core.notifications import notify
from apps.core.state_machine import transition
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
