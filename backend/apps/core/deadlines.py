"""Processamento de prazos: aplica todas as transições por prazo, de forma idempotente."""

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies import assignment_services as assignments
from apps.vacancies import services as vacancies
from apps.vacancies.models import Assignment, Vacancy
from apps.workers.models import Worker
from integrations.payments import PaymentGatewayError

logger = logging.getLogger(__name__)

V = Vacancy.Status
S = Assignment.Status


def _apply(counter, key, queryset, action):
    """Aplica `action` a cada item; um item com problema não interrompe os demais."""
    for item in queryset:
        try:
            action(item)
        except (DomainError, PaymentGatewayError) as exc:
            logger.warning("Prazo não aplicado em %s#%s: %s", key, item.pk, exc)
            continue
        counter[key] = counter.get(key, 0) + 1


def process_deadlines(now=None):
    """Devolve um dicionário {ação: quantidade} do que foi aplicado nesta execução."""
    now = now or timezone.now()
    p = PlatformParameters.get()
    done = {}

    # 1. Vaga não paga: prazo para pagar expirou ou a antecedência mínima deixou de ser possível.
    unpaid = Vacancy.objects.filter(status=V.AWAITING_PAYMENT).filter(
        Q(created_at__lte=now - timedelta(hours=p.payment_deadline_hours))
        | Q(starts_at__lt=now + timedelta(hours=p.min_publish_lead_hours))
    )
    _apply(
        done,
        "vagas_canceladas_por_falta_de_pagamento",
        unpaid,
        lambda v: vacancies.cancel_unpaid_vacancy(
            v, reason="Prazo para pagamento expirado", now=now
        ),
    )

    # 2. Encerrar candidaturas.
    to_close = Vacancy.objects.filter(
        status=V.PUBLISHED, starts_at__lte=now + timedelta(hours=p.applications_close_hours_before)
    )
    _apply(
        done,
        "candidaturas_encerradas",
        to_close,
        lambda v: vacancies.close_applications(v, now=now),
    )

    # 3. Iniciar ou cancelar vagas cujo horário chegou.
    due = Vacancy.objects.filter(status=V.APPLICATIONS_CLOSED, starts_at__lte=now)
    with_people = due.filter(assignments__status__in=Assignment.ACTIVE_STATUSES).distinct()
    _apply(done, "vagas_iniciadas", with_people, lambda v: vacancies.start_vacancy(v, now=now))
    without_people = due.exclude(pk__in=with_people.values("pk"))
    _apply(
        done,
        "vagas_canceladas_sem_alocacao",
        without_people,
        lambda v: vacancies.cancel_vacancy_without_assignments(v, now=now),
    )

    # 4. Falta (suspensão automática é efeito colateral e fica registrada em StateTransition).
    no_shows = Assignment.objects.filter(
        status=S.CONFIRMED,
        vacancy__starts_at__lt=now - timedelta(minutes=p.no_show_tolerance_minutes),
    )
    def register_no_show(assignment):
        before = Worker.objects.get(pk=assignment.worker_id).suspended_until
        assignments.mark_no_show(assignment, now=now)
        after = Worker.objects.get(pk=assignment.worker_id).suspended_until
        if after != before:
            done["suspensoes_automaticas"] = done.get("suspensoes_automaticas", 0) + 1

    _apply(done, "faltas", no_shows, register_no_show)

    # 5. Check-out automático.
    overdue = Assignment.objects.filter(
        status=S.IN_PROGRESS,
        vacancy__ends_at__lt=now - timedelta(hours=p.auto_checkout_hours_after_end),
    )
    _apply(done, "checkouts_automaticos", overdue, lambda a: assignments.auto_check_out(a, now=now))

    # 6. Aprovação automática por decurso da janela de contestação.
    silent = Assignment.objects.filter(
        status=S.AWAITING_VALIDATION,
        check_out_at__lte=now - timedelta(hours=p.contest_window_hours),
    )
    _apply(
        done, "aprovacoes_automaticas", silent, lambda a: assignments.auto_approve_hours(a, now=now)
    )

    # 7. Liquidação.
    _apply(
        done,
        "liquidacoes",
        Assignment.objects.filter(status=S.APPROVED),
        lambda a: assignments.settle(a, now=now),
    )

    # 8. Finalização das vagas.
    in_progress = Vacancy.objects.filter(status=V.IN_PROGRESS).filter(
        Q(reopened=False) | Q(ends_at__lte=now)
    )
    _apply(
        done, "vagas_finalizadas", in_progress, lambda v: vacancies.finalize_vacancy(v, now=now)
    )

    return done

