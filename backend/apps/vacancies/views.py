"""API de vagas da empresa: criar, pagar (publicar), listar e detalhar."""

from decimal import Decimal

from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.companies.models import Company
from apps.companies.views import first_error
from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.core.permissions import IsCompanyUser
from apps.payments import services as payments
from apps.payments.models import Custody, LedgerEntry
from apps.vacancies import search, services
from apps.vacancies.models import Assignment, Vacancy
from integrations.payments import PaymentGatewayError

PENDING_COMPANY = "Cadastro em análise"
REJECTED_COMPANY = "Cadastro rejeitado. Corrija os dados do cadastro para publicar vagas."
NO_COMPANY = "Acesso restrito a empresas."
MIN_PAY_CENTS = 100
MIN_PAY_MESSAGE = "O valor mínimo por pessoa é R$ 1,00."


def company_of(user):
    membership = user.company_memberships.select_related("company").first()
    return membership.company if membership else None


class VacancySerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    category = serializers.ChoiceField(choices=Vacancy.Category.choices)
    description = serializers.CharField()
    street = serializers.CharField(max_length=200, required=False, allow_blank=True)
    number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    complement = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=2, required=False, allow_blank=True)
    zip_code = serializers.RegexField(r"^\d{0,8}$", required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal("-90"), max_value=Decimal("90")
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=Decimal("-180"), max_value=Decimal("180")
    )
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    pay_per_person_cents = serializers.IntegerField(
        min_value=MIN_PAY_CENTS, error_messages={"min_value": MIN_PAY_MESSAGE}
    )
    positions = serializers.IntegerField(
        min_value=1, error_messages={"min_value": "É preciso ao menos 1 pessoa."}
    )


def _retained_cents(vacancy):
    """Valor ainda retido no PSP: só existe com a custódia RETIDA."""
    custody = getattr(vacancy, "custody", None)
    if custody is None or custody.status != Custody.Status.HELD:
        return 0
    totals = payments.total_by_kind(custody)
    K = LedgerEntry.Kind
    used = sum(totals.get(k, 0) for k in (K.WORKER_PAYOUT, K.PLATFORM_FEE, K.COMPANY_REFUND))
    return custody.amount_cents - used


def serialize_vacancy(vacancy):
    filled = getattr(vacancy, "filled", None)
    if filled is None:
        filled = vacancy.filled_positions
    custody = getattr(vacancy, "custody", None)
    return {
        "id": vacancy.pk,
        "title": vacancy.title,
        "category": vacancy.category,
        "category_label": vacancy.get_category_display(),
        "description": vacancy.description,
        "street": vacancy.street,
        "number": vacancy.number,
        "complement": vacancy.complement,
        "district": vacancy.district,
        "city": vacancy.city,
        "state": vacancy.state,
        "zip_code": vacancy.zip_code,
        "latitude": str(vacancy.latitude),
        "longitude": str(vacancy.longitude),
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
        "pay_per_person_cents": vacancy.pay_per_person_cents,
        "positions": vacancy.positions,
        "filled_positions": filled,
        "total_cents": vacancy.pay_per_person_cents * vacancy.positions,
        "retained_cents": _retained_cents(vacancy),
        "custody_status": custody.status if custody else None,
        "status": vacancy.status,
        "status_label": vacancy.get_status_display(),
        "created_at": vacancy.created_at.isoformat(),
    }


class CompanyAreaView(APIView):
    """Base: sessão, papel EMPRESA e vínculo (membership) com a empresa."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsCompanyUser]

    def company(self, request):
        return company_of(request.user)

    def vacancies(self, company):
        return (
            Vacancy.objects.filter(company=company)
            .select_related("custody")
            .annotate(
                filled=Count(
                    "assignments",
                    filter=Q(assignments__status__in=Assignment.ACTIVE_STATUSES),
                )
            )
        )


def forbidden_company(company):
    """Resposta 403 quando a empresa ainda não pode publicar; None se está aprovada."""
    if company is None:
        return Response({"detail": NO_COMPANY}, status=403)
    if company.verification_status == Company.VerificationStatus.PENDING:
        return Response({"detail": PENDING_COMPANY}, status=403)
    if company.verification_status != Company.VerificationStatus.APPROVED:
        return Response({"detail": REJECTED_COMPANY}, status=403)
    return None


class PublicReadMixin:
    """GET é público (busca do prestador, US12); os demais métodos exigem empresa."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return super().get_permissions()


