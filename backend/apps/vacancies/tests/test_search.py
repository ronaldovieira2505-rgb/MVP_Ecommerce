"""US12 (busca), US13 (filtros), US14 (proximidade) e US17 (valor líquido)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.tests.factories import (
    LAT,
    LNG,
    make_assignment,
    make_company,
    make_published_vacancy,
    make_worker,
    vacancy_fields,
)
from apps.vacancies import services as vacancy_services
from apps.vacancies.models import Vacancy

pytestmark = pytest.mark.django_db

URL = "/api/vacancies/"


def now():
    return timezone.now()


def published(**kw):
    return make_published_vacancy(now=now(), **kw)


def results(client=None, **params):
    response = (client or APIClient()).get(URL, params)
    assert response.status_code == 200, response.content
    return response.json()["results"]


def test_card_shows_net_value_fee_positions_and_guarantee():
    vacancy = published(positions=2)
    vacancy.company.trade_name = "Mercado Bom"
    vacancy.company.save()
    [card] = results()
    assert card["id"] == vacancy.pk
    assert card["company_name"] == "Mercado Bom"
    assert card["gross_cents"] == 10000
    assert card["fee_percent"] == 3
    assert card["fee_cents"] == 300
    assert card["net_cents"] == 9700
    assert card["remaining_positions"] == 2
    assert card["payment_guaranteed"] is True
    assert card["urgent"] is False


def test_net_value_follows_platform_parameter():
    from apps.core.models import PlatformParameters

    params = PlatformParameters.get()
    params.worker_fee_percent = 10
    params.save()
    published()
    [card] = results()
    assert card["net_cents"] == 9000


def test_hides_unpaid_cancelled_and_full_vacancies():
    published(title="Visível")
    full = published(title="Lotada", positions=1)
    make_assignment(vacancy=full, now=now())
    removed = published(title="Removida")
    vacancy_services.remove_vacancy(removed)
    vacancy_services.create_vacancy(
        company=make_company(),
        **vacancy_fields(now() + timedelta(hours=48), title="Sem pagamento"),
    )
    titles = [c["title"] for c in results()]
    assert titles == ["Visível"]


def test_search_term_ignores_case_and_accents():
    published(title="Ajudante de elétrica", category="AJUDANTE_OBRA")
    published(title="Garçom", description="Servir mesas", category="EVENTOS")
    assert [c["title"] for c in results(q="ELETRICA")] == ["Ajudante de elétrica"]
    assert [c["title"] for c in results(q="mesas")] == ["Garçom"]
    assert [c["title"] for c in results(q="eventos")] == ["Garçom"]
    assert results(q="fotografia") == []


def test_filters_are_combined():
    soon = published(title="Amanhã", starts_in_hours=24, category="LIMPEZA")
    published(title="Depois", starts_in_hours=24 * 5, category="LIMPEZA")
    published(title="Outra categoria", starts_in_hours=24, category="VAREJO")
    published(title="Barata", starts_in_hours=24, category="LIMPEZA", pay_per_person_cents=5000)
    day = timezone.localtime(soon.starts_at).date().isoformat()
    found = results(category="LIMPEZA", date_from=day, date_to=day, min_pay=9000)
    assert [c["title"] for c in found] == ["Amanhã"]
    # combinado com a busca por texto
    assert results(category="VAREJO", q="amanhã") == []
    assert [c["title"] for c in results(category="LIMPEZA", q="barata")] == ["Barata"]


def test_invalid_filter_returns_400():
    assert APIClient().get(URL, {"date_from": "31/12/2026"}).status_code == 400
    assert APIClient().get(URL, {"category": "XPTO"}).status_code == 400
    assert APIClient().get(URL, {"lat": "-23.5"}).status_code == 400


def test_nearest_first_with_distance_in_km():
    far = published(title="Longe", latitude=LAT + 0.1, longitude=LNG, starts_in_hours=24)
    near = published(title="Perto", latitude=LAT + 0.01, longitude=LNG, starts_in_hours=72)
    found = results(lat=str(LAT), lng=str(LNG))
    assert [c["id"] for c in found] == [near.pk, far.pk]
    assert found[0]["distance_km"] == pytest.approx(1.1, abs=0.1)
    assert found[1]["distance_km"] == pytest.approx(11.1, abs=0.2)


def test_without_location_orders_by_start():
    later = published(title="Depois", starts_in_hours=72)
    sooner = published(title="Antes", starts_in_hours=24)
    found = results()
    assert [c["id"] for c in found] == [sooner.pk, later.pk]
    assert found[0]["distance_km"] is None


def test_reopened_vacancy_shows_urgent():
    vacancy = published()
    vacancy.positions = 2
    vacancy.reopened = True
    vacancy.status = Vacancy.Status.APPLICATIONS_CLOSED
    vacancy.save()
    [card] = results()
    assert card["urgent"] is True


def test_detail_has_full_description_address_and_values():
    vacancy = published(description="Descarregar 2 caminhões", street="Praça da Sé")
    data = APIClient().get(f"{URL}{vacancy.pk}/").json()
    assert data["description"] == "Descarregar 2 caminhões"
    assert data["street"] == "Praça da Sé"
    assert data["latitude"] and data["longitude"]
    assert (data["gross_cents"], data["fee_cents"], data["net_cents"]) == (10000, 300, 9700)


def test_detail_of_unpublished_vacancy_is_404():
    vacancy = published()
    vacancy_services.remove_vacancy(vacancy)
    assert APIClient().get(f"{URL}{vacancy.pk}/").status_code == 404


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("anonymous", "Entre como prestador"),
        ("pending_docs", "Envie seu documento"),
        ("in_review", "em verificação"),
        ("no_pix", "chave PIX"),
        ("suspended", "suspensa até"),
        ("approved", None),
    ],
)
def test_apply_button_explains_what_is_missing(setup, message):
    vacancy = published()
    client = APIClient()
    if setup != "anonymous":
        worker = make_worker(approved=setup != "pending_docs")
        if setup == "in_review":
            worker.verification_status = "EM_ANALISE"
        if setup == "no_pix":
            worker.pix_key = ""
        if setup == "suspended":
            worker.suspended_until = now() + timedelta(days=3)
        worker.save()
        client.force_login(worker.user)
    data = client.get(f"{URL}{vacancy.pk}/").json()
    if message is None:
        assert data["can_apply"] is True
        assert data["apply_blocker"] is None
    else:
        assert data["can_apply"] is False
        assert message in data["apply_blocker"]


def test_company_still_gets_its_own_detail():
    vacancy = published()
    client = APIClient()
    client.force_login(vacancy.company.members.first().user)
    data = client.get(f"{URL}{vacancy.pk}/").json()
    assert "custody_status" in data  # visão da empresa (US20), não a pública


def test_create_still_requires_company():
    worker = make_worker()
    client = APIClient()
    client.force_login(worker.user)
    assert client.post(URL, {}, format="json").status_code == 403
