"""Serviço de domínio da Vaga. Toda mudança de `status` passa por `transition()`."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.notifications import notify, notify_company
from apps.core.state_machine import record_creation, transition
from apps.payments import services as payments
from apps.vacancies.models import Application, Assignment, Vacancy, VacancyChange
from apps.vacancies.state_machine import (
    APPLICATION_MACHINE,
    ASSIGNMENT_MACHINE,
    VACANCY_MACHINE,
)

V = Vacancy.Status


def _check_lead_time(vacancy_starts_at, now, params):
    if vacancy_starts_at < now + timedelta(minutes=params.min_publish_lead_minutes):
        raise DomainError(
            "O turno deve começar com ao menos "
            f"{params.min_publish_lead_minutes} min de antecedência."
        )


@transaction.atomic
def create_vacancy(*, company, actor=None, now=None, **fields):
    """Cria a vaga em AGUARDANDO_PAGAMENTO, com a custódia PENDENTE."""
    now = now or timezone.now()
    params = PlatformParameters.get()
    if company.verification_status != Company.VerificationStatus.APPROVED:
        raise DomainError("Só empresas aprovadas podem criar vagas.")
    if fields["ends_at"] <= fields["starts_at"]:
        raise DomainError("O fim do turno deve ser depois do início.")
    _check_lead_time(fields["starts_at"], now, params)
    vacancy = Vacancy.objects.create(
        company=company, status=V.AWAITING_PAYMENT, created_at=now, **fields
    )
    record_creation(vacancy, VACANCY_MACHINE, actor=actor, reason="Vaga criada", now=now)
    payments.open_custody(vacancy, actor=actor, now=now)
    return vacancy


@transaction.atomic
def pay_vacancy(vacancy, *, actor=None, now=None):
    """Empresa paga (PSP simulado): custódia RETIDA e vaga PUBLICADA."""
    now = now or timezone.now()
    VACANCY_MACHINE.validate(vacancy.status, V.PUBLISHED)
    _check_lead_time(vacancy.starts_at, now, PlatformParameters.get())
    payments.retain(vacancy.custody, actor=actor, now=now)
    return transition(
        vacancy, VACANCY_MACHINE, V.PUBLISHED, actor=actor, reason="Pagamento confirmado", now=now
    )


@transaction.atomic
def cancel_unpaid_vacancy(vacancy, *, actor=None, reason="Empresa desistiu", now=None):
    """AGUARDANDO_PAGAMENTO → CANCELADA (desistência ou prazo); nada foi cobrado."""
    VACANCY_MACHINE.validate(vacancy.status, V.CANCELLED)
    payments.cancel_pending(vacancy.custody, actor=actor, reason=reason, now=now)
    return transition(vacancy, VACANCY_MACHINE, V.CANCELLED, actor=actor, reason=reason, now=now)


def expire_pending_applications(vacancy, *, reason, now=None):
    pending = vacancy.applications.filter(status=Application.Status.PENDING)
    for application in pending:
        transition(
            application,
            APPLICATION_MACHINE,
            Application.Status.EXPIRED,
            reason=reason,
            now=now,
        )


class VacancyLockedError(DomainError):
    """Vaga com prestador aprovado: não pode ser editada nem removida."""


LOCKED_MESSAGE = "Não é possível alterar: já há prestador aprovado"
EDITABLE_FIELDS = (
    "title",
    "description",
    "category",
    "street",
    "number",
    "complement",
    "district",
    "city",
    "state",
    "zip_code",
    "latitude",
    "longitude",
    "starts_at",
    "ends_at",
)


def _ensure_changeable(vacancy):
    """Só PUBLICADA e sem alocação (aprovada) pode ser editada ou removida."""
    if vacancy.assignments.exists():
        raise VacancyLockedError(LOCKED_MESSAGE)
    if vacancy.status != V.PUBLISHED:
        raise DomainError("Só é possível alterar uma vaga publicada.")


@transaction.atomic
def edit_vacancy(vacancy, *, actor=None, now=None, **fields):
    """Edita campos permitidos da vaga PUBLICADA sem aprovados e audita cada mudança.

    Valor por pessoa e número de pessoas não são editáveis após o pagamento.
    """
    now = now or timezone.now()
    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise DomainError("Valor e número de pessoas não podem ser alterados após o pagamento.")
    _ensure_changeable(vacancy)
    changes = []
    for name, new in fields.items():
        old = getattr(vacancy, name)
        if old != new:
            changes.append((name, old, new))
    if not changes:
        return vacancy
    params = PlatformParameters.get()
    starts_at = fields.get("starts_at", vacancy.starts_at)
    ends_at = fields.get("ends_at", vacancy.ends_at)
    if ends_at <= starts_at:
        raise DomainError("O fim do turno deve ser depois do início.")
    if "starts_at" in fields and starts_at != vacancy.starts_at:
        _check_lead_time(starts_at, now, params)
    for name, _old, new in changes:
        setattr(vacancy, name, new)
    vacancy.save(update_fields=[name for name, _o, _n in changes])
    VacancyChange.objects.bulk_create(
        VacancyChange(
            vacancy=vacancy,
            user=actor,
            changed_at=now,
            field=name,
            old_value="" if old is None else str(old),
            new_value="" if new is None else str(new),
        )
        for name, old, new in changes
    )
    return vacancy


@transaction.atomic
def remove_vacancy(vacancy, *, actor=None, now=None):
    """PUBLICADA → CANCELADA, só sem candidatura aprovada. Estorno total."""
    if vacancy.assignments.exists():
        raise VacancyLockedError(LOCKED_MESSAGE)
    VACANCY_MACHINE.validate(vacancy.status, V.CANCELLED)
    if vacancy.status != V.PUBLISHED:
        raise DomainError("Só é possível remover uma vaga publicada.")
    reason = "Vaga removida pela empresa"
    pending = list(
        vacancy.applications.filter(status=Application.Status.PENDING).select_related(
            "worker__user"
        )
    )
    vacancy = transition(vacancy, VACANCY_MACHINE, V.CANCELLED, actor=actor, reason=reason, now=now)
    expire_pending_applications(vacancy, reason=reason, now=now)
    payments.close(vacancy.custody, actor=actor, reason=reason, now=now)
    for application in pending:
        notify(
            application.worker.user,
            "VAGA_REMOVIDA",
            "Vaga removida",
            f"A vaga “{vacancy.title}” foi removida pela empresa e sua candidatura expirou.",
        )
    return vacancy


@transaction.atomic
def close_applications(vacancy, *, now=None):
    return transition(
        vacancy,
        VACANCY_MACHINE,
        V.APPLICATIONS_CLOSED,
        reason="Prazo de candidaturas encerrado",
        now=now,
    )


@transaction.atomic
def start_vacancy(vacancy, *, now=None):
    VACANCY_MACHINE.validate(vacancy.status, V.IN_PROGRESS)
    if not vacancy.assignments.filter(status__in=Assignment.ACTIVE_STATUSES).exists():
        raise DomainError("A vaga não tem alocações para iniciar.")
    return transition(
        vacancy, VACANCY_MACHINE, V.IN_PROGRESS, reason="Horário de início do turno", now=now
    )


@transaction.atomic
def cancel_vacancy_without_assignments(vacancy, *, now=None):
    """Chegou o início e ninguém foi aprovado: estorno total e aviso à empresa."""
    reason = "Ninguém foi aprovado até o início do turno"
    vacancy = transition(vacancy, VACANCY_MACHINE, V.CANCELLED, reason=reason, now=now)
    expire_pending_applications(vacancy, reason=reason, now=now)
    payments.close(vacancy.custody, reason=reason, now=now)
    notify_company(
        vacancy.company,
        "VAGA_CANCELADA",
        "Vaga cancelada",
        f"Ninguém foi aprovado para “{vacancy.title}”. O valor foi estornado.",
    )
    return vacancy


def can_finalize(vacancy, now):
    if vacancy.reopened and now < vacancy.ends_at:
        return False  # ainda aceita candidaturas para a posição liberada
    return not any(
        not ASSIGNMENT_MACHINE.is_final(status)
        for status in vacancy.assignments.values_list("status", flat=True)
    )


@transaction.atomic
def finalize_vacancy(vacancy, *, now=None):
    """EM_ANDAMENTO → FINALIZADA quando todas as alocações estão em estado final."""
    now = now or timezone.now()
    VACANCY_MACHINE.validate(vacancy.status, V.FINISHED)
    if not can_finalize(vacancy, now):
        raise DomainError("Ainda há alocações em andamento nesta vaga.")
    reason = "Todas as alocações em estado final"
    vacancy = transition(vacancy, VACANCY_MACHINE, V.FINISHED, reason=reason, now=now)
    expire_pending_applications(vacancy, reason=reason, now=now)
    payments.close(vacancy.custody, reason=reason, now=now)
    return vacancy