@method_decorator(csrf_protect, name="dispatch")
class VacancyCreateView(PublicReadMixin, CompanyAreaView):
    def get(self, request):
        """Busca: ?q=&category=&date_from=&date_to=&min_pay=&lat=&lng= (US12/13/14/17)."""
        try:
            found = search.search(request.query_params)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        params = PlatformParameters.get()
        return Response(
            {"results": [search.serialize_card(v, d, params) for v, d in found]}
        )

    def post(self, request):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        serializer = VacancySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": first_error(serializer.errors), "errors": serializer.errors}, status=400
            )
        try:
            vacancy = services.create_vacancy(
                company=company, actor=request.user, **serializer.validated_data
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        vacancy = self.vacancies(company).get(pk=vacancy.pk)
        return Response(serialize_vacancy(vacancy), status=201)


@method_decorator(csrf_protect, name="dispatch")
class VacancyPayView(CompanyAreaView):
    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        vacancy = self.vacancies(company).filter(pk=pk).first()
        if vacancy is None:  # de outra empresa: não revela que existe
            return Response({"detail": "Vaga não encontrada."}, status=404)
        try:
            services.pay_vacancy(vacancy, actor=request.user)
        except PaymentGatewayError as error:
            return Response({"detail": str(error)}, status=502)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        vacancy = self.vacancies(company).get(pk=pk)
        data = serialize_vacancy(vacancy)
        data["payment_method"] = company.preferred_payment_method
        return Response(data)


class VacancyEditSerializer(serializers.Serializer):
    """Campos editáveis; valor por pessoa e posições ficam de fora (somente leitura)."""

    title = serializers.CharField(max_length=150, required=False)
    category = serializers.ChoiceField(choices=Vacancy.Category.choices, required=False)
    description = serializers.CharField(required=False)
    street = serializers.CharField(max_length=200, required=False, allow_blank=True)
    number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    complement = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=2, required=False, allow_blank=True)
    zip_code = serializers.RegexField(r"^\d{0,8}$", required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
        required=False,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
        required=False,
    )
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)


READ_ONLY_FIELDS = ("pay_per_person_cents", "positions")
READ_ONLY_MESSAGE = (
    "Para alterar valor ou número de pessoas, remova o anúncio (estorno total) e publique um novo."
)


class VacancyDetailView(PublicReadMixin, CompanyAreaView):
    @method_decorator(csrf_protect)
    def patch(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        vacancy = self.vacancies(company).filter(pk=pk).first()
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        if any(name in request.data for name in READ_ONLY_FIELDS):
            return Response({"detail": READ_ONLY_MESSAGE}, status=400)
        serializer = VacancyEditSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {"detail": first_error(serializer.errors), "errors": serializer.errors}, status=400
            )
        try:
            services.edit_vacancy(vacancy, actor=request.user, **serializer.validated_data)
        except services.VacancyLockedError as error:
            return Response({"detail": str(error)}, status=409)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        data = serialize_vacancy(self.vacancies(company).get(pk=pk))
        data["payment_method"] = company.preferred_payment_method
        return Response(data)

    def get(self, request, pk):
        user = request.user
        if not (user.is_authenticated and user.role == Role.COMPANY):
            return self.public_detail(request, pk)
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        vacancy = self.vacancies(company).filter(pk=pk).first()
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        data = serialize_vacancy(vacancy)
        data["payment_method"] = company.preferred_payment_method
        return Response(data)


    def public_detail(self, request, pk):
        """Detalhe para o prestador: só vagas que aparecem na busca (US12/US17)."""
        vacancy = search.detail_vacancy(pk)
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        return Response(search.serialize_detail(vacancy, request.user))


@method_decorator(csrf_protect, name="dispatch")
class VacancyRemoveView(CompanyAreaView):
    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        vacancy = self.vacancies(company).filter(pk=pk).first()
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        try:
            services.remove_vacancy(vacancy, actor=request.user)
        except PaymentGatewayError as error:
            return Response({"detail": str(error)}, status=502)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_vacancy(self.vacancies(company).get(pk=pk)))


class CompanyVacancyListView(CompanyAreaView):
    def get(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        vacancies = list(self.vacancies(company).order_by("-starts_at", "-pk"))
        results = [serialize_vacancy(v) for v in vacancies]
        return Response(
            {
                "total_retained_cents": sum(r["retained_cents"] for r in results),
                "results": results,
            }
        )
