from django.contrib import admin

from apps.vacancies.models import Application, Assignment, Vacancy


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "starts_at", "positions", "status", "reopened")
    list_filter = ("status", "category")
    search_fields = ("title",)
    readonly_fields = ("status", "reopened")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "vacancy", "worker", "status", "created_at")
    list_filter = ("status",)
    readonly_fields = ("status",)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "vacancy", "worker", "status", "check_in_at", "check_out_at")
    list_filter = ("status",)
    readonly_fields = ("status",)
