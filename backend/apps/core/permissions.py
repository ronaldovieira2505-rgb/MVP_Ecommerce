"""Permissões do DRF por papel e por objeto. A autorização é sempre verificada no servidor."""

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class HasRole(BasePermission):
    """Base: exige usuário autenticado com um dos papéis em `roles`."""

    roles: tuple = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.roles)


class IsCompanyUser(HasRole):
    roles = (Role.COMPANY,)


class IsWorkerUser(HasRole):
    roles = (Role.WORKER,)


class IsAdminUser(HasRole):
    roles = (Role.ADMIN,)


def _belongs_to_user(obj, user):
    """O objeto pertence ao usuário? Considera `user`, `worker`, `company` (vínculo)."""
    if getattr(obj, "user_id", None) is not None:
        return obj.user_id == user.pk
    worker = getattr(obj, "worker", None)
    if worker is not None and hasattr(worker, "user_id"):
        return worker.user_id == user.pk
    company = getattr(obj, "company", None)
    if company is not None:
        return company.members.filter(user=user).exists()
    return False


class IsObjectOwner(BasePermission):
    """Permissão por objeto: só o dono (usuário, prestador ou membro da empresa) acessa.

    Admin (`role=ADMIN`) tem acesso a qualquer objeto.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role == Role.ADMIN:
            return True
        return _belongs_to_user(obj, user)
