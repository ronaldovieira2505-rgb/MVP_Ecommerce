"""Erros de domínio explícitos."""


class DomainError(Exception):
    """Violação de regra de negócio. Nada é gravado quando ela é lançada."""


class InvalidTransition(DomainError):
    """Transição de estado que não está listada em docs/maquina-de-estados.md."""
