from django.contrib import admin

from apps.companies.models import Company, CompanyMember


class CompanyMemberInline(admin.TabularInline):
    model = CompanyMember
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "trade_name", "cnpj", "verification_status", "created_at")
    list_filter = ("verification_status", "tax_regime")
    search_fields = ("legal_name", "trade_name", "cnpj")
    # O status só muda pelo serviço de domínio (grava a auditoria).
    readonly_fields = ("verification_status",)
    inlines = [CompanyMemberInline]
