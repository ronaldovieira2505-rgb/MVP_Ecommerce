"""Custódia e livro-razão. Toda operação é idempotente pela chave do lançamento."""

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.state_machine import record_creation, transition
from apps.payments.models import Custody, LedgerEntry
from apps.payments.state_machine import CUSTODY_MACHINE
from integrations.payments import get_gateway

K = LedgerEntry.Kind
C = Custody.Status


def _lock(custody):
    return Custody.objects.select_for_update().get(pk=custody.pk)


def _entry(custody, kind, amount_cents, key, assignment=None, now=None):
    """Cria o lançamento uma única vez por chave. Devolve (lançamento, criado)."""
    return LedgerEntry.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "custody": custody,
            "assignment": assignment,
            "kind": kind,
            "amount_cents": amount_cents,
            "created_at": now or timezone.now(),
        },
    )


def total_by_kind(custody):
    rows = custody.entries.values("kind").annotate(total=Sum("amount_cents"))
    return {row["kind"]: row["total"] for row in rows}


@transaction.atomic
def open_custody(vacancy, *, actor=None, now=None):
    custody = Custody.objects.create(
        vacancy=vacancy,
        amount_cents=vacancy.pay_per_person_cents * vacancy.positions,
        idempotency_key=f"custody:vacancy:{vacancy.pk}",
        created_at=now or timezone.now(),
    )
    record_creation(custody, CUSTODY_MACHINE, actor=actor, reason="Vaga criada", now=now)
    return custody


@transaction.atomic
def retain(custody, *, actor=None, now=None):
    """Empresa pagou: o PSP retém o valor e a custódia passa a RETIDA."""
    custody = _lock(custody)
    if custody.status == C.HELD:
        return custody  # repetição: nada a fazer
    CUSTODY_MACHINE.validate(custody.status, C.HELD)
    result = get_gateway().hold(
        idempotency_key=f"{custody.idempotency_key}:retencao", amount_cents=custody.amount_cents
    )
    _entry(custody, K.RETENTION, custody.amount_cents, f"custody:{custody.pk}:retencao", now=now)
    return transition(
        custody,
        CUSTODY_MACHINE,
        C.HELD,
        actor=actor,
        reason="Pagamento confirmado",
        now=now,
        psp_reference=result.reference,
    )


@transaction.atomic
def cancel_pending(custody, *, actor=None, reason="", now=None):
    custody = _lock(custody)
    return transition(custody, CUSTODY_MACHINE, C.CANCELLED, actor=actor, reason=reason, now=now)


@transaction.atomic
def settle_assignment(custody, assignment, *, actor=None, now=None):
    """Liquida uma alocação aprovada: repasse (valor − taxa) e taxa da plataforma."""
    custody = _lock(custody)
    payout_key = f"assignment:{assignment.pk}:repasse"
    if LedgerEntry.objects.filter(idempotency_key=payout_key).exists():
        return custody  # repetição: não duplica lançamentos
    if custody.status != C.HELD:
        raise DomainError("A custódia precisa estar RETIDA para liquidar uma alocação.")

    gross = assignment.vacancy.pay_per_person_cents
    params = PlatformParameters.get()
    fee = params.worker_fee_cents(gross)
    net = gross - fee
    gateway = get_gateway()
    gateway.release(
        idempotency_key=payout_key, amount_cents=net, destination=f"worker:{assignment.worker_id}"
    )
    _entry(custody, K.WORKER_PAYOUT, net, payout_key, assignment, now)
    if fee > 0:
        fee_key = f"assignment:{assignment.pk}:taxa"
        gateway.release(idempotency_key=fee_key, amount_cents=fee, destination="platform")
        _entry(custody, K.PLATFORM_FEE, fee, fee_key, assignment, now)
    return transition(
        custody,
        CUSTODY_MACHINE,
        C.HELD,
        actor=actor,
        reason=f"Liquidação da alocação {assignment.pk}",
        now=now,
    )


@transaction.atomic
def refund_assignment(custody, assignment, *, actor=None, reason="", now=None):
    """Devolve à empresa o valor da posição de uma alocação estornada/cancelada."""
    custody = _lock(custody)
    key = f"assignment:{assignment.pk}:estorno"
    if LedgerEntry.objects.filter(idempotency_key=key).exists():
        return custody
    if custody.status != C.HELD:
        raise DomainError("A custódia precisa estar RETIDA para estornar uma alocação.")
    amount = assignment.vacancy.pay_per_person_cents
    get_gateway().refund(idempotency_key=key, amount_cents=amount)
    _entry(custody, K.COMPANY_REFUND, amount, key, assignment, now)
    return transition(
        custody,
        CUSTODY_MACHINE,
        C.HELD,
        actor=actor,
        reason=reason or f"Estorno da alocação {assignment.pk}",
        now=now,
    )


@transaction.atomic
def close(custody, *, actor=None, reason="", now=None):
    """Encerra a custódia estornando o saldo restante (vaga finalizada ou cancelada)."""
    custody = _lock(custody)
    if custody.status == C.CLOSED:
        return custody
    CUSTODY_MACHINE.validate(custody.status, C.CLOSED)
    totals = total_by_kind(custody)
    used = sum(totals.get(k, 0) for k in (K.WORKER_PAYOUT, K.PLATFORM_FEE, K.COMPANY_REFUND))
    remaining = custody.amount_cents - used
    if remaining < 0:
        raise DomainError("Invariante violada: lançamentos superam o valor retido.")
    if remaining > 0:
        key = f"custody:{custody.pk}:estorno-saldo"
        get_gateway().refund(idempotency_key=key, amount_cents=remaining)
        _entry(custody, K.COMPANY_REFUND, remaining, key, now=now)
    return transition(custody, CUSTODY_MACHINE, C.CLOSED, actor=actor, reason=reason, now=now)
