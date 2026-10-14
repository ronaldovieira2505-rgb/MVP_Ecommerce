"""Tabelas de transição de Vaga, Candidatura e Alocação (docs/maquina-de-estados.md)."""

from apps.core.state_machine import StateMachine
from apps.vacancies.models import Application, Assignment, Vacancy

V = Vacancy.Status
A = Application.Status
S = Assignment.Status

VACANCY_MACHINE = StateMachine(
    "Vacancy",
    {
        V.AWAITING_PAYMENT: {V.PUBLISHED, V.CANCELLED},
        V.PUBLISHED: {V.APPLICATIONS_CLOSED, V.CANCELLED},
        V.APPLICATIONS_CLOSED: {V.IN_PROGRESS, V.CANCELLED},
        V.IN_PROGRESS: {V.FINISHED},
        V.FINISHED: set(),
        V.CANCELLED: set(),
    },
)

APPLICATION_MACHINE = StateMachine(
    "Application",
    {
        A.PENDING: {A.APPROVED, A.REJECTED, A.WITHDRAWN, A.EXPIRED},
        A.APPROVED: set(),
        A.REJECTED: set(),
        A.WITHDRAWN: set(),
        A.EXPIRED: set(),
    },
)

ASSIGNMENT_MACHINE = StateMachine(
    "Assignment",
    {
        S.CONFIRMED: {S.IN_PROGRESS, S.NO_SHOW, S.CANCELLED_BY_WORKER, S.CANCELLED_BY_COMPANY},
        S.IN_PROGRESS: {S.AWAITING_VALIDATION},
        S.AWAITING_VALIDATION: {S.APPROVED, S.CONTESTED},
        S.CONTESTED: {S.APPROVED, S.REFUNDED},
        S.APPROVED: {S.PAID},
        S.PAID: set(),
        S.NO_SHOW: set(),
        S.REFUNDED: set(),
        S.CANCELLED_BY_WORKER: set(),
        S.CANCELLED_BY_COMPANY: set(),
    },
)
