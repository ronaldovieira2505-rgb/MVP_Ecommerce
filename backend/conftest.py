import pytest

from integrations.payments import get_gateway, reset_gateway


@pytest.fixture(autouse=True)
def fake_gateway():
    """PSP simulado limpo a cada teste (os testes nunca chamam serviços externos)."""
    reset_gateway()
    yield get_gateway()
    reset_gateway()
