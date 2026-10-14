from datetime import date

from django.contrib.auth import login
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.companies.views import digits_only, first_error
from apps.core.masking import mask_phone
from apps.core.validators import is_valid_cpf
from apps.workers import services

INVALID_CPF = "CPF inválido"
UNDERAGE = "É preciso ter 18 anos ou mais"


class CpfField(serializers.CharField):
    def to_internal_value(self, data):
        cpf = digits_only(super().to_internal_value(data))
        if not is_valid_cpf(cpf):
            raise serializers.ValidationError(INVALID_CPF)
        return cpf


class WorkerRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    cpf = CpfField()
    phone = serializers.CharField(max_length=20)
    birth_date = serializers.DateField()
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_birth_date(self, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError(UNDERAGE)
        return value


def serialize_worker(worker):
    """Nunca devolve CPF ou chave PIX em claro."""
    return {
        "id": worker.pk,
        "full_name": worker.full_name,
        "cpf": worker.masked_cpf,
        "phone": mask_phone(worker.phone),
        "verification_status": worker.verification_status,
        "profile_steps": services.profile_steps(worker),
    }


@method_decorator(csrf_protect, name="dispatch")
class WorkerRegisterView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = WorkerRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": first_error(serializer.errors), "errors": serializer.errors}, status=400
            )
        try:
            worker = services.register_worker(**serializer.validated_data)
        except (services.CpfAlreadyRegistered, services.EmailAlreadyRegistered) as error:
            return Response({"detail": str(error)}, status=409)
        login(request, worker.user)
        return Response(serialize_worker(worker), status=201)


class WorkerMeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != Role.WORKER or not hasattr(request.user, "worker"):
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        return Response(serialize_worker(request.user.worker))
