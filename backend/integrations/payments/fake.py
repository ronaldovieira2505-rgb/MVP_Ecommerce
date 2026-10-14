"""PSP simulado: determinístico, sem rede. Usado em desenvolvimento e nos testes."""

from hashlib import sha1

from integrations.payments.base import GatewayResult, PaymentGateway, PaymentGatewayError


class FakePaymentGateway(PaymentGateway):
    def __init__(self):
        self.operations = {}  # idempotency_key -> (operação, valor)
        self.fail = False  # simula indisponibilidade do PSP

    def _execute(self, operation, idempotency_key, amount_cents):
        if idempotency_key in self.operations:
            return GatewayResult(reference=self._reference(operation, idempotency_key))
        if self.fail:
            raise PaymentGatewayError("PSP simulado indisponível.")
        self.operations[idempotency_key] = (operation, amount_cents)
        return GatewayResult(reference=self._reference(operation, idempotency_key))

    @staticmethod
    def _reference(operation, idempotency_key):
        return f"fake-{operation}-{sha1(idempotency_key.encode()).hexdigest()[:12]}"

    def hold(self, *, idempotency_key, amount_cents):
        return self._execute("hold", idempotency_key, amount_cents)

    def release(self, *, idempotency_key, amount_cents, destination):
        return self._execute("release", idempotency_key, amount_cents)

    def refund(self, *, idempotency_key, amount_cents):
        return self._execute("refund", idempotency_key, amount_cents)
