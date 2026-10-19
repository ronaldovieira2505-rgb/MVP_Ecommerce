from django.urls import path

from . import candidate_views, views, worker_views

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
    path(
        "vacancies/<int:pk>/candidates/",
        candidate_views.VacancyCandidatesView.as_view(),
        name="vacancy-candidates",
    ),
    path(
        "applications/<int:pk>/approve/",
        candidate_views.ApplicationApproveView.as_view(),
        name="application-approve",
    ),
    path(
        "applications/<int:pk>/reject/",
        candidate_views.ApplicationRejectView.as_view(),
        name="application-reject",
    ),
    path(
        "applications/<int:pk>/photo/",
        candidate_views.ApplicationPhotoView.as_view(),
        name="application-photo",
    ),
    path(
        "assignments/<int:pk>/check-in/",
        worker_views.AssignmentCheckInView.as_view(),
        name="assignment-check-in",
    ),
    path(
        "assignments/<int:pk>/check-out/",
        worker_views.AssignmentCheckOutView.as_view(),
        name="assignment-check-out",
    ),
    path("workers/me/jobs/", worker_views.WorkerJobsView.as_view(), name="worker-jobs"),
    path("vacancies/", views.VacancyCreateView.as_view(), name="vacancy-create"),
    path("vacancies/<int:pk>/", views.VacancyDetailView.as_view(), name="vacancy-detail"),
    path("vacancies/<int:pk>/pay/", views.VacancyPayView.as_view(), name="vacancy-pay"),
    path("vacancies/<int:pk>/remove/", views.VacancyRemoveView.as_view(), name="vacancy-remove"),
    path("company/vacancies/", views.CompanyVacancyListView.as_view(), name="company-vacancies"),
]
