from django.urls import path

from . import views, worker_views

urlpatterns = [
    path(
        "vacancies/<int:pk>/apply/",
        worker_views.VacancyApplyView.as_view(),
        name="vacancy-apply",
    ),
    path(
        "applications/<int:pk>/withdraw/",
        worker_views.ApplicationWithdrawView.as_view(),
        name="application-withdraw",
    ),
    path("workers/me/jobs/", worker_views.WorkerJobsView.as_view(), name="worker-jobs"),
    path("vacancies/", views.VacancyCreateView.as_view(), name="vacancy-create"),
    path("vacancies/<int:pk>/", views.VacancyDetailView.as_view(), name="vacancy-detail"),
    path("vacancies/<int:pk>/pay/", views.VacancyPayView.as_view(), name="vacancy-pay"),
    path("vacancies/<int:pk>/remove/", views.VacancyRemoveView.as_view(), name="vacancy-remove"),
    path("company/vacancies/", views.CompanyVacancyListView.as_view(), name="company-vacancies"),
]
