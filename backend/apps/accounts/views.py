from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Role

INVALID_CREDENTIALS = "E-mail ou senha inválidos"


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


def authenticate_by_email(request, email, password):
    """Autentica por e-mail (sem diferenciar maiúsculas). Devolve o usuário ou None."""
    User = get_user_model()
    for candidate in User.objects.filter(email__iexact=email.strip()):
        user = authenticate(request, username=candidate.get_username(), password=password)
        if user is not None:
            return user
    return None


def display_name(user):
    if user.role == Role.WORKER:
        worker = getattr(user, "worker", None)
        if worker is not None:
            return worker.full_name
    if user.role == Role.COMPANY:
        member = user.company_memberships.select_related("company").first()
        if member is not None:
            return str(member.company)
    return user.get_full_name() or user.get_username()


def verification_status(user):
    if user.role == Role.WORKER:
        worker = getattr(user, "worker", None)
        return worker.verification_status if worker is not None else None
    if user.role == Role.COMPANY:
        member = user.company_memberships.select_related("company").first()
        return member.company.verification_status if member is not None else None
    return None


def serialize_user(user):
    return {
        "id": user.pk,
        "name": display_name(user),
        "email": user.email,
        "role": user.role,
        "verification_status": verification_status(user),
    }


class CsrfView(APIView):
    """Entrega o cookie CSRF ao frontend (necessário antes do login)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=False)
        user = None
        if not serializer.errors:
            user = authenticate_by_email(
                request, serializer.validated_data["email"], serializer.validated_data["password"]
            )
        if user is None:
            return Response({"detail": INVALID_CREDENTIALS}, status=400)
        login(request, user)
        return Response(serialize_user(user))


class LogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


class MeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(serialize_user(request.user))
