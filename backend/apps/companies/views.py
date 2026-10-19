from dataclasses import asdict

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.companies import services
from apps.companies.models import Company
from apps.core.validators import validate_cnpj
from integrations.cnpj import CnpjLookupError, CnpjNotFound

INVALID_CNPJ = "CNPJ inválido"
LOOKUP_UNAVAILABLE = (
    "Não foi possível consultar o CNPJ agora. Preencha os dados manualmente; "
    "a equipe vai conferi-los na análise do cadastro."
)


def digits_only(value):
    return "".join(c for c in str(value) if c.isdigit())


def clean_cnpj(value):
    """Aceita máscara; devolve só dígitos ou None se os dígitos verificadores não fecham."""
    cnpj = digits_only(value)
    try:
        validate_cnpj(cnpj)
    except DjangoValidationError:
        return None
    return cnpj


class CnpjField(serializers.CharField):
    def to_internal_value(self, data):
        cnpj = clean_cnpj(super().to_internal_value(data))
        if cnpj is None:
            raise serializers.ValidationError(INVALID_CNPJ)
        return cnpj


class CompanyRegistrationSerializer(serializers.Serializer):
    cnpj = CnpjField()
    legal_name = serializers.CharField(max_length=200)
    trade_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    registration_status = serializers.CharField(max_length=40, required=False, allow_blank=True)
    street = serializers.CharField(max_length=200, required=False, allow_blank=True)
    number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    complement = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=2, required=False, allow_blank=True)
    zip_code = serializers.CharField(max_length=9, required=False, allow_blank=True)
    # Cadastro simplificado: inscrição estadual, telefone e meio de pagamento são opcionais.
    state_registration = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    tax_regime = serializers.ChoiceField(choices=Company.TaxRegime.choices)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    preferred_payment_method = serializers.ChoiceField(
        choices=Company.PaymentMethod.choices, required=False, allow_blank=True, default=""
    )
    owner_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)

    def validate_state_registration(self, value):
        return "ISENTO" if value.strip().upper() == "ISENTO" else value.strip()

    def validate_zip_code(self, value):
        return digits_only(value)

    def validate_email(self, value):
        return value.strip().lower()


def first_error(errors):
    for messages in errors.values():
        if messages:
            return str(messages[0])
    return "Verifique os dados informados."


class CnpjLookupView(APIView):
    """Pré-preenche o cadastro. Público: o visitante ainda não tem conta."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, cnpj):
        digits = clean_cnpj(cnpj)
        if digits is None:
            return Response({"detail": INVALID_CNPJ}, status=400)
        if Company.objects.filter(cnpj=digits).exists():
            return Response({"detail": services.CNPJ_ALREADY_REGISTERED}, status=409)
        try:
            data = services.lookup_cnpj(digits)
        except CnpjNotFound:
            return Response({"found": False, "available": True, "detail": "CNPJ não encontrado."})
        except CnpjLookupError:
            return Response({"found": False, "available": False, "detail": LOOKUP_UNAVAILABLE})
        return Response({"found": True, "available": True, "data": asdict(data)})


@method_decorator(csrf_protect, name="dispatch")
class CompanyRegisterView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CompanyRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": first_error(serializer.errors), "errors": serializer.errors}, status=400
            )
        try:
            company = services.register_company(**serializer.validated_data)
        except (services.CnpjAlreadyRegistered, services.EmailAlreadyRegistered) as error:
            return Response({"detail": str(error)}, status=409)
        return Response(
            {
                "id": company.pk,
                "verification_status": company.verification_status,
                "data_unverified": company.data_unverified,
            },
            status=201,
        )
