"""API da empresa para selecionar candidatos: listar, aprovar e recusar (US42)."""

from django.http import FileResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError, InvalidTransition
from apps.vacancies import application_services as applications
from apps.vacancies.models import Application, Assignment, Vacancy
from apps.vacancies.views import NO_COMPANY, CompanyAreaView, forbidden_company
from apps.workers.models import Worker, WorkerDocument

NOT_FOUND = "Candidatura não encontrada."


def _worker_has_selfie(worker):
    return any(d.kind == WorkerDocument.Kind.SELFIE for d in worker.documents.all())


def _first_name(worker):
    parts = worker.full_name.split()
    return parts[0] if parts else ""


def serialize_candidate(application):
    """Só o que a empresa pode ver antes da alocação: sem CPF, telefone nem PIX."""
    worker = application.worker
    return {
        "id": application.pk,
        "name": _first_name(worker),
        "photo_url": (
            f"/api/applications/{application.pk}/photo/" if _worker_has_selfie(worker) else None
        ),
        "verified": worker.verification_status == Worker.VerificationStatus.APPROVED,
        "completed_shifts": worker.assignments.filter(status=Assignment.Status.PAID).count(),
        "applied_at": application.created_at.isoformat(),
    }


def serialize_team_member(assignment):
    """Contato liberado só após a alocação: primeiro nome e telefone."""
    worker = assignment.worker
    return {
        "id": assignment.pk,
        "first_name": _first_name(worker),
        "phone": worker.phone,
        "status": assignment.status,
        "status_label": assignment.get_status_display(),
    }


class CandidateAreaView(CompanyAreaView):
    def own_vacancy(self, request, pk):
        """(vaga, resposta de erro). Vaga de outra empresa responde 404."""
        company = self.company(request)
        if company is None:
            return None, Response({"detail": NO_COMPANY}, status=403)
        vacancy = Vacancy.objects.filter(pk=pk, company=company).first()
        if vacancy is None:
            return None, Response({"detail": "Vaga não encontrada."}, status=404)
        return vacancy, None

    def own_application(self, request, pk):
        company = self.company(request)
        if company is None:
            return None, Response({"detail": NO_COMPANY}, status=403)
        application = (
            Application.objects.select_related("vacancy", "worker__user")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if application is None:  # de outra empresa: não revela que existe
            return None, Response({"detail": NOT_FOUND}, status=404)
        return application, None


class VacancyCandidatesView(CandidateAreaView):
    """`GET /api/vacancies/<id>/candidates/`: pendentes + equipe já alocada."""

    def get(self, request, pk):
        vacancy, error = self.own_vacancy(request, pk)
        if error:
            return error
        pending = (
            vacancy.applications.filter(status=Application.Status.PENDING)
            .select_related("worker")
            .prefetch_related("worker__documents")
            .order_by("created_at", "pk")
        )
        team = (
            vacancy.assignments.filter(status__in=Assignment.ACTIVE_STATUSES)
            .select_related("worker")
            .order_by("pk")
        )
        filled = vacancy.filled_positions
        return Response(
            {
                "positions": vacancy.positions,
                "filled_positions": filled,
                "team_complete": filled >= vacancy.positions,
                "candidates": [serialize_candidate(a) for a in pending],
                "team": [serialize_team_member(a) for a in team],
            }
        )


class DecisionView(CandidateAreaView):
    def post(self, request, pk):
        denied = None
        company = self.company(request)
        if company is not None:
            denied = forbidden_company(company)
        if denied:
            return denied
        application, error = self.own_application(request, pk)
        if error:
            return error
        try:
            return Response(self.decide(application, request))
        except InvalidTransition:
            return Response({"detail": "Esta candidatura já foi decidida."}, status=409)
        except DomainError as exc:
            return Response({"detail": str(exc)}, status=409)

    def decide(self, application, request):
        raise NotImplementedError


@method_decorator(csrf_protect, name="dispatch")
class ApplicationApproveView(DecisionView):
    """`POST /api/applications/<id>/approve/`."""

    def decide(self, application, request):
        assignment = applications.approve_application(application, actor=request.user)
        return {
            "application_id": application.pk,
            "status": Application.Status.APPROVED,
            "assignment": serialize_team_member(assignment),
        }


@method_decorator(csrf_protect, name="dispatch")
class ApplicationRejectView(DecisionView):
    """`POST /api/applications/<id>/reject/`."""

    def decide(self, application, request):
        application = applications.reject_application(application, actor=request.user)
        return {"application_id": application.pk, "status": application.status}


class ApplicationPhotoView(CandidateAreaView):
    """`GET /api/applications/<id>/photo/`: selfie verificada, só para a empresa da vaga."""

    def get(self, request, pk):
        application, error = self.own_application(request, pk)
        if error:
            return error
        document = (
            application.worker.documents.filter(kind=WorkerDocument.Kind.SELFIE)
            .order_by("-uploaded_at", "-pk")
            .first()
        )
        if document is None:
            return Response({"detail": "Foto não encontrada."}, status=404)
        return FileResponse(document.file.open("rb"))
