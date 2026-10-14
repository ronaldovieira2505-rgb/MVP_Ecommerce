"""Consulta de CNPJ simulada: determinística, sem rede. Usada em desenvolvimento e nos testes."""

from integrations.cnpj.base import CnpjData, CnpjLookup, CnpjLookupError, CnpjNotFound


class FakeCnpjLookup(CnpjLookup):
    def __init__(self):
        self.fail = False  # simula BrasilAPI fora do ar ou lenta
        self.not_found = set()
        self.calls = []  # (cnpj, timeout) de cada consulta feita

    def lookup(self, cnpj, *, timeout):
        self.calls.append((cnpj, timeout))
        if self.fail:
            raise CnpjLookupError("BrasilAPI simulada indisponível.")
        if cnpj in self.not_found:
            raise CnpjNotFound("CNPJ não encontrado.")
        return CnpjData(
            cnpj=cnpj,
            legal_name=f"Empresa Simulada {cnpj[:8]} LTDA",
            trade_name=f"Simulada {cnpj[:8]}",
            registration_status="ATIVA",
            street="Rua das Flores",
            number="100",
            complement="Sala 1",
            district="Centro",
            city="São Paulo",
            state="SP",
            zip_code="01001000",
        )
