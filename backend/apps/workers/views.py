from datetime import date

from django.contrib.auth import login
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.companies.views import digits_only, first_error
from apps.core.exceptions import DomainError
from apps.core.masking import mask_phone
from apps.core.validators import is_valid_cpf
from apps.workers import services
from apps.workers.models import Worker, WorkerDocument

KINDS = list(WorkerDocument.Kind)
RESTRICTED = "Acesso restrito a prestadores."
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
    steps = services.profile_steps(worker)
    uploaded = set(worker.documents.values_list("kind", flat=True))
    awaiting = (
        all(step["done"] for step in steps)
        and worker.verification_status == Worker.VerificationStatus.IN_REVIEW
    )
    return {
        "id": worker.pk,
        "full_name": worker.full_name,
        "cpf": worker.masked_cpf,
        "phone": mask_phone(worker.phone),
        "verification_status": worker.verification_status,
        "pix_key_type": worker.pix_key_type,
        "pix_key": worker.masked_pix_key,
        "documents": [{"kind": kind.value, "uploaded": kind.value in uploaded} for kind in KINDS],
        "profile_steps": steps,
        "verification_message": "Aguardando verificação" if awaiting else "",
    }


def worker_or_403(request):
    user = request.user
    if user.role != Role.WORKER or not hasattr(user, "worker"):
        return None
    return user.worker


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
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        return Response(serialize_worker(worker))


class WorkerDocumentsView(APIView):
    """`POST /api/workers/me/documents/` (multipart): document_front, document_back, selfie."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    FIELDS = {
        "document_front": WorkerDocument.Kind.FRONT,
        "document_back": WorkerDocument.Kind.BACK,
        "selfie": WorkerDocument.Kind.SELFIE,
    }

    def post(self, request):
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        files = {
            kind: request.FILES[name] for name, kind in self.FIELDS.items() if name in request.FILES
        }
        try:
            worker = services.upload_documents(worker, files=files, actor=request.user)
        except services.DocumentsNotAllowed as error:
            return Response({"detail": str(error)}, status=409)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        return Response(serialize_worker(worker))


class WorkerDocumentFileView(APIView):
    """Download protegido: só o dono ou o admin. Nunca existe URL pública."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, worker_id, kind):
        user = request.user
        is_admin = user.is_staff or user.role == Role.ADMIN
        owns = user.role == Role.WORKER and hasattr(user, "worker") and user.worker.pk == worker_id
        if not (is_admin or owns):
            raise Http404
        document = get_object_or_404(WorkerDocument, worker_id=worker_id, kind=kind)
        response = FileResponse(document.file.open("rb"))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class WorkerPixSerializer(serializers.Serializer):
    key_type = serializers.ChoiceField(choices=Worker.PixKeyType.choices)
    key = serializers.CharField(max_length=100)
    current_password = serializers.CharField(
        required=False, allow_blank=True, max_length=128, trim_whitespace=False
    )


class WorkerPixView(APIView):
    """`PUT /api/workers/me/pix/`. A troca de uma chave existente exige a senha atual."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request):
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        serializer = WorkerPixSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": first_error(serializer.errors), "errors": serializer.errors}, status=400
            )
        data = serializer.validated_data
        try:
            worker = services.set_pix_key(
                worker,
                key_type=data["key_type"],
                key=data["key"],
                current_password=data.get("current_password", ""),
                actor=request.user,
            )
        except services.WrongPassword as error:
            return Response({"detail": str(error)}, status=403)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        return Response(serialize_worker(worker))
