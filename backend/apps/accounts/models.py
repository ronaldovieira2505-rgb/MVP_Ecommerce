from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuário customizado.

    Existe desde a primeira migration para permitir evoluir a identidade
    (Contratante, Contratado, Admin) sem trocar o AUTH_USER_MODEL depois.
    Nenhuma regra de negócio aqui por enquanto.
    """
