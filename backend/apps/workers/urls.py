from django.urls import path

from . import views

urlpatterns = [
    path("workers/register/", views.WorkerRegisterView.as_view(), name="worker-register"),
    path("workers/me/", views.WorkerMeView.as_view(), name="worker-me"),
]
