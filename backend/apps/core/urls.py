from django.urls import include, path

from . import notification_views, views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.companies.urls")),
    path("", include("apps.workers.urls")),
    path("notifications/", notification_views.NotificationListView.as_view(), name="notifications"),
    path(
        "notifications/read-all/",
        notification_views.NotificationReadAllView.as_view(),
        name="notifications-read-all",
    ),
    path(
        "notifications/<int:pk>/read/",
        notification_views.NotificationReadView.as_view(),
        name="notification-read",
    ),
]
