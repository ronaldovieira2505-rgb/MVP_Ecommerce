from django.urls import path

from . import views

urlpatterns = [
    path("workers/register/", views.WorkerRegisterView.as_view(), name="worker-register"),
    path("workers/me/", views.WorkerMeView.as_view(), name="worker-me"),
    path("workers/me/documents/", views.WorkerDocumentsView.as_view(), name="worker-documents"),
    path("workers/me/pix/", views.WorkerPixView.as_view(), name="worker-pix"),
    path(
        "workers/<int:worker_id>/documents/<str:kind>/",
        views.WorkerDocumentFileView.as_view(),
        name="worker-document-file",
    ),
]
