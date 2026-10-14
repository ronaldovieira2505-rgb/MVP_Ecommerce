from django.conf import settings
from django.utils.module_loading import import_string

from integrations.cnpj.base import CnpjData, CnpjLookup, CnpjLookupError, CnpjNotFound

__all__ = [
    "CnpjData",
    "CnpjLookup",
    "CnpjLookupError",
    "CnpjNotFound",
    "get_cnpj_lookup",
    "reset_cnpj_lookup",
]

_instance = None


def get_cnpj_lookup() -> CnpjLookup:
    """Instância única da implementação configurada em `CNPJ_LOOKUP`."""
    global _instance
    if _instance is None:
        _instance = import_string(settings.CNPJ_LOOKUP)()
    return _instance


def reset_cnpj_lookup():
    global _instance
    _instance = None
