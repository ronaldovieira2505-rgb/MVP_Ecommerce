from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin
from apps.payments.models import Custody, LedgerEntry


@admin.register(Custody)
class CustodyAdmin(admin.ModelAdmin):
    list_display = ("id", "vacancy", "amount_cents", "status", "psp_reference")
    list_filter = ("status",)
    readonly_fields = ("idempotency_key", "psp_reference")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "custody", "assignment", "kind", "amount_cents")
    list_filter = ("kind",)
