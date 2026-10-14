"""Motor genérico de máquinas de estado.

Cada app declara sua tabela de transições (`state_machine.py`) e só altera `status`
por meio de `transition()`, que valida a origem com `select_for_update` e grava um
`StateTransition` na mesma transação.
"""

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import InvalidTransition
from apps.core.models import StateTransition


class StateMachine:
    def __init__(self, entity_type, transitions, field="status"):
        self.entity_type = entity_type
        self.field = field
        self.transitions = {origin: frozenset(dest) for origin, dest in transitions.items()}

    def validate(self, from_state, to_state):
        if to_state not in self.transitions.get(from_state, frozenset()):
            raise InvalidTransition(
                f"Transição não permitida em {self.entity_type}: {from_state} → {to_state}."
            )

    def is_final(self, state):
        return not self.transitions.get(state)


def record_creation(instance, machine, *, actor=None, reason="", now=None):
    """Registra o estado inicial (origem vazia) de uma entidade recém-criada."""
    return StateTransition.objects.create(
        entity_type=machine.entity_type,
        entity_id=instance.pk,
        from_state="",
        to_state=getattr(instance, machine.field),
        actor=actor,
        reason=reason,
        created_at=now or timezone.now(),
    )


def transition(instance, machine, to_state, *, actor=None, reason="", now=None, **changes):
    """Executa uma transição listada ou lança `InvalidTransition` sem gravar nada.

    `actor=None` significa SISTEMA. `changes` são campos extras gravados junto.
    """
    with transaction.atomic():
        locked = type(instance)._default_manager.select_for_update().get(pk=instance.pk)
        from_state = getattr(locked, machine.field)
        machine.validate(from_state, to_state)
        setattr(locked, machine.field, to_state)
        for field, value in changes.items():
            setattr(locked, field, value)
        locked.save()
        StateTransition.objects.create(
            entity_type=machine.entity_type,
            entity_id=locked.pk,
            from_state=from_state,
            to_state=to_state,
            actor=actor,
            reason=reason,
            created_at=now or timezone.now(),
        )
    instance.refresh_from_db()
    return instance
