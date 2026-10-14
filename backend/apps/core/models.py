from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class PlatformParameters(models.Model):
    """Parâmetros editáveis (singleton). Padrões em docs/regras-de-negocio.md."""

    min_publish_lead_minutes = models.PositiveIntegerField(
        "antecedência mínima de publicação (min)", default=720
    )
    payment_deadline_minutes = models.PositiveIntegerField(
        "prazo para pagar a vaga (min)", default=1440
    )
    applications_close_minutes_before = models.PositiveIntegerField(
        "encerramento de candidaturas (min antes do início)", default=120
    )
    checkin_open_minutes_before = models.PositiveIntegerField(
        "antecedência do check-in (min)", default=30
    )
    no_show_tolerance_minutes = models.PositiveIntegerField(
        "tolerância de falta (min)", default=30
    )
    geofence_radius_m = models.PositiveIntegerField("raio do check-in (m)", default=150)
    auto_checkout_minutes_after_end = models.PositiveIntegerField(
        "check-out automático (min após o fim)", default=120
    )
    contest_window_minutes = models.PositiveIntegerField(
        "janela de contestação (min)", default=1440
    )
    no_show_limit = models.PositiveIntegerField("faltas que geram suspensão", default=2)
    no_show_window_days = models.PositiveIntegerField("janela de faltas (dias)", default=30)
    suspension_days = models.PositiveIntegerField("duração da suspensão (dias)", default=15)
    free_cancel_minutes_before = models.PositiveIntegerField(
        "cancelamento sem penalidade (min antes) [pós-MVP]", default=1440
    )
    late_cancel_block_days = models.PositiveIntegerField(
        "bloqueio por cancelamento tardio (dias) [pós-MVP]", default=7
    )
    cnpj_lookup_timeout_seconds = models.PositiveIntegerField(
        "limite da consulta de CNPJ (s)", default=5
    )
    document_max_size_mb = models.PositiveIntegerField(
        "tamanho máximo de cada documento/selfie (MB)", default=5
    )
    worker_fee_percent = models.DecimalField(
        "taxa retida do prestador (%)", max_digits=5, decimal_places=2, default=Decimal("3")
    )

    class Meta:
        verbose_name = "parâmetros da plataforma"
        verbose_name_plural = "parâmetros da plataforma"

    def __str__(self):
        return "Parâmetros da plataforma"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Os parâmetros da plataforma não podem ser apagados.")

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def worker_fee_cents(self, gross_cents):
        """Taxa em centavos: percentual arredondado para o centavo mais próximo (meio p/ cima)."""
        fee = Decimal(gross_cents) * self.worker_fee_percent / Decimal(100)
        return int(fee.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def worker_net_cents(self, gross_cents):
        return gross_cents - self.worker_fee_cents(gross_cents)


class PlatformParametersChange(models.Model):
    """Auditoria simples dos parâmetros: quem, quando, valor anterior e novo."""

    field = models.CharField("parâmetro", max_length=60)
    old_value = models.CharField("valor anterior", max_length=40)
    new_value = models.CharField("valor novo", max_length=40)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="alterado por",
    )
    changed_at = models.DateTimeField("alterado em", default=timezone.now)

    class Meta:
        verbose_name = "alteração de parâmetro"
        verbose_name_plural = "alterações de parâmetros"
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.field}: {self.old_value} → {self.new_value}"


class StateTransition(models.Model):
    """Trilha de auditoria de qualquer mudança de estado."""

    entity_type = models.CharField("entidade", max_length=50)
    entity_id = models.BigIntegerField("id da entidade")
    from_state = models.CharField("estado de origem", max_length=40, blank=True)
    to_state = models.CharField("estado de destino", max_length=40)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="ator",
        help_text="Vazio = SISTEMA.",
    )
    reason = models.TextField("motivo", blank=True)
    created_at = models.DateTimeField("data", default=timezone.now)

    class Meta:
        verbose_name = "transição de estado"
        verbose_name_plural = "transições de estado"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return f"{self.entity_type}#{self.entity_id}: {self.from_state or '—'} → {self.to_state}"


class VerificationReview(models.Model):
    """Decisão do admin na fila de verificação."""

    class SubjectType(models.TextChoices):
        COMPANY = "COMPANY", "Contratante"
        WORKER = "WORKER", "Prestador"

    class Decision(models.TextChoices):
        APPROVED = "APROVADO", "Aprovado"
        REJECTED = "REJEITADO", "Rejeitado"

    subject_type = models.CharField("tipo", max_length=10, choices=SubjectType.choices)
    subject_id = models.BigIntegerField("id do sujeito")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verification_reviews",
        verbose_name="analista",
    )
    decision = models.CharField("decisão", max_length=10, choices=Decision.choices)
    reason = models.TextField("motivo", blank=True)
    created_at = models.DateTimeField("data", default=timezone.now)

    class Meta:
        verbose_name = "análise de verificação"
        verbose_name_plural = "análises de verificação"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject_type}#{self.subject_id}: {self.decision}"


class Notification(models.Model):
    """Notificação dentro do app (sem e-mail ou push no MVP)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="usuário",
    )
    kind = models.CharField("tipo", max_length=40)
    title = models.CharField("título", max_length=120)
    message = models.TextField("mensagem", blank=True)
    link = models.CharField("link", max_length=200, blank=True)
    read_at = models.DateTimeField("lida em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.kind}: {self.title}"
