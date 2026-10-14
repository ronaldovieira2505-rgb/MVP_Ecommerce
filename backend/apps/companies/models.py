from django.conf import settings
from django.db import models

from apps.core.validators import validate_cnpj


class Company(models.Model):
    """Contratante (empresa com CNPJ)."""

    class TaxRegime(models.TextChoices):
        SIMPLES = "SIMPLES", "Simples Nacional"
        NORMAL = "NORMAL", "Normal"

    class PaymentMethod(models.TextChoices):
        PIX = "PIX", "PIX"
        BOLETO = "BOLETO", "Boleto"
        CARD = "CARTAO", "Cartão"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDENTE", "Pendente"
        APPROVED = "APROVADA", "Aprovada"
        REJECTED = "REJEITADA", "Rejeitada"

    cnpj = models.CharField("CNPJ", max_length=14, unique=True, validators=[validate_cnpj])
    legal_name = models.CharField("razão social", max_length=200)
    trade_name = models.CharField("nome fantasia", max_length=200, blank=True)
    state_registration = models.CharField("inscrição estadual", max_length=30, blank=True)
    tax_regime = models.CharField("regime tributário", max_length=10, choices=TaxRegime.choices)
    registration_status = models.CharField("situação cadastral", max_length=40, blank=True)
    street = models.CharField("logradouro", max_length=200, blank=True)
    number = models.CharField("número", max_length=20, blank=True)
    complement = models.CharField("complemento", max_length=100, blank=True)
    district = models.CharField("bairro", max_length=100, blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    zip_code = models.CharField("CEP", max_length=8, blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    preferred_payment_method = models.CharField(
        "meio de pagamento preferido", max_length=10, choices=PaymentMethod.choices, blank=True
    )
    verification_status = models.CharField(
        "verificação",
        max_length=12,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    description = models.TextField("descrição", blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "contratante"
        verbose_name_plural = "contratantes"

    def __str__(self):
        return self.trade_name or self.legal_name


class CompanyMember(models.Model):
    """Vínculo entre usuário e empresa (nunca compartilhar login)."""

    class MemberRole(models.TextChoices):
        OWNER = "OWNER", "Proprietário"
        MANAGER = "MANAGER", "Gerente"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_memberships"
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")
    role = models.CharField("papel", max_length=10, choices=MemberRole.choices, default="OWNER")

    class Meta:
        verbose_name = "membro da empresa"
        verbose_name_plural = "membros das empresas"
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="unique_company_member")
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.company_id} ({self.role})"
