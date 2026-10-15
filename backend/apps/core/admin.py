from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import (
    Http404,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.companies.models import Company
from apps.companies.services import lookup_cnpj
from apps.core.deadlines import process_deadlines
from apps.core.exceptions import DomainError
from apps.core.models import (
    Notification,
    PlatformParameters,
    PlatformParametersChange,
    StateTransition,
    VerificationReview,
)
from apps.core.verification_queue import SLUG_KINDS, decide, queue_items
from apps.workers.models import Worker, WorkerDocument
from integrations.cnpj import CnpjLookupError

admin.site.site_header = "Conecta Já — Administração"
admin.site.site_title = "Conecta Já"
admin.site.index_title = "Painel administrativo"


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProcessDeadlinesMixin:
    """Botão “Processar prazos agora” na lista do modelo."""

    change_list_template = "admin/core/processar_prazos_changelist.html"

    def get_urls(self):
        custom = [
            path(
                "processar-prazos/",
                self.admin_site.admin_view(self.processar_prazos_view),
                name="processar_prazos",
            )
        ]
        return custom + super().get_urls()

    def processar_prazos_view(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not request.user.has_perm("core.change_platformparameters"):
            self.message_user(request, "Sem permissão para processar prazos.", messages.ERROR)
        else:
            done = process_deadlines()
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(done.items()))
            self.message_user(
                request, f"Prazos processados. {summary or 'Nada a processar.'}", messages.SUCCESS
            )
        return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("admin:index"))


MINUTE_FIELDS = (
    "min_publish_lead_minutes",
    "payment_deadline_minutes",
    "applications_close_minutes_before",
    "checkin_open_minutes_before",
    "no_show_tolerance_minutes",
    "auto_checkout_minutes_after_end",
    "contest_window_minutes",
    "free_cancel_minutes_before",
)
# Parâmetros que não fazem sentido com zero; os demais aceitam 0.
POSITIVE_ONLY_FIELDS = (
    "payment_deadline_minutes",
    "geofence_radius_m",
    "contest_window_minutes",
    "no_show_limit",
    "no_show_window_days",
    "suspension_days",
    "cnpj_lookup_timeout_seconds",
    "document_max_size_mb",
)


def humanize_minutes(minutes):
    """720 -> '720 min = 12 h'; 90 -> '90 min = 1 h 30 min'; 1440 -> '1440 min = 1 dia'."""
    if minutes is None:
        return ""
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} dia" if days == 1 else f"{days} dias")
    if hours:
        parts.append(f"{hours} h")
    if mins or not parts:
        parts.append(f"{mins} min")
    return f"{minutes} min = {' '.join(parts)}"


