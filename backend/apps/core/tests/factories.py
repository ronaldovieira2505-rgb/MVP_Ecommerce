"""Funções de apoio para montar cenários nos testes."""

from datetime import date, datetime, timedelta, timezone
from itertools import count

from django.contrib.auth import get_user_model

from apps.accounts.models import Role
from apps.companies.models import Company, CompanyMember
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies import services as vacancies
from apps.workers.models import Worker

User = get_user_model()
_seq = count(1)

# Origem dos testes: um instante fixo em UTC.
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
LAT, LNG = -23.55052, -46.633308  # Praça da Sé, São Paulo


def make_user(role=Role.WORKER, **kw):
    n = next(_seq)
    return User.objects.create_user(
        f"user{n}", f"user{n}@example.com", "senha-forte-123", role=role, **kw
    )


def make_admin():
    return User.objects.create_superuser("admin", "admin@example.com", "senha-forte-123")


def make_company(approved=True):
    n = next(_seq)
    company = Company.objects.create(
        cnpj=f"{n:08d}000100"[:14],
        legal_name=f"Empresa {n} LTDA",
        tax_regime=Company.TaxRegime.SIMPLES,
        verification_status=(
            Company.VerificationStatus.APPROVED if approved else Company.VerificationStatus.PENDING
        ),
    )
    CompanyMember.objects.create(user=make_user(Role.COMPANY), company=company)
    return company


def make_worker(approved=True, **kw):
    n = next(_seq)
    return Worker.objects.create(
        user=make_user(),
        full_name=f"Prestador {n}",
        cpf=f"{n:011d}",
        birth_date=date(1995, 1, 1),
        pix_key_type="ALEATORIA",
        pix_key=f"pix-{n}-abcdef",
        verification_status=(
            Worker.VerificationStatus.APPROVED if approved else "PENDENTE_DOCUMENTOS"
        ),
        **kw,
    )


def vacancy_fields(starts_at, hours=4, **kw):
    fields = {
        "title": "Carga e descarga",
        "category": "CARGA_DESCARGA",
        "description": "Descarregar caminhão",
        "latitude": LAT,
        "longitude": LNG,
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(hours=hours),
        "pay_per_person_cents": 10000,
        "positions": 1,
    }
    fields.update(kw)
    return fields


def make_published_vacancy(company=None, starts_in_hours=48, now=NOW, **kw):
    company = company or make_company()
    vacancy = vacancies.create_vacancy(
        company=company,
        now=now,
        **vacancy_fields(now + timedelta(hours=starts_in_hours), **kw),
    )
    return vacancies.pay_vacancy(vacancy, now=now)


def make_assignment(vacancy=None, worker=None, now=NOW, **kw):
    """Alocação CONFIRMADA (candidatura aprovada)."""
    vacancy = vacancy or make_published_vacancy(now=now, **kw)
    worker = worker or make_worker()
    application = applications.apply_to_vacancy(vacancy, worker, now=now)
    return applications.approve_application(application, actor=None, now=now)


def make_paid_ready_assignment(now=NOW):
    """Alocação APROVADA, pronta para liquidar (custódia RETIDA)."""
    assignment = make_assignment(now=now)
    start = assignment.vacancy.starts_at
    assignments.check_in(assignment, lat=LAT, lng=LNG, now=start)
    assignments.check_out(assignment, now=start + timedelta(hours=4))
    assignments.approve_hours(assignment, now=start + timedelta(hours=5))
    return assignment

