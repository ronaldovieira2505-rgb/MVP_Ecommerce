import pytest

from integrations.geo import haversine_distance_m
from integrations.payments import PaymentGatewayError, get_gateway
from integrations.payments.fake import FakePaymentGateway


def test_haversine_zero_distance():
    assert haversine_distance_m(-23.55, -46.63, -23.55, -46.63) == 0


def test_haversine_known_distance():
    # São Paulo → Rio de Janeiro ≈ 360 km
    distance = haversine_distance_m(-23.5505, -46.6333, -22.9068, -43.1729)
    assert 355_000 < distance < 365_000


def test_haversine_about_150_meters():
    # 0,00135° de latitude ≈ 150 m
    distance = haversine_distance_m(-23.55, -46.63, -23.55 + 0.00135, -46.63)
    assert 148 < distance < 152


def test_default_gateway_is_fake_and_shared():
    assert isinstance(get_gateway(), FakePaymentGateway)
    assert get_gateway() is get_gateway()


def test_fake_gateway_is_idempotent_per_key():
    gateway = FakePaymentGateway()
    first = gateway.hold(idempotency_key="k", amount_cents=100)
    second = gateway.hold(idempotency_key="k", amount_cents=100)
    assert first == second
    assert len(gateway.operations) == 1


def test_fake_gateway_can_simulate_outage():
    gateway = FakePaymentGateway()
    gateway.fail = True
    with pytest.raises(PaymentGatewayError):
        gateway.refund(idempotency_key="k", amount_cents=100)
