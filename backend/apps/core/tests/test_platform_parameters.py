import pytest
from django.contrib import admin
from django.urls import reverse

from apps.core.admin import PlatformParametersForm, humanize_minutes
from apps.core.models import PlatformParameters, PlatformParametersChange
from apps.core.tests.factories import make_admin

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = make_admin()
    client.force_login(user)
    return user


def payload(**overrides):
    form = PlatformParametersForm(instance=PlatformParameters.get())
    data = {name: form.initial.get(name, getattr(form.instance, name)) for name in form.fields}
    data.update(overrides)
    return data


def change_url():
    return reverse("admin:core_platformparameters_change", args=[1])


def test_page_shows_labels_units_and_readable_values(client, staff):
    html = client.get(change_url()).content.decode().lower()
    for text in [
        "janela de contestação (min)",
        "raio do check-in (m)",
        "janela de faltas (dias)",
        "taxa retida do prestador (%)",
        "valor atual: 720 min = 12 h",
        "valor atual: 1440 min = 1 dia",
    ]:
        assert text in html


def test_valid_change_applies_immediately_and_is_audited(client, staff):
    response = client.post(change_url(), payload(contest_window_minutes=2, worker_fee_percent=5))

    assert response.status_code == 302
    params = PlatformParameters.get()
    assert params.contest_window_minutes == 2
    assert params.worker_fee_cents(10000) == 500
    changes = {c.field: c for c in PlatformParametersChange.objects.all()}
    assert set(changes) == {"contest_window_minutes", "worker_fee_percent"}
    contest = changes["contest_window_minutes"]
    assert (contest.old_value, contest.new_value) == ("1440", "2")
    assert contest.changed_by == staff and contest.changed_at
    fee = changes["worker_fee_percent"]
    assert (fee.old_value, fee.new_value) == ("3", "5")


def test_unchanged_save_creates_no_audit(client, staff):
    client.post(change_url(), payload())
    assert not PlatformParametersChange.objects.exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"contest_window_minutes": -1},
        {"contest_window_minutes": 0},
        {"payment_deadline_minutes": 0},
        {"geofence_radius_m": 0},
        {"no_show_limit": 0},
        {"min_publish_lead_minutes": -5},
        {"worker_fee_percent": 101},
        {"worker_fee_percent": -1},
    ],
)
def test_invalid_values_show_error_and_change_nothing(client, staff, overrides):
    before = PlatformParameters.objects.values().get()
    response = client.post(change_url(), payload(**overrides))

    assert response.status_code == 200
    assert "errornote" in response.content.decode()
    assert PlatformParameters.objects.values().get() == before
    assert not PlatformParametersChange.objects.exists()


def test_zero_is_accepted_where_it_makes_sense(client, staff):
    data = payload(min_publish_lead_minutes=0, no_show_tolerance_minutes=0, worker_fee_percent=0)
    assert client.post(change_url(), data).status_code == 302
    assert PlatformParameters.get().worker_fee_percent == 0


def test_parameter_changes_are_read_only():
    model_admin = admin.site._registry[PlatformParametersChange]
    assert not model_admin.has_add_permission(None)
    assert not model_admin.has_change_permission(None)
    assert not model_admin.has_delete_permission(None)


@pytest.mark.parametrize(
    ("minutes", "text"),
    [
        (720, "720 min = 12 h"),
        (1440, "1440 min = 1 dia"),
        (90, "90 min = 1 h 30 min"),
        (2, "2 min = 2 min"),
    ],
)
def test_humanize_minutes(minutes, text):
    assert humanize_minutes(minutes) == text
