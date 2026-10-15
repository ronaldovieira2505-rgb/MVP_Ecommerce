"""Fila de verificação de cadastros (US73): empresas `PENDENTE` e prestadores `EM_ANALISE`."""

from dataclasses import dataclass
from datetime import datetime

from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce

from apps.companies.models import Company
from apps.companies.services import review_company
from apps.companies.state_machine import COMPANY_VERIFICATION_MACHINE
from apps.core.models import StateTransition, VerificationReview
from apps.workers.models import Worker
from apps.workers.services import review_worker
from apps.workers.state_machine import WORKER_VERIFICATION_MACHINE

SubjectType = VerificationReview.SubjectType

# Rótulo do tipo e slug usado na URL do painel.
KIND_SLUGS = {SubjectType.COMPANY: "empresa", SubjectType.WORKER: "prestador"}
SLUG_KINDS = {slug: kind for kind, slug in KIND_SLUGS.items()}


@dataclass(frozen=True)
class QueueItem:
    kind: str
    slug: str
    label: str
    pk: int
    name: str
    arrived_at: datetime


def _arrival(machine, queue_state):
    """Chegada na fila = última entrada no estado da fila (cobre o reenvio); senão, a criação."""
    last_entry = (
        StateTransition.objects.filter(
            entity_type=machine.entity_type,
            entity_id=OuterRef("pk"),
            to_state=queue_state,
        )
        .order_by("-created_at", "-id")
        .values("created_at")[:1]
    )
    return Coalesce(Subquery(last_entry), "created_at")


def queue_items():
    """Cadastros pendentes em ordem de chegada (mais antigo primeiro)."""
    companies = Company.objects.filter(
        verification_status=Company.VerificationStatus.PENDING
    ).annotate(
        arrived_at=_arrival(COMPANY_VERIFICATION_MACHINE, Company.VerificationStatus.PENDING)
    )
    workers = Worker.objects.filter(
        verification_status=Worker.VerificationStatus.IN_REVIEW
    ).annotate(
        arrived_at=_arrival(WORKER_VERIFICATION_MACHINE, Worker.VerificationStatus.IN_REVIEW)
    )
    items = [
        QueueItem(
            kind=SubjectType.COMPANY,
            slug=KIND_SLUGS[SubjectType.COMPANY],
            label=SubjectType.COMPANY.label,
            pk=company.pk,
            name=str(company),
            arrived_at=company.arrived_at,
        )
        for company in companies
    ] + [
        QueueItem(
            kind=SubjectType.WORKER,
            slug=KIND_SLUGS[SubjectType.WORKER],
            label=SubjectType.WORKER.label,
            pk=worker.pk,
            name=worker.full_name,
            arrived_at=worker.arrived_at,
        )
        for worker in workers
    ]
    return sorted(items, key=lambda item: (item.arrived_at, item.slug, item.pk))


def decide(kind, subject, *, reviewer, approve, reason=""):
    """Aprova ou rejeita pelo serviço de domínio (valida o estado e grava a auditoria)."""
    review = review_company if kind == SubjectType.COMPANY else review_worker
    return review(subject, reviewer=reviewer, approve=approve, reason=reason.strip())
