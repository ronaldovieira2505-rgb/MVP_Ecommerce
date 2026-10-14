from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

from apps.core.masking import mask_cpf, mask_pix_key
from apps.core.validators import validate_adult, validate_cpf


class PrivateMediaStorage(FileSystemStorage):
    """Armazenamento privado: documentos nunca têm URL pública."""

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return self.base_location

    def url(self, name):
        raise ValueError("Documentos privados não possuem URL pública.")


def private_storage():
    return PrivateMediaStorage()


class Worker(models.Model):
    """Prestador (pessoa física)."""

    class VerificationStatus(models.TextChoices):
        PENDING_DOCUMENTS = "PENDENTE_DOCUMENTOS", "Pendente de documentos"
        IN_REVIEW = "EM_ANALISE", "Em análise"
        APPROVED = "APROVADO", "Aprovado"
        REJECTED = "REJEITADO", "Rejeitado"

    class PixKeyType(models.TextChoices):
        CPF = "CPF", "CPF"
        EMAIL = "EMAIL", "E-mail"
        PHONE = "TELEFONE", "Telefone"
        RANDOM = "ALEATORIA", "Aleatória"

    class Level(models.TextChoices):
        NEW = "NOVO", "Novo"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="worker"
    )
    full_name = models.CharField("nome completo", max_length=200)
    cpf = models.CharField("CPF", max_length=11, unique=True, validators=[validate_cpf])
    phone = models.CharField("telefone", max_length=20, blank=True)
    birth_date = models.DateField("data de nascimento", validators=[validate_adult])
    verification_status = models.CharField(
        "verificação",
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING_DOCUMENTS,
    )
    pix_key_type = models.CharField(
        "tipo da chave PIX", max_length=10, choices=PixKeyType.choices, blank=True
    )
    pix_key = models.CharField("chave PIX", max_length=100, blank=True)
    home_latitude = models.DecimalField(
        "latitude residencial", max_digits=9, decimal_places=6, null=True, blank=True
    )
    home_longitude = models.DecimalField(
        "longitude residencial", max_digits=9, decimal_places=6, null=True, blank=True
    )
    suspended_until = models.DateTimeField("suspenso até", null=True, blank=True)
    level = models.CharField("nível", max_length=10, choices=Level.choices, default=Level.NEW)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "prestador"
        verbose_name_plural = "prestadores"

    def __str__(self):
        # Sem dados pessoais em logs.
        return f"Prestador #{self.pk}"

    @property
    def masked_cpf(self):
        return mask_cpf(self.cpf)

    @property
    def masked_pix_key(self):
        return mask_pix_key(self.pix_key_type, self.pix_key)

    def is_suspended(self, now):
        return self.suspended_until is not None and self.suspended_until > now


class WorkerDocument(models.Model):
    class Kind(models.TextChoices):
        FRONT = "DOC_FRENTE", "Documento (frente)"
        BACK = "DOC_VERSO", "Documento (verso)"
        SELFIE = "SELFIE", "Selfie"

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices)
    file = models.FileField("arquivo", upload_to="worker_documents/", storage=private_storage)
    uploaded_at = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "documento do prestador"
        verbose_name_plural = "documentos dos prestadores"

    def __str__(self):
        return f"{self.kind} do prestador #{self.worker_id}"
