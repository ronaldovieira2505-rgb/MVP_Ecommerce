from apps.core.state_machine import StateMachine
from apps.payments.models import Custody

C = Custody.Status

CUSTODY_MACHINE = StateMachine(
    "Custody",
    {
        C.PENDING: {C.HELD, C.CANCELLED},
        C.HELD: {C.HELD, C.CLOSED},  # RETIDA → RETIDA: lançamentos parciais
        C.CANCELLED: set(),
        C.CLOSED: set(),
    },
)
