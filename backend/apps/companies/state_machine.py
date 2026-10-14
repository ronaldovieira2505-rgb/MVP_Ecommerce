from apps.companies.models import Company
from apps.core.state_machine import StateMachine

S = Company.VerificationStatus

COMPANY_VERIFICATION_MACHINE = StateMachine(
    "CompanyVerification",
    {
        S.PENDING: {S.APPROVED, S.REJECTED},
        S.APPROVED: set(),
        S.REJECTED: {S.PENDING},
    },
    field="verification_status",
)
