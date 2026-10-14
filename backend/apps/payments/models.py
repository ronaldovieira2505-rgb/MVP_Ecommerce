from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import DomainError


class Custody(models.Model):
    """Valor retido no PSP para uma vaga (a plataforma não custodia fundos)."""

    class Status(models.TextChoices):
        PENDING = "PENDENTE", "Pendente"
        HELD = "RETIDA", "Retida"
        CANCELLED = "CANCELADA", "Cancelada"
        CLOSED = "ENCERRADA", "Encerrada"

    vacancy = models.OneToOneField(
        "vacancies.Vacancy", on_delete=models.PROTECT, related_name="custody"
    )
    amount_cents = models.PositiveIntegerField("valor (centavos)")
    status = models.CharField("status", max_length=10, choices=Status.choices, default="PENDENTE")
    psp_reference = models.CharField("referência no PSP", max_length=100, blank=True)
    idempotency_key = models.CharField("chave de idempotência", max_length=120, unique=True)
    created_at = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        verbose_name = "custódia"
        verbose_name_plural = "custódias"

    def __str__(self):
        return f"Custódia #{self.pk}"


class LedgerQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise DomainError("O livro-razão é imutável.")

    def delete(self):
        raise DomainError("O livro-razão é imutável.")


class LedgerEntry(models.Model):
    """Lançamento do livro-razão: imutável, só inserção."""

    class Kind(models.TextChoices):
        RETENTION = "RETENCAO", "Retenção"
        WORKER_PAYOUT = "REPASSE_PRESTADOR", "Repasse ao prestador"
        PLATFORM_FEE = "TAXA_PLATAFORMA", "Taxa da plataforma"
        COMPANY_REFUND = "ESTORNO_CONTRATANTE", "Estorno ao contratante"

    custody = models.ForeignKey(Custody, on_delete=models.PROTECT, related_name="entries")
    assignment = models.ForeignKey(
        "vacancies.Assignment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    amount_cents = models.PositiveIntegerField("valor (centavos)")
    idempotency_key = models.CharField("chave de idempotência", max_length=120, unique=True)
    created_at = models.DateTimeField("criado em", default=timezone.now)

    objects = LedgerQuerySet.as_manager()

    class Meta:
        verbose_name = "lançamento"
        verbose_name_plural = "livro-razão"
        constraints = [
            models.CheckConstraint(condition=Q(amount_cents__gt=0), name="ledger_amount_gt_0")
        ]

    def __str__(self):
        return f"{self.kind} {self.amount_cents}"

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise DomainError("O livro-razão é imutável.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise DomainError("O livro-razão é imutável.")
