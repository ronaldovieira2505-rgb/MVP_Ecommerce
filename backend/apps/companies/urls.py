from django.urls import path

from . import views

urlpatterns = [
    path("cnpj/<str:cnpj>/", views.CnpjLookupView.as_view(), name="cnpj-lookup"),
    path("companies/register/", views.CompanyRegisterView.as_view(), name="company-register"),
]
