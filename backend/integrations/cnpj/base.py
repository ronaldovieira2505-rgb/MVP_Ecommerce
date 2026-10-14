"""Interface da consulta de CNPJ. A implementação vem de `CNPJ_LOOKUP`."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class CnpjLookupError(Exception):
    """Serviço fora do ar, lento (timeout) ou com resposta inválida."""


class CnpjNotFound(CnpjLookupError):
    """O CNPJ não existe na base consultada."""


@dataclass(frozen=True)
class CnpjData:
    cnpj: str
    legal_name: str
    trade_name: str = ""
    registration_status: str = ""
    street: str = ""
    number: str = ""
    complement: str = ""
    district: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""


class CnpjLookup(ABC):
    @abstractmethod
    def lookup(self, cnpj: str, *, timeout: float) -> CnpjData:
        """Consulta o CNPJ (só dígitos, já validado). Lança `CnpjLookupError` em caso de falha."""
