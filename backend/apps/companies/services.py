"""Verificação (triagem manual) da empresa."""

from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.companies.state_machine import COMPANY_VERIFICATION_MACHINE
from apps.core.exceptions import DomainError
from apps.core.models import VerificationReview
from apps.core.notifications import notify_company
from apps.core.state_machine import transition

S = Company.VerificationStatus


@transaction.atomic
def review_company(company, *, reviewer, approve, reason="", now=None):
    if not approve and not reason.strip():
        raise DomainError("O motivo é obrigatório na rejeição.")
    decision = (
        VerificationReview.Decision.APPROVED if approve else VerificationReview.Decision.REJECTED
    )
    company = transition(
        company,
        COMPANY_VERIFICATION_MACHINE,
        S.APPROVED if approve else S.REJECTED,
        actor=reviewer,
        reason=reason,
        now=now,
    )
    VerificationReview.objects.create(
        subject_type=VerificationReview.SubjectType.COMPANY,
        subject_id=company.pk,
        reviewer=reviewer,
        decision=decision,
        reason=reason,
        created_at=now or timezone.now(),
    )
    notify_company(
        company,
        "VERIFICACAO",
        "Cadastro aprovado" if approve else "Cadastro rejeitado",
        reason,
    )
    return company


@transaction.atomic
def resubmit_company(company, *, actor=None, now=None):
    """REJEITADA → PENDENTE: a empresa corrigiu os dados."""
    return transition(
        company,
        COMPANY_VERIFICATION_MACHINE,
        S.PENDING,
        actor=actor,
        reason="Dados corrigidos pela empresa",
        now=now,
    )
