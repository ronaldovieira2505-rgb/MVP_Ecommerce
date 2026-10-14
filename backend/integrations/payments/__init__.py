from django.conf import settings
from django.utils.module_loading import import_string

from integrations.payments.base import GatewayResult, PaymentGateway, PaymentGatewayError

__all__ = ["GatewayResult", "PaymentGateway", "PaymentGatewayError", "get_gateway", "reset_gateway"]

_instance = None


def get_gateway() -> PaymentGateway:
    """Instância única da implementação configurada em `PAYMENT_GATEWAY`."""
    global _instance
    if _instance is None:
        _instance = import_string(settings.PAYMENT_GATEWAY)()
    return _instance


def reset_gateway():
    global _instance
    _instance = None