class PlatformParametersForm(forms.ModelForm):
    worker_fee_percent = forms.IntegerField(
        label="Taxa retida do prestador (%)", min_value=0, max_value=100
    )

    class Meta:
        model = PlatformParameters
        fields = (
            *MINUTE_FIELDS,
            "geofence_radius_m",
            "no_show_limit",
            "no_show_window_days",
            "suspension_days",
            "late_cancel_block_days",
            "cnpj_lookup_timeout_seconds",
            "document_max_size_mb",
            "worker_fee_percent",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["worker_fee_percent"] = int(self.instance.worker_fee_percent)
        for name in MINUTE_FIELDS:
            current = getattr(self.instance, name, None) if self.instance.pk else None
            self.fields[name].help_text = f"Valor atual: {humanize_minutes(current)}"

    def clean(self):
        cleaned = super().clean()
        for name in POSITIVE_ONLY_FIELDS:
            if cleaned.get(name) == 0:
                self.add_error(name, "O valor deve ser maior que zero.")
        return cleaned


def _display(value):
    if isinstance(value, Decimal) and value == value.to_integral():
        return str(int(value))
    return str(value)


@admin.register(PlatformParameters)
class PlatformParametersAdmin(ProcessDeadlinesMixin, admin.ModelAdmin):
    form = PlatformParametersForm

    def has_add_permission(self, request):
        return not PlatformParameters.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        before = PlatformParameters.objects.filter(pk=obj.pk).first() if change else None
        defaults = before or PlatformParameters()
        super().save_model(request, obj, form, change)
        for name in form.changed_data:
            old, new = getattr(defaults, name), getattr(obj, name)
            if old != new:
                PlatformParametersChange.objects.create(
                    field=name,
                    old_value=_display(old),
                    new_value=_display(new),
                    changed_by=request.user,
                )


@admin.register(PlatformParametersChange)
class PlatformParametersChangeAdmin(ReadOnlyAdmin):
    list_display = ("changed_at", "changed_by", "field", "old_value", "new_value")
    list_filter = ("field",)


@admin.register(StateTransition)
class StateTransitionAdmin(ProcessDeadlinesMixin, ReadOnlyAdmin):
    list_display = ("created_at", "entity_type", "entity_id", "from_state", "to_state", "actor")
    list_filter = ("entity_type", "to_state")
    search_fields = ("entity_id", "reason")


COMPANY_COMPARISON_FIELDS = (
    "legal_name",
    "trade_name",
    "registration_status",
    "street",
    "number",
    "complement",
    "district",
    "city",
    "state",
    "zip_code",
)


def _company_comparison(company):
    """Dados informados × dados da BrasilAPI. Se a consulta falhar, devolve (None, motivo)."""
    try:
        official = lookup_cnpj(company.cnpj)
    except CnpjLookupError as error:
        return None, str(error)
    rows = []
    for name in COMPANY_COMPARISON_FIELDS:
        informed, returned = getattr(company, name), getattr(official, name)
        rows.append(
            {
                "label": Company._meta.get_field(name).verbose_name,
                "informed": informed,
                "returned": returned,
                "differs": informed.strip().lower() != returned.strip().lower(),
            }
        )
    return rows, ""


def _worker_documents(worker):
    sent = {document.kind: document for document in worker.documents.all()}
    documents = []
    for kind in WorkerDocument.Kind:
        document = sent.get(kind.value)
        documents.append(
            {
                "label": kind.label,
                "url": reverse("worker-document-file", args=[worker.pk, kind.value])
                if document
                else "",
                "is_pdf": bool(document) and document.file.name.lower().endswith(".pdf"),
            }
        )
    return documents


@admin.register(VerificationReview)
class VerificationReviewAdmin(ReadOnlyAdmin):
    """Também hospeda a “Fila de verificação” (US73) do painel administrativo."""

    change_list_template = "admin/core/verificationreview_changelist.html"
    list_display = ("created_at", "subject_type", "subject_id", "decision", "reviewer")
    list_filter = ("subject_type", "decision")

    def get_urls(self):
        custom = [
            path("fila/", self.admin_site.admin_view(self.queue_view), name="verification_queue"),
            path(
                "fila/<slug:slug>/<int:pk>/",
                self.admin_site.admin_view(self.queue_detail_view),
                name="verification_queue_detail",
            ),
        ]
        return custom + super().get_urls()

    def _require_reviewer(self, request):
        if not request.user.has_perm("core.add_verificationreview"):
            raise PermissionDenied

    def queue_view(self, request):
        self._require_reviewer(request)
        context = {
            **self.admin_site.each_context(request),
            "title": "Fila de verificação",
            "items": queue_items(),
        }
        return TemplateResponse(request, "admin/core/verification_queue.html", context)

    def queue_detail_view(self, request, slug, pk):
        self._require_reviewer(request)
        kind = SLUG_KINDS.get(slug)
        if kind is None:
            raise Http404
        model = Company if kind == VerificationReview.SubjectType.COMPANY else Worker
        subject = get_object_or_404(model, pk=pk)
        queue_url = reverse("admin:verification_queue")
        if request.method == "POST":
            action = request.POST.get("action")
            if action not in ("approve", "reject"):
                return HttpResponseBadRequest("Ação inválida.")
            try:
                decide(
                    kind,
                    subject,
                    reviewer=request.user,
                    approve=action == "approve",
                    reason=request.POST.get("reason", ""),
                )
            except DomainError as error:
                self.message_user(request, str(error), messages.ERROR)
                return HttpResponseRedirect(request.path)
            self.message_user(
                request,
                "Cadastro aprovado." if action == "approve" else "Cadastro rejeitado.",
                messages.SUCCESS,
            )
            return HttpResponseRedirect(queue_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Verificação — {SLUG_KINDS[slug].label}",
            "kind": kind,
            "subject": subject,
            "queue_url": queue_url,
            "in_queue": (
                subject.verification_status == Company.VerificationStatus.PENDING
                if kind == VerificationReview.SubjectType.COMPANY
                else subject.verification_status == Worker.VerificationStatus.IN_REVIEW
            ),
        }
        if kind == VerificationReview.SubjectType.COMPANY:
            rows, lookup_error = _company_comparison(subject)
            context.update(comparison=rows, lookup_error=lookup_error)
        else:
            context.update(
                documents=_worker_documents(subject),
                email=subject.user.email,
                masked_cpf=subject.masked_cpf,
                masked_pix_key=subject.masked_pix_key,
            )
        return TemplateResponse(request, "admin/core/verification_detail.html", context)


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "user", "kind", "title", "read_at")
    list_filter = ("kind",)
