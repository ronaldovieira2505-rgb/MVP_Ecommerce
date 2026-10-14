"""Interface do PSP. O domínio depende só disto; a implementação vem de `PAYMENT_GATEWAY`."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class PaymentGatewayError(Exception):
    """Falha ao falar com o PSP. O domínio tenta de novo no próximo processamento."""


@dataclass(frozen=True)
class GatewayResult:
    reference: str


class PaymentGateway(ABC):
    """Todas as operações são idempotentes pela `idempotency_key`."""

    @abstractmethod
    def hold(self, *, idempotency_key: str, amount_cents: int) -> GatewayResult:
        """Retém o valor pago pela empresa."""

    @abstractmethod
    def release(
        self, *, idempotency_key: str, amount_cents: int, destination: str
    ) -> GatewayResult:
        """Libera valor retido para um destino (prestador ou plataforma)."""

    @abstractmethod
    def refund(self, *, idempotency_key: str, amount_cents: int) -> GatewayResult:
        """Devolve valor retido à empresa."""
