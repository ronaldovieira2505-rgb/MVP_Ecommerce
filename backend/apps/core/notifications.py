"""Notificações dentro do app."""

from apps.core.models import Notification


def notify(user, kind, title, message="", link=""):
    return Notification.objects.create(
        user=user, kind=kind, title=title, message=message, link=link
    )


def notify_company(company, kind, title, message="", link=""):
    for member in company.members.select_related("user"):
        notify(member.user, kind, title, message, link)


def notify_admins(kind, title, message="", link=""):
    from django.contrib.auth import get_user_model

    for admin in get_user_model().objects.filter(is_staff=True, is_active=True):
        notify(admin, kind, title, message, link)
