"""Serviço de domínio da Vaga. Toda mudança de `status` passa por `transition()`."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.notifications import notify_company
from apps.core.state_machine import record_creation, transition
from apps.payments import services as payments
from apps.vacancies.models import Application, Assignment, Vacancy
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


@transaction.atomic
def remove_vacancy(vacancy, *, actor=None, now=None):
    """PUBLICADA → CANCELADA, só sem candidatura aprovada. Estorno total."""
    VACANCY_MACHINE.validate(vacancy.status, V.CANCELLED)
    if vacancy.assignments.exists():
        raise DomainError("Não é possível remover uma vaga com candidatura aprovada.")
    reason = "Vaga removida pela empresa"
    vacancy = transition(vacancy, VACANCY_MACHINE, V.CANCELLED, actor=actor, reason=reason, now=now)
    expire_pending_applications(vacancy, reason=reason, now=now)
    payments.close(vacancy.custody, actor=actor, reason=reason, now=now)
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
