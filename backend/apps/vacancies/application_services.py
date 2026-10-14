"""Serviço de domínio da Candidatura e criação da Alocação."""

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.notifications import notify
from apps.core.state_machine import record_creation, transition
from apps.vacancies.models import Application, Assignment, Vacancy
from apps.vacancies.state_machine import APPLICATION_MACHINE, ASSIGNMENT_MACHINE
from apps.workers.models import Worker

A = Application.Status


def _has_overlap(worker, vacancy):
    return (
        Assignment.objects.filter(worker=worker, status__in=Assignment.ACTIVE_STATUSES)
        .filter(vacancy__starts_at__lt=vacancy.ends_at, vacancy__ends_at__gt=vacancy.starts_at)
        .exclude(vacancy=vacancy)
        .exists()
    )


@transaction.atomic
def apply_to_vacancy(vacancy, worker, *, actor=None, now=None):
    now = now or timezone.now()
    vacancy = Vacancy.objects.select_for_update().get(pk=vacancy.pk)
    if not vacancy.accepts_applications(now):
        raise DomainError("A vaga não aceita candidaturas.")
    if worker.verification_status != Worker.VerificationStatus.APPROVED:
        raise DomainError("Só prestadores aprovados podem se candidatar.")
    if not worker.pix_key:
        raise DomainError("Cadastre uma chave PIX para se candidatar.")
    if worker.is_suspended(now):
        raise DomainError("Prestador suspenso não pode se candidatar.")
    if Application.objects.filter(vacancy=vacancy, worker=worker).exists():
        raise DomainError("Você já se candidatou a esta vaga.")
    if _has_overlap(worker, vacancy):
        raise DomainError("Você já tem outro turno neste horário.")
    application = Application.objects.create(vacancy=vacancy, worker=worker)
    record_creation(application, APPLICATION_MACHINE, actor=actor or worker.user, now=now)
    return application


@transaction.atomic
def approve_application(application, *, actor=None, now=None):
    """Empresa aprova: cria a Alocação CONFIRMADA e notifica o prestador."""
    now = now or timezone.now()
    APPLICATION_MACHINE.validate(application.status, A.APPROVED)
    vacancy = Vacancy.objects.select_for_update().get(pk=application.vacancy_id)
    worker = application.worker
    if vacancy.filled_positions >= vacancy.positions:
        raise DomainError("Não há posição livre nesta vaga.")
    open_window = now < vacancy.starts_at or (vacancy.reopened and now < vacancy.ends_at)
    if not open_window:
        raise DomainError("O turno já começou; não é possível aprovar esta candidatura.")
    if worker.is_suspended(now):
        raise DomainError("Prestador suspenso não pode ser aprovado.")
    if _has_overlap(worker, vacancy):
        raise DomainError("O prestador já tem outro turno neste horário.")
    application = transition(
        application,
        APPLICATION_MACHINE,
        A.APPROVED,
        actor=actor,
        reason="Candidatura aprovada pela empresa",
        now=now,
        decided_at=now,
        decided_by=actor,
    )
    assignment = Assignment.objects.create(
        vacancy=vacancy, worker=worker, application=application
    )
    record_creation(
        assignment, ASSIGNMENT_MACHINE, actor=actor, reason="Candidatura aprovada", now=now
    )
    notify(
        worker.user,
        "CANDIDATURA_APROVADA",
        "Candidatura aprovada",
        f"Você foi aprovado para “{vacancy.title}”.",
    )
    return assignment


@transaction.atomic
def reject_application(application, *, actor=None, now=None):
    application = transition(
        application,
        APPLICATION_MACHINE,
        A.REJECTED,
        actor=actor,
        reason="Candidatura recusada pela empresa",
        now=now,
        decided_at=now or timezone.now(),
        decided_by=actor,
    )
    notify(
        application.worker.user,
        "CANDIDATURA_RECUSADA",
        "Candidatura recusada",
        f"Sua candidatura para “{application.vacancy.title}” foi recusada.",
    )
    return application


@transaction.atomic
def withdraw_application(application, *, actor=None, now=None):
    return transition(
        application,
        APPLICATION_MACHINE,
        A.WITHDRAWN,
        actor=actor,
        reason="Desistência do prestador",
        now=now,
    )
