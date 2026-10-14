import pytest

from integrations.cnpj import get_cnpj_lookup, reset_cnpj_lookup
from integrations.payments import get_gateway, reset_gateway


@pytest.fixture(autouse=True)
def fake_gateway():
    """PSP simulado limpo a cada teste (os testes nunca chamam serviços externos)."""
    reset_gateway()
    yield get_gateway()
    reset_gateway()


@pytest.fixture(autouse=True)
def fake_cnpj_lookup(settings):
    """BrasilAPI simulada a cada teste (nenhum teste chama a internet)."""
    settings.CNPJ_LOOKUP = "integrations.cnpj.fake.FakeCnpjLookup"
    reset_cnpj_lookup()
    yield get_cnpj_lookup()
    reset_cnpj_lookup()
