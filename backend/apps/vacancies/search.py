"""Busca pública de vagas para o prestador (US12, US13, US14, US17)."""

import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies.application_services import has_overlap
from apps.vacancies.models import Application, Assignment, Vacancy
from apps.workers.models import Worker
from integrations.geo import haversine_distance_m

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
V = Vacancy.Status


def normalize(text):
    """Minúsculas e sem acentos, para a busca não diferenciar "Eletrica" de "Elétrica"."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def searchable_vacancies(now=None):
    """Vagas que aceitam candidaturas e ainda têm posição livre (lotadas ficam de fora)."""
    now = now or timezone.now()
    qs = (
        Vacancy.objects.filter(
            Q(status=V.PUBLISHED)
            | Q(
                reopened=True,
                ends_at__gt=now,
                status__in=(V.APPLICATIONS_CLOSED, V.IN_PROGRESS),
            )
        )
        .select_related("company", "custody")
        .annotate(
            filled=Count(
                "assignments", filter=Q(assignments__status__in=Assignment.ACTIVE_STATUSES)
            )
        )
    )
    return [v for v in qs if v.filled < v.positions and v.accepts_applications(now)]


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise DomainError(f"Data inválida em {name}; use AAAA-MM-DD.") from error


def _parse_coordinate(value, name, limit):
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise DomainError(f"Coordenada inválida em {name}.") from error
    if not -limit <= number <= limit:
        raise DomainError(f"Coordenada inválida em {name}.")
    return number


def parse_filters(params):
    """Lê os parâmetros da query string e valida (erro → DomainError)."""
    filters = {"q": (params.get("q") or "").strip()}
    category = params.get("category") or ""
    if category and category not in Vacancy.Category.values:
        raise DomainError("Categoria inválida.")
    filters["category"] = category
    filters["date_from"] = _parse_date(params["date_from"], "date_from") if params.get(
        "date_from"
    ) else None
    filters["date_to"] = _parse_date(params["date_to"], "date_to") if params.get(
        "date_to"
    ) else None
    min_pay = params.get("min_pay") or ""
    if min_pay:
        if not min_pay.isdigit():
            raise DomainError("Valor mínimo inválido; informe em centavos.")
        filters["min_pay"] = int(min_pay)
    else:
        filters["min_pay"] = None
    lat, lng = params.get("lat"), params.get("lng")
    if bool(lat) != bool(lng):
        raise DomainError("Informe latitude e longitude juntas.")
    filters["origin"] = (
        (_parse_coordinate(lat, "lat", 90), _parse_coordinate(lng, "lng", 180)) if lat else None
    )
    return filters


def search(params, now=None):
    """Aplica busca e filtros (todos combinados) e ordena por distância ou por início."""
    now = now or timezone.now()
    filters = parse_filters(params)
    fee = PlatformParameters.get()
    term = normalize(filters["q"])
    results = []
    for vacancy in searchable_vacancies(now):
        if term:
            haystack = normalize(
                f"{vacancy.title} {vacancy.description} {vacancy.get_category_display()}"
            )
            if term not in haystack:
                continue
        if filters["category"] and vacancy.category != filters["category"]:
            continue
        local_day = vacancy.starts_at.astimezone(LOCAL_TZ).date()
        if filters["date_from"] and local_day < filters["date_from"]:
            continue
        if filters["date_to"] and local_day > filters["date_to"]:
            continue
        net = fee.worker_net_cents(vacancy.pay_per_person_cents)
        if filters["min_pay"] is not None and net < filters["min_pay"]:
            continue
        distance = None
        if filters["origin"]:
            distance = haversine_distance_m(
                filters["origin"][0], filters["origin"][1], vacancy.latitude, vacancy.longitude
            )
        results.append((vacancy, distance))
    if filters["origin"]:
        results.sort(key=lambda item: (item[1], item[0].starts_at, item[0].pk))
    else:
        results.sort(key=lambda item: (item[0].starts_at, item[0].pk))
    return results


def serialize_card(vacancy, distance_m=None, params=None):
    params = params or PlatformParameters.get()
    gross = vacancy.pay_per_person_cents
    filled = getattr(vacancy, "filled", None)
    if filled is None:
        filled = vacancy.filled_positions
    return {
        "id": vacancy.pk,
        "title": vacancy.title,
        "company_name": vacancy.company.trade_name or vacancy.company.legal_name,
        "category": vacancy.category,
        "category_label": vacancy.get_category_display(),
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
        "district": vacancy.district,
        "city": vacancy.city,
        "state": vacancy.state,
        "gross_cents": gross,
        "fee_percent": params.worker_fee_percent,
        "fee_cents": params.worker_fee_cents(gross),
        "net_cents": params.worker_net_cents(gross),
        "remaining_positions": max(vacancy.positions - filled, 0),
        "payment_guaranteed": True,  # só aparece na busca vaga paga em custódia
        "urgent": vacancy.reopened,
        "distance_km": None if distance_m is None else round(distance_m / 1000, 1),
    }


def detail_vacancy(pk):
    """Vaga paga e ainda em curso, mesmo sem aceitar candidaturas (o botão explica o motivo)."""
    return (
        Vacancy.objects.filter(
            pk=pk, status__in=(V.PUBLISHED, V.APPLICATIONS_CLOSED, V.IN_PROGRESS)
        )
        .select_related("company", "custody")
        .annotate(
            filled=Count(
                "assignments", filter=Q(assignments__status__in=Assignment.ACTIVE_STATUSES)
            )
        )
        .first()
    )


def serialize_detail(vacancy, user, now=None):
    data = serialize_card(vacancy)
    worker = Worker.objects.filter(user=user).first() if user and user.is_authenticated else None
    mine = (
        Application.objects.filter(vacancy=vacancy, worker=worker).first() if worker else None
    )
    data.update(
        {
            "description": vacancy.description,
            "street": vacancy.street,
            "number": vacancy.number,
            "complement": vacancy.complement,
            "zip_code": vacancy.zip_code,
            "latitude": str(vacancy.latitude),
            "longitude": str(vacancy.longitude),
            "apply_blocker": apply_blocker(user, now, vacancy),
            "my_application": (
                {"id": mine.pk, "status": mine.status, "status_label": mine.get_status_display()}
                if mine
                else None
            ),
        }
    )
    data["can_apply"] = data["apply_blocker"] is None
    return data


def apply_blocker(user, now=None, vacancy=None):
    """Explica o que falta para o usuário poder se candidatar (None = pode)."""
    now = now or timezone.now()
    if not user or not user.is_authenticated:
        return "Entre como prestador para se candidatar."
    if user.role != Role.WORKER:
        return "Só prestadores podem se candidatar."
    worker = Worker.objects.filter(user=user).first()
    if worker is None:
        return "Complete seu cadastro de prestador para se candidatar."
    status = worker.verification_status
    S = Worker.VerificationStatus
    if status == S.PENDING_DOCUMENTS:
        return "Envie seu documento e a selfie para se candidatar."
    if status == S.IN_REVIEW:
        return "Seu cadastro está em verificação. Aguarde a aprovação para se candidatar."
    if status == S.REJECTED:
        return "Seu cadastro foi rejeitado. Reenvie os documentos para se candidatar."
    if not worker.pix_key:
        return "Cadastre sua chave PIX para se candidatar."
    if worker.is_suspended(now):
        return worker.suspension_message
    if vacancy is None:
        return None
    if Application.objects.filter(vacancy=vacancy, worker=worker).exists():
        return "Você já se candidatou a esta vaga."
    if not vacancy.accepts_applications(now):
        return "As candidaturas desta vaga estão encerradas."
    if vacancy.filled_positions >= vacancy.positions:
        return "Esta vaga está lotada."
    if has_overlap(worker, vacancy):
        return "Você já tem um turno nesse horário."
    return None
