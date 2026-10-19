"""Dados de demonstração (BASE-03). Idempotente: rodar de novo não duplica nada."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.companies.models import Company, CompanyMember
from apps.companies.services import review_company
from apps.companies.state_machine import COMPANY_VERIFICATION_MACHINE
from apps.core.models import PlatformParameters, PlatformParametersChange
from apps.core.state_machine import record_creation
from apps.vacancies import application_services as applications
from apps.vacancies import services as vacancies
from apps.vacancies.models import Vacancy
from apps.workers.models import Worker
from apps.workers.services import review_worker
from apps.workers.state_machine import WORKER_VERIFICATION_MACHINE

User = get_user_model()

PASSWORD = "Demo@12345"
EMAIL_DOMAIN = "exemplo.com"

# Parâmetros em minutos para a demonstração ao vivo (--prazos-curtos).
SHORT_DEADLINES = {
    "min_publish_lead_minutes": 1,
    "applications_close_minutes_before": 1,
    "no_show_tolerance_minutes": 2,
    "contest_window_minutes": 2,
    "auto_checkout_minutes_after_end": 2,
}

ADMIN = {"email": f"admin@{EMAIL_DOMAIN}", "name": "Administrador Demo"}

# Empresas aprovadas, empresa pendente e prestadores. Documentos são gerados (nada real).
COMPANIES = [
    {
        "base": "11222333",
        "legal_name": "Armazéns Paulista Demo LTDA",
        "trade_name": "Armazéns Paulista",
        "owner": "Marina Souza",
        "email": f"empresa1@{EMAIL_DOMAIN}",
        "approved": True,
    },
    {
        "base": "22333444",
        "legal_name": "Eventos Centro Demo LTDA",
        "trade_name": "Eventos Centro",
        "owner": "Carlos Lima",
        "email": f"empresa2@{EMAIL_DOMAIN}",
        "approved": True,
    },
    {
        "base": "33444555",
        "legal_name": "Mercado Novo Demo LTDA",
        "trade_name": "Mercado Novo",
        "owner": "Paula Dias",
        "email": f"empresa.pendente@{EMAIL_DOMAIN}",
        "approved": False,
    },
]

WORKERS = [
    {
        "base": "111222333",
        "name": "Ana Prestadora Demo",
        "email": f"prestador1@{EMAIL_DOMAIN}",
        "lat": "-23.550520",
        "lng": "-46.633308",  # Praça da Sé
        "pix": ("EMAIL", f"prestador1@{EMAIL_DOMAIN}"),
        "approved": True,
    },
    {
        "base": "222333444",
        "name": "Bruno Prestador Demo",
        "email": f"prestador2@{EMAIL_DOMAIN}",
        "lat": "-23.561414",
        "lng": "-46.655881",  # Avenida Paulista (MASP)
        "pix": ("ALEATORIA", "7c9e6679-7425-40de-944b-e07fc1f90ae7"),
        "approved": True,
    },
    {
        "base": "333444555",
        "name": "Carla Prestadora Demo",
        "email": f"prestador3@{EMAIL_DOMAIN}",
        "lat": "-23.587416",
        "lng": "-46.657634",  # Parque Ibirapuera
        "pix": ("TELEFONE", "+5511999990003"),
        "approved": True,
    },
    {
        "base": "444555666",
        "name": "Diego Prestador Demo",
        "email": f"prestador.pendente@{EMAIL_DOMAIN}",
        "lat": "-23.534000",
        "lng": "-46.634000",
        "pix": ("ALEATORIA", "0b8f3c1e-52d4-4a77-9a3e-1d2c4b5a6f70"),
        "approved": False,
    },
]


def _check_digit(digits, weights):
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
    rest = total % 11
    return "0" if rest < 2 else str(11 - rest)


def make_cpf(base9):
    first = _check_digit(base9, range(10, 1, -1))
    second = _check_digit(base9 + first, range(11, 1, -1))
    return base9 + first + second


def make_cnpj(base8):
    base12 = base8 + "0001"
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    first = _check_digit(base12, w1)
    second = _check_digit(base12 + first, [6, *w1])
    return base12 + first + second


class Command(BaseCommand):
    help = "Cria dados de demonstração (idempotente). Use --prazos-curtos para a demo ao vivo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prazos-curtos",
            action="store_true",
            help="Ajusta os prazos da plataforma para minutos (demonstração ao vivo).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        admin = self._admin()
        companies = [self._company(spec, admin) for spec in COMPANIES]
        workers = [self._worker(spec, admin) for spec in WORKERS]
        if options["prazos_curtos"]:
            self._short_deadlines(admin)
        self._vacancies(companies, workers, admin, now)
        self._print_credentials(options["prazos_curtos"])

    def _admin(self):
        user = User.objects.filter(email__iexact=ADMIN["email"]).first()
        if user is None:
            user = User.objects.create_superuser(
                ADMIN["email"], ADMIN["email"], PASSWORD, first_name=ADMIN["name"]
            )
        return user

    def _company(self, spec, admin):
        cnpj = make_cnpj(spec["base"])
        company = Company.objects.filter(cnpj=cnpj).first()
        if company is not None:
            return company
        user = User.objects.create_user(
            spec["email"], spec["email"], PASSWORD, first_name=spec["owner"], role=Role.COMPANY
        )
        company = Company.objects.create(
            cnpj=cnpj,
            legal_name=spec["legal_name"],
            trade_name=spec["trade_name"],
            tax_regime=Company.TaxRegime.SIMPLES,
            registration_status="ATIVA",
            city="São Paulo",
            state="SP",
        )
        CompanyMember.objects.create(
            user=user, company=company, role=CompanyMember.MemberRole.OWNER
        )
        record_creation(company, COMPANY_VERIFICATION_MACHINE, actor=user, reason="Cadastro demo")
        if spec["approved"]:
            review_company(company, reviewer=admin, approve=True, reason="Dados de demonstração")
        return company

    def _worker(self, spec, admin):
        cpf = make_cpf(spec["base"])
        worker = Worker.objects.filter(cpf=cpf).first()
        if worker is not None:
            return worker
        user = User.objects.create_user(
            spec["email"], spec["email"], PASSWORD, first_name=spec["name"], role=Role.WORKER
        )
        pix_type, pix_key = spec["pix"]
        worker = Worker.objects.create(
            user=user,
            full_name=spec["name"],
            cpf=cpf,
            birth_date=date(1995, 5, 20),
            verification_status=Worker.VerificationStatus.IN_REVIEW,
            pix_key_type=pix_type,
            pix_key=pix_key,
            home_latitude=spec["lat"],
            home_longitude=spec["lng"],
        )
        record_creation(
            worker, WORKER_VERIFICATION_MACHINE, actor=user, reason="Cadastro demo"
        )
        if spec["approved"]:
            review_worker(worker, reviewer=admin, approve=True, reason="Dados de demonstração")
        return worker

    def _short_deadlines(self, admin):
        params = PlatformParameters.get()
        for field, value in SHORT_DEADLINES.items():
            old = getattr(params, field)
            if old == value:
                continue
            setattr(params, field, value)
            PlatformParametersChange.objects.create(
                field=field, old_value=str(old), new_value=str(value), changed_by=admin
            )
        params.save()

    def _vacancy(self, company, title, starts_at, hours, now, **fields):
        """Cria a vaga uma única vez (por empresa e título). Devolve (vaga, criada)."""
        existing = Vacancy.objects.filter(company=company, title=title).first()
        if existing is not None:
            return existing, False
        vacancy = vacancies.create_vacancy(
            company=company,
            now=now,
            title=title,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=hours),
            **fields,
        )
        return vacancy, True

    def _vacancies(self, companies, workers, admin, now):
        company_a, company_b = companies[0], companies[1]
        worker_a = workers[0]

        # 1. Publicada, 2 posições, R$ 100,00 (vaga do roteiro, perto da Praça da Sé).
        vacancy, created = self._vacancy(
            company_a,
            "Carga e descarga no Centro",
            now + timedelta(days=2),
            4,
            now,
            category="CARGA_DESCARGA",
            description="Descarregar um caminhão de caixas leves.",
            street="Praça da Sé",
            city="São Paulo",
            state="SP",
            latitude="-23.550520",
            longitude="-46.633308",
            pay_per_person_cents=10000,
            positions=2,
        )
        if created:
            vacancies.pay_vacancy(vacancy, now=now)

        # 2. Publicada, outra região e categoria.
        vacancy, created = self._vacancy(
            company_b,
            "Montagem de evento na Paulista",
            now + timedelta(days=3),
            6,
            now,
            category="EVENTOS",
            description="Montar estrutura de palco e cadeiras.",
            street="Avenida Paulista",
            city="São Paulo",
            state="SP",
            latitude="-23.561414",
            longitude="-46.655881",
            pay_per_person_cents=15000,
            positions=3,
        )
        if created:
            vacancies.pay_vacancy(vacancy, now=now)

        # 3. Publicada com um prestador aprovado (alocação CONFIRMADA).
        vacancy, created = self._vacancy(
            company_a,
            "Limpeza pós-obra no Ibirapuera",
            now + timedelta(days=1),
            5,
            now,
            category="LIMPEZA",
            description="Limpeza geral após reforma.",
            city="São Paulo",
            state="SP",
            latitude="-23.587416",
            longitude="-46.657634",
            pay_per_person_cents=12000,
            positions=1,
        )
        if created:
            vacancies.pay_vacancy(vacancy, now=now)
            application = applications.apply_to_vacancy(vacancy, worker_a, now=now)
            applications.approve_application(application, actor=None, now=now)

        # 4. Aguardando pagamento.
        self._vacancy(
            company_b,
            "Reposição de estoque no Mercadão",
            now + timedelta(days=4),
            4,
            now,
            category="VAREJO",
            description="Repor prateleiras e organizar o estoque.",
            city="São Paulo",
            state="SP",
            latitude="-23.541500",
            longitude="-46.629100",
            pay_per_person_cents=9000,
            positions=1,
        )

    def _print_credentials(self, short):
        out = self.stdout
        out.write(self.style.SUCCESS("Dados de demonstração prontos."))
        out.write(f"Senha de todos os usuários: {PASSWORD}")
        out.write(f"Admin (painel /admin): {ADMIN['email']}")
        for spec in COMPANIES:
            status = "aprovada" if spec["approved"] else "pendente na fila"
            out.write(f"Empresa ({status}): {spec['email']}")
        for spec in WORKERS:
            status = "aprovado" if spec["approved"] else "pendente na fila"
            out.write(f"Prestador ({status}): {spec['email']}")
        if short:
            out.write("Prazos curtos ativados (minutos). Veja docs/roteiro-demo.md.")
