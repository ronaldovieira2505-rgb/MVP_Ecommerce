import pytest
from django.contrib import admin
from django.urls import reverse

from apps.core.models import StateTransition
from apps.core.tests.factories import make_admin, make_assignment
from apps.payments.models import LedgerEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    client.force_login(make_admin())
    return client


@pytest.mark.parametrize("model", [StateTransition, LedgerEntry])
def test_audit_models_are_read_only(model):
    model_admin = admin.site._registry[model]
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


def test_main_models_are_registered_in_admin():
    from django.apps import apps

    for app, name in [
        ("companies", "Company"),
        ("workers", "Worker"),
        ("vacancies", "Vacancy"),
        ("vacancies", "Application"),
        ("vacancies", "Assignment"),
        ("payments", "Custody"),
        ("core", "PlatformParameters"),
        ("core", "Notification"),
    ]:
        assert apps.get_model(app, name) in admin.site._registry


def test_admin_index_is_in_portuguese(admin_client):
    response = admin_client.get("/admin/")
    assert response.status_code == 200
    assert "Conecta Já" in response.content.decode()


def test_ledger_changelist_is_view_only(admin_client):
    make_assignment()
    response = admin_client.get(reverse("admin:payments_ledgerentry_changelist"))
    assert response.status_code == 200
    assert "/admin/payments/ledgerentry/add/" not in response.content.decode()
    assert admin_client.get("/admin/payments/ledgerentry/add/").status_code == 403


def test_process_deadlines_button_is_shown_and_works(admin_client):
    response = admin_client.get(reverse("admin:core_statetransition_changelist"))
    assert "Processar prazos agora" in response.content.decode()

    response = admin_client.post(reverse("admin:processar_prazos"), follow=True)
    assert response.status_code == 200
    assert "Prazos processados" in response.content.decode()


def test_process_deadlines_requires_post(admin_client):
    assert admin_client.get(reverse("admin:processar_prazos")).status_code == 405
