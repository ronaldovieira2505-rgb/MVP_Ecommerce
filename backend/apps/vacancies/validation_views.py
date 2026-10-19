"""API da empresa para conferir as horas e liberar o pagamento (US56/US59)."""

import logging
from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies import assignment_services as assignments
from apps.vacancies.models import Assignment
from apps.vacancies.views import NO_COMPANY, CompanyAreaView, forbidden_company
from integrations.payments import PaymentGatewayError

logger = logging.getLogger(__name__)

NOT_FOUND = "Alocação não encontrada."


def _first_name(worker):
    parts = worker.full_name.split()
    return parts[0] if parts else ""


def serialize_pending_assignment(assignment, params, now):
    """Horas a conferir: previsto × registrado, distância e prazo da aprovação automática."""
    vacancy = assignment.vacancy
    auto_approve_at = assignment.check_out_at + timedelta(minutes=params.contest_window_minutes)
    remaining = max(0, int((auto_approve_at - now).total_seconds()))
    return {
        "id": assignment.pk,
        "vacancy_id": vacancy.pk,
        "vacancy_title": vacancy.title,
        "worker_first_name": _first_name(assignment.worker),
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
        "check_in_at": assignment.check_in_at and assignment.check_in_at.isoformat(),
        "check_out_at": assignment.check_out_at.isoformat(),
        "check_out_auto": assignment.check_out_auto,
        "check_in_distance_m": assignment.check_in_distance_m,
        "gross_cents": vacancy.pay_per_person_cents,
        "status": assignment.status,
        "status_label": assignment.get_status_display(),
        "auto_approve_at": auto_approve_at.isoformat(),
        "auto_approve_in_seconds": remaining,
    }


class CompanyPendingAssignmentsView(CompanyAreaView):
    """`GET /api/company/assignments/pending/`: alocações AGUARDANDO_VALIDACAO das minhas vagas.

    Filtro opcional `?vacancy=<id>` para a seção dentro da vaga.
    """

    def get(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        queryset = Assignment.objects.filter(
            vacancy__company=company,
            status=Assignment.Status.AWAITING_VALIDATION,
            check_out_at__isnull=False,
        ).select_related("vacancy", "worker")
        vacancy_id = request.query_params.get("vacancy")
        if vacancy_id:
            if not vacancy_id.isdigit():
                return Response({"detail": "Vaga inválida."}, status=400)
            queryset = queryset.filter(vacancy_id=int(vacancy_id))
        params = PlatformParameters.get()
        now = timezone.now()
        items = [
            serialize_pending_assignment(a, params, now)
            for a in queryset.order_by("check_out_at", "pk")
        ]
        return Response({"results": items})


@method_decorator(csrf_protect, name="dispatch")
class AssignmentApproveView(CompanyAreaView):
    """`POST /api/assignments/<id>/approve/`: aprova as horas e tenta liquidar o pagamento.

    Alocação de outra empresa responde 404. Se o PSP falhar, a alocação continua `APROVADA`
    e o próximo processamento de prazos tenta de novo, sem duplicar lançamentos.
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        assignment = (
            Assignment.objects.select_related("vacancy__company", "worker__user")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if assignment is None:  # de outra empresa: não revela que existe
            return Response({"detail": NOT_FOUND}, status=404)
        try:
            assignment = assignments.approve_hours(assignment, actor=request.user)
        except DomainError as error:  # inclui InvalidTransition
            return Response({"detail": str(error)}, status=409)
        payment_pending = False
        try:
            assignment = assignments.settle(assignment)
        except (DomainError, PaymentGatewayError) as error:
            payment_pending = True
            logger.warning("Liquidação adiada para a alocação #%s: %s", assignment.pk, error)
        return Response(
            {
                "id": assignment.pk,
                "status": assignment.status,
                "status_label": assignment.get_status_display(),
                "payment_pending": payment_pending,
            }
        )
