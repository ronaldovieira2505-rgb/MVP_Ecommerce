from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .permissions import IsObjectOwner


def serialize_notification(n):
    return {
        "id": n.pk,
        "kind": n.kind,
        "title": n.title,
        "message": n.message,
        "link": n.link,
        "read": n.read_at is not None,
        "created_at": n.created_at.isoformat(),
    }


class NotificationListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        own = Notification.objects.filter(user=request.user)
        return Response(
            {
                "unread_count": own.filter(read_at__isnull=True).count(),
                "results": [serialize_notification(n) for n in own[:50]],
            }
        )


class NotificationReadView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsObjectOwner]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk)
        self.check_object_permissions(request, notification)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(serialize_notification(notification))


class NotificationReadAllView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return Response(status=204)
