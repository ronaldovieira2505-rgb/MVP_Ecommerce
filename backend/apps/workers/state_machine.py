from apps.core.state_machine import StateMachine
from apps.workers.models import Worker

S = Worker.VerificationStatus

WORKER_VERIFICATION_MACHINE = StateMachine(
    "WorkerVerification",
    {
        S.PENDING_DOCUMENTS: {S.IN_REVIEW},
        S.IN_REVIEW: {S.APPROVED, S.REJECTED},
        S.APPROVED: set(),
        S.REJECTED: {S.IN_REVIEW},
    },
    field="verification_status",
)
