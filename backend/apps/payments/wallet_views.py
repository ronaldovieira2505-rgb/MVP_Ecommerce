"""`GET /api/workers/me/wallet/` — carteira do prestador autenticado (US60)."""

from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsWorkerUser
from apps.payments.wallet import wallet_for


class WorkerWalletView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsWorkerUser]

    def get(self, request):
        worker = getattr(request.user, "worker", None)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        return Response(wallet_for(worker))
