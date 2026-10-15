from django.urls import path

from . import views

urlpatterns = [
    path("vacancies/", views.VacancyCreateView.as_view(), name="vacancy-create"),
    path("vacancies/<int:pk>/", views.VacancyDetailView.as_view(), name="vacancy-detail"),
    path("vacancies/<int:pk>/pay/", views.VacancyPayView.as_view(), name="vacancy-pay"),
    path("company/vacancies/", views.CompanyVacancyListView.as_view(), name="company-vacancies"),
]
