"""Cadastro e verificação (triagem manual) da empresa."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.companies.models import Company, CompanyMember
from apps.companies.state_machine import COMPANY_VERIFICATION_MACHINE
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters, VerificationReview
from apps.core.notifications import notify_company
from apps.core.state_machine import transition
from integrations.cnpj import CnpjLookupError, get_cnpj_lookup

S = Company.VerificationStatus

CNPJ_ALREADY_REGISTERED = "Já existe uma conta para este CNPJ"
EMAIL_ALREADY_REGISTERED = "Já existe uma conta com este e-mail"


class CnpjAlreadyRegistered(DomainError):
    pass


class EmailAlreadyRegistered(DomainError):
    pass


def lookup_cnpj(cnpj):
    """Consulta a BrasilAPI com o limite lido de `PlatformParameters`. Lança `CnpjLookupError`."""
    timeout = PlatformParameters.get().cnpj_lookup_timeout_seconds
    return get_cnpj_lookup().lookup(cnpj, timeout=timeout)


COMPANY_FIELDS = (
    "legal_name",
    "trade_name",
    "registration_status",
    "street",
    "number",
    "complement",
    "district",
    "city",
    "state",
    "zip_code",
    "state_registration",
    "tax_regime",
    "phone",
    "preferred_payment_method",
)


def register_company(*, cnpj, owner_name, email, password, **fields):
    """Cria User (COMPANY), Company (PENDENTE) e CompanyMember (OWNER).

    A consulta de CNPJ é refeita aqui, no servidor: se falhar, a empresa fica marcada como
    `data_unverified` para o admin conferir (nunca confiamos no cliente para isso).
    """
    if Company.objects.filter(cnpj=cnpj).exists():
        raise CnpjAlreadyRegistered(CNPJ_ALREADY_REGISTERED)
    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        raise EmailAlreadyRegistered(EMAIL_ALREADY_REGISTERED)
    try:
        lookup_cnpj(cnpj)
        data_unverified = False
    except CnpjLookupError:
        data_unverified = True
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=owner_name[:150],
                role=Role.COMPANY,
            )
            company = Company.objects.create(
                cnpj=cnpj,
                data_unverified=data_unverified,
                verification_status=S.PENDING,
                **{name: fields.get(name, "") for name in COMPANY_FIELDS},
            )
            CompanyMember.objects.create(
                user=user, company=company, role=CompanyMember.MemberRole.OWNER
            )
    except IntegrityError as error:  # corrida: outro cadastro com o mesmo CNPJ/e-mail
        if Company.objects.filter(cnpj=cnpj).exists():
            raise CnpjAlreadyRegistered(CNPJ_ALREADY_REGISTERED) from error
        raise EmailAlreadyRegistered(EMAIL_ALREADY_REGISTERED) from error
    return company


@transaction.atomic
def review_company(company, *, reviewer, approve, reason="", now=None):
    if not approve and not reason.strip():
        raise DomainError("O motivo é obrigatório na rejeição.")
    decision = (
        VerificationReview.Decision.APPROVED if approve else VerificationReview.Decision.REJECTED
    )
    company = transition(
        company,
        COMPANY_VERIFICATION_MACHINE,
        S.APPROVED if approve else S.REJECTED,
        actor=reviewer,
        reason=reason,
        now=now,
    )
    VerificationReview.objects.create(
        subject_type=VerificationReview.SubjectType.COMPANY,
        subject_id=company.pk,
        reviewer=reviewer,
        decision=decision,
        reason=reason,
        created_at=now or timezone.now(),
    )
    notify_company(
        company,
        "VERIFICACAO",
        "Cadastro aprovado" if approve else "Cadastro rejeitado",
        reason,
    )
    return company


@transaction.atomic
def resubmit_company(company, *, actor=None, now=None):
    """REJEITADA → PENDENTE: a empresa corrigiu os dados."""
    return transition(
        company,
        COMPANY_VERIFICATION_MACHINE,
        S.PENDING,
        actor=actor,
        reason="Dados corrigidos pela empresa",
        now=now,
    )
