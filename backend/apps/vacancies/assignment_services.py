"""Serviço de domínio da Alocação: execução, validação e liquidação."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.notifications import notify, notify_admins, notify_company
from apps.core.state_machine import transition
from apps.payments import services as payments
from apps.vacancies.models import Assignment
from apps.vacancies.state_machine import ASSIGNMENT_MACHINE
from apps.workers.services import apply_automatic_suspension
from integrations.geo import haversine_distance_m

S = Assignment.Status


@transaction.atomic
def check_in(assignment, *, lat, lng, actor=None, now=None):
    now = now or timezone.now()
    ASSIGNMENT_MACHINE.validate(assignment.status, S.IN_PROGRESS)
    params = PlatformParameters.get()
    vacancy = assignment.vacancy
    opens_at = vacancy.starts_at - timedelta(minutes=params.checkin_open_minutes_before)
    closes_at = vacancy.starts_at + timedelta(minutes=params.no_show_tolerance_minutes)
    if not opens_at <= now <= closes_at:
        raise DomainError("O check-in está fora da janela permitida.")
    distance = haversine_distance_m(lat, lng, vacancy.latitude, vacancy.longitude)
    if distance > params.geofence_radius_m:
        raise DomainError(
            f"Você está a {round(distance)} m do local; o limite é {params.geofence_radius_m} m."
        )
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.IN_PROGRESS,
        actor=actor,
        reason="Check-in realizado",
        now=now,
        check_in_at=now,
        check_in_lat=lat,
        check_in_lng=lng,
        check_in_distance_m=round(distance),
    )


@transaction.atomic
def check_out(assignment, *, actor=None, now=None):
    now = now or timezone.now()
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.AWAITING_VALIDATION,
        actor=actor,
        reason="Check-out realizado",
        now=now,
        check_out_at=now,
    )


@transaction.atomic
def auto_check_out(assignment, *, now=None):
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.AWAITING_VALIDATION,
        reason="Check-out automático",
        now=now,
        check_out_at=assignment.vacancy.ends_at,
        check_out_auto=True,
    )


@transaction.atomic
def mark_no_show(assignment, *, now=None):
    """Falta: libera a posição, reabre a vaga, avisa a empresa e avalia a suspensão."""
    now = now or timezone.now()
    assignment = transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.NO_SHOW,
        reason="Sem check-in dentro da tolerância",
        now=now,
    )
    vacancy = assignment.vacancy
    if now < vacancy.ends_at and not vacancy.reopened:
        vacancy.reopened = True
        vacancy.save(update_fields=["reopened"])
    notify_company(
        vacancy.company,
        "FALTA",
        "Prestador faltou",
        f"Um prestador não compareceu a “{vacancy.title}”. A vaga foi reaberta.",
    )
    apply_automatic_suspension(assignment.worker, now=now)
    return assignment


@transaction.atomic
def approve_hours(assignment, *, actor=None, now=None):
    now = now or timezone.now()
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.APPROVED,
        actor=actor,
        reason="Horas aprovadas pela empresa",
        now=now,
        validated_at=now,
        validated_by=actor,
    )


@transaction.atomic
def auto_approve_hours(assignment, *, now=None):
    now = now or timezone.now()
    return transition(
        assignment,
        ASSIGNMENT_MACHINE,
        S.APPROVED,
        reason="aprovação por decurso de prazo",
        now=now,
        validated_at=now,
        validated_by=None,
    )


@transaction.atomic
def contest(assignment, *, reason, actor=None, now=None):
    if not reason.strip():
        raise DomainError("Informe o motivo da contestação.")
    assignment = transition(
        assignment, ASSIGNMENT_MACHINE, S.CONTESTED, actor=actor, reason=reason, now=now
    )
    message = f"A empresa contestou as horas de “{assignment.vacancy.title}”."
    notify(assignment.worker.user, "CONTESTACAO", "Horas contestadas", message)
    notify_admins("CONTESTACAO", "Nova contestação", message)
    return assignment


@transaction.atomic
def resolve_contest(assignment, *, in_favor_of_worker, reason, actor, now=None):
    """Admin decide: a favor do prestador → APROVADA; da empresa → ESTORNADA."""
    if not reason.strip():
        raise DomainError("O motivo é obrigatório.")
    if in_favor_of_worker:
        return transition(
            assignment,
            ASSIGNMENT_MACHINE,
            S.APPROVED,
            actor=actor,
            reason=reason,
            now=now,
            validated_at=now or timezone.now(),
            validated_by=actor,
        )
    ASSIGNMENT_MACHINE.validate(assignment.status, S.REFUNDED)
    payments.refund_assignment(
        assignment.vacancy.custody, assignment, actor=actor, reason=reason, now=now
    )
    return transition(
        assignment, ASSIGNMENT_MACHINE, S.REFUNDED, actor=actor, reason=reason, now=now
    )


@transaction.atomic
def settle(assignment, *, now=None):
    """APROVADA → PAGA. Se o PSP falhar, a exceção desfaz tudo e segue APROVADA."""
    ASSIGNMENT_MACHINE.validate(assignment.status, S.PAID)
    payments.settle_assignment(assignment.vacancy.custody, assignment, now=now)
    assignment = transition(
        assignment, ASSIGNMENT_MACHINE, S.PAID, reason="Liquidação do turno", now=now
    )
    notify(
        assignment.worker.user,
        "PAGAMENTO_LIBERADO",
        "Pagamento liberado",
        f"O pagamento de “{assignment.vacancy.title}” foi liberado.",
    )
    return assignment
