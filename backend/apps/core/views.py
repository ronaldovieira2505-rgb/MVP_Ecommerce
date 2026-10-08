from django.db import connection
from django.db.utils import Error as DatabaseError
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def health(request):
    """Verifica que a API responde e que o banco está acessível."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return Response({"status": "error", "detail": "database unavailable"}, status=503)
    return Response({"status": "ok"})
