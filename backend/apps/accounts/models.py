from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    COMPANY = "COMPANY", "Contratante"
    WORKER = "WORKER", "Prestador"
    ADMIN = "ADMIN", "Administrador"


class ConectaUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Usuário customizado. Admin = `is_staff`; `role` define a área do usuário."""

    role = models.CharField("perfil", max_length=10, choices=Role.choices, default=Role.WORKER)

    objects = ConectaUserManager()
