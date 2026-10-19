"""API do prestador: candidatar-se, desistir e acompanhar os trabalhos (US37/US38)."""

from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import DomainError, InvalidTransition
from apps.core.models import PlatformParameters
from apps.core.permissions import IsWorkerUser
from apps.vacancies import application_services as applications
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Application, Assignment, Vacancy

AS = Assignment.Status
AP = Application.Status

# Grupos da página "Meus trabalhos" (US38).
IN_PROGRESS_STATUSES = (AS.IN_PROGRESS, AS.AWAITING_VALIDATION, AS.CONTESTED, AS.APPROVED)
CLOSED_ASSIGNMENT_STATUSES = (
    AS.NO_SHOW,
    AS.REFUNDED,
    AS.CANCELLED_BY_WORKER,
    AS.CANCELLED_BY_COMPANY,
)
CLOSED_APPLICATION_STATUSES = (AP.REJECTED, AP.WITHDRAWN, AP.EXPIRED)


class WorkerAreaView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsWorkerUser]

    def worker(self, request):
        return getattr(request.user, "worker", None)


def _execution_info(assignment, params, now):
    """Janela de check-in e horários registrados, para os botões de "Meus trabalhos"."""
    vacancy = assignment.vacancy
    opens_at = vacancy.starts_at - timedelta(minutes=params.checkin_open_minutes_before)
    closes_at = vacancy.starts_at + timedelta(minutes=params.no_show_tolerance_minutes)
    return {
        "check_in_opens_at": opens_at.isoformat(),
        "check_in_closes_at": closes_at.isoformat(),
        "can_check_in": assignment.status == AS.CONFIRMED and opens_at <= now <= closes_at,
        "can_check_out": assignment.status == AS.IN_PROGRESS,
        "check_in_at": assignment.check_in_at and assignment.check_in_at.isoformat(),
        "check_out_at": assignment.check_out_at and assignment.check_out_at.isoformat(),
        "check_out_auto": assignment.check_out_auto,
    }


def serialize_assignment(assignment, params=None, now=None):
    params = params or PlatformParameters.get()
    item = _item("assignment", assignment, assignment.vacancy, params)
    item.update(_execution_info(assignment, params, now or timezone.now()))
    return item


def _item(kind, obj, vacancy, params):
    return {
        "kind": kind,
        "id": obj.pk,
        "vacancy_id": vacancy.pk,
        "title": vacancy.title,
        "company_name": vacancy.company.trade_name or vacancy.company.legal_name,
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
        "gross_cents": vacancy.pay_per_person_cents,
        "net_cents": params.worker_net_cents(vacancy.pay_per_person_cents),
        "status": obj.status,
        "status_label": obj.get_status_display(),
        "can_withdraw": kind == "application" and obj.status == AP.PENDING,
    }


def serialize_application(application):
    return _item("application", application, application.vacancy, PlatformParameters.get())


@method_decorator(csrf_protect, name="dispatch")
class VacancyApplyView(WorkerAreaView):
    """`POST /api/vacancies/<id>/apply/`: candidatura com um clique."""

    def post(self, request, pk):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        vacancy = Vacancy.objects.select_related("company").filter(pk=pk).first()
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        try:
            application = applications.apply_to_vacancy(vacancy, worker, actor=request.user)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_application(application), status=201)


@method_decorator(csrf_protect, name="dispatch")
class ApplicationWithdrawView(WorkerAreaView):
    """`POST /api/applications/<id>/withdraw/`: desistência sem penalidade."""

    def post(self, request, pk):
        worker = self.worker(request)
        application = None
        if worker:
            application = (
                Application.objects.select_related("vacancy__company")
                .filter(pk=pk, worker=worker)
                .first()
            )
        if application is None:  # de outro prestador: não revela que existe
            return Response({"detail": "Candidatura não encontrada."}, status=404)
        try:
            application = applications.withdraw_application(application, actor=request.user)
        except InvalidTransition:
            return Response(
                {"detail": "Só é possível desistir de uma candidatura pendente."}, status=409
            )
        return Response(serialize_application(application))


class WorkerJobsView(WorkerAreaView):
    """`GET /api/workers/me/jobs/`: candidaturas e alocações agrupadas por situação."""

    def get(self, request):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        params = PlatformParameters.get()
        now = timezone.now()
        groups = {"waiting": [], "upcoming": [], "in_progress": [], "completed": [], "closed": []}
        for application in worker.applications.select_related("vacancy__company"):
            if application.status == AP.PENDING:
                key = "waiting"
            elif application.status in CLOSED_APPLICATION_STATUSES:
                key = "closed"
            else:  # APROVADA: o acompanhamento continua na alocação
                continue
            groups[key].append(_item("application", application, application.vacancy, params))
        for assignment in worker.assignments.select_related("vacancy__company"):
            if assignment.status == AS.CONFIRMED:
                key = "upcoming"
            elif assignment.status in IN_PROGRESS_STATUSES:
                key = "in_progress"
            elif assignment.status == AS.PAID:
                key = "completed"
            else:
                key = "closed"
            groups[key].append(serialize_assignment(assignment, params, now))
        for key, items in groups.items():
            newest_first = key in ("completed", "closed")
            items.sort(key=lambda i: (i["starts_at"], i["id"]), reverse=newest_first)
        return Response({"groups": groups})


class AssignmentActionView(WorkerAreaView):
    """Base das ações do prestador sobre a própria alocação (404 para a de outro)."""

    def post(self, request, pk):
        worker = self.worker(request)
        assignment = None
        if worker:
            assignment = (
                Assignment.objects.select_related("vacancy__company")
                .filter(pk=pk, worker=worker)
                .first()
            )
        if assignment is None:
            return Response({"detail": "Alocação não encontrada."}, status=404)
        try:
            assignment = self.run(request, assignment)
        except DomainError as error:  # inclui InvalidTransition
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_assignment(assignment))


@method_decorator(csrf_protect, name="dispatch")
class AssignmentCheckInView(AssignmentActionView):
    """`POST /api/assignments/<id>/check-in/` com `lat`, `lng` e `accuracy` (m).

    A distância é calculada no servidor (Haversine); a precisão é só informativa.
    """

    def run(self, request, assignment):
        lat, lng = request.data.get("lat"), request.data.get("lng")
        if lat is None or lng is None:
            raise DomainError("Informe a sua localização para registrar a chegada.")
        return assignments.check_in(assignment, lat=lat, lng=lng, actor=request.user)


@method_decorator(csrf_protect, name="dispatch")
class AssignmentCheckOutView(AssignmentActionView):
    """`POST /api/assignments/<id>/check-out/`: encerra o turno."""

    def run(self, request, assignment):
        return assignments.check_out(assignment, actor=request.user)

