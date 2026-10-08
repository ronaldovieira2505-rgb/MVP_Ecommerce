import pytest
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError


@pytest.mark.django_db
def test_health_returns_ok(client):
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_503_when_database_is_down(client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("db down")

    monkeypatch.setattr("apps.core.views.connection.cursor", broken_cursor)

    response = client.get("/api/health/")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_custom_user_model_is_configured():
    assert get_user_model()._meta.label == "accounts.User"
