import re
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role
from apps.companies.models import Company
from apps.core.models import PlatformParameters
from apps.core.validators import is_valid_cnpj, is_valid_cpf
from apps.vacancies.models import Assignment, Vacancy
from apps.workers.models import Worker

pytestmark = pytest.mark.django_db

User = get_user_model()


def run_seed(*args):
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def test_creates_demo_data_on_empty_database():
    output = run_seed()

    assert User.objects.filter(role=Role.ADMIN, is_superuser=True).count() == 1
    approved_companies = Company.objects.filter(verification_status="APROVADA")
    assert approved_companies.count() == 4
    assert Company.objects.filter(verification_status="PENDENTE").count() == 1
    approved_workers = Worker.objects.filter(verification_status="APROVADO")
    assert approved_workers.count() == 3
    assert all(w.pix_key for w in approved_workers)
    assert Worker.objects.filter(verification_status="EM_ANALISE").count() == 1

    vacancies = Vacancy.objects.all()
    assert vacancies.count() == 14
    assert len({v.status for v in vacancies}) >= 2
    for vacancy in vacancies:
        assert -24.1 < float(vacancy.latitude) < -23.2
        assert -46.9 < float(vacancy.longitude) < -46.3
    assert Assignment.objects.filter(status="CONFIRMADA").count() == 1

    assert "admin@exemplo.com" in output
    assert "Demo@12345" in output


def test_demo_data_has_valid_documents_and_fake_emails():
    run_seed()

    assert all(is_valid_cnpj(c.cnpj) for c in Company.objects.all())
    assert all(is_valid_cpf(w.cpf) for w in Worker.objects.all())
    assert all(u.email.endswith("@exemplo.com") for u in User.objects.all())


def test_running_twice_does_not_duplicate():
    run_seed()
    counts = (
        User.objects.count(),
        Company.objects.count(),
        Worker.objects.count(),
        Vacancy.objects.count(),
        Assignment.objects.count(),
    )

    run_seed()

    assert counts == (
        User.objects.count(),
        Company.objects.count(),
        Worker.objects.count(),
        Vacancy.objects.count(),
        Assignment.objects.count(),
    )


def test_short_deadlines_sets_minutes_parameters():
    run_seed("--prazos-curtos")

    params = PlatformParameters.get()
    assert params.min_publish_lead_minutes == 1
    assert params.applications_close_minutes_before == 1
    assert params.no_show_tolerance_minutes == 2
    assert params.contest_window_minutes == 2
    assert params.auto_checkout_minutes_after_end == 2


def test_without_flag_keeps_default_deadlines():
    run_seed()

    params = PlatformParameters.get()
    assert params.min_publish_lead_minutes == 720
    assert params.contest_window_minutes == 1440


def test_credentials_can_log_in(client):
    output = run_seed()
    password = re.search(r"Senha de todos os usuários: (\S+)", output).group(1)

    response = client.post(
        "/api/auth/login/",
        {"email": "prestador1@exemplo.com", "password": password},
        content_type="application/json",
    )

    assert response.status_code == 200


def test_catalog_has_varied_published_ads_with_urgent_one():
    run_seed()

    published = Vacancy.objects.filter(status=Vacancy.Status.PUBLISHED)
    assert published.count() >= 12
    assert len({v.category for v in published}) >= 5
    assert len({v.company_id for v in published}) >= 4
    assert published.filter(reopened=True).count() == 1
    assert all(v.starts_at > timezone.now() for v in published)


def test_catalog_respects_lead_time_when_run_at_night():
    # 20:00 em São Paulo: os turnos de "amanhã" às 6h e 7h ficariam a menos de 12h.
    night = datetime(2026, 10, 19, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    with patch("django.utils.timezone.now", return_value=night):
        run_seed()

    lead = timedelta(minutes=PlatformParameters.get().min_publish_lead_minutes)
    assert Vacancy.objects.count() == 14
    assert all(v.starts_at >= night + lead for v in Vacancy.objects.all())
