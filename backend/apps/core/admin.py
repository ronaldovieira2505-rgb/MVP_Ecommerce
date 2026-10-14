from django.contrib import admin, messages
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse

from apps.core.deadlines import process_deadlines
from apps.core.models import (
    Notification,
    PlatformParameters,
    StateTransition,
    VerificationReview,
)

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


@admin.register(PlatformParameters)
class PlatformParametersAdmin(ProcessDeadlinesMixin, admin.ModelAdmin):
    def has_add_permission(self, request):
        return not PlatformParameters.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StateTransition)
class StateTransitionAdmin(ProcessDeadlinesMixin, ReadOnlyAdmin):
    list_display = ("created_at", "entity_type", "entity_id", "from_state", "to_state", "actor")
    list_filter = ("entity_type", "to_state")
    search_fields = ("entity_id", "reason")


@admin.register(VerificationReview)
class VerificationReviewAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "subject_type", "subject_id", "decision", "reviewer")
    list_filter = ("subject_type", "decision")


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "user", "kind", "title", "read_at")
    list_filter = ("kind",)
