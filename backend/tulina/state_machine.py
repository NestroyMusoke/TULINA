from __future__ import annotations

from dataclasses import dataclass

from .models import TransferStatus


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class TransitionContext:
    actor_id: str
    actor_role: str
    reason: str


ALLOWED: dict[TransferStatus, frozenset[TransferStatus]] = {
    TransferStatus.FOUND: frozenset({TransferStatus.AWAITING_APPROVAL}),
    TransferStatus.AWAITING_APPROVAL: frozenset(
        {TransferStatus.APPROVED, TransferStatus.NEEDS_REVIEW, TransferStatus.CANCELLED}
    ),
    TransferStatus.APPROVED: frozenset({TransferStatus.NOTE_ISSUED, TransferStatus.CANCELLED}),
    TransferStatus.NOTE_ISSUED: frozenset({TransferStatus.IN_TRANSIT, TransferStatus.CANCELLED}),
    TransferStatus.IN_TRANSIT: frozenset(
        {TransferStatus.DELIVERED, TransferStatus.NEEDS_REVIEW, TransferStatus.CANCELLED}
    ),
    TransferStatus.DELIVERED: frozenset(),
    TransferStatus.NEEDS_REVIEW: frozenset(
        {TransferStatus.AWAITING_APPROVAL, TransferStatus.CANCELLED}
    ),
    TransferStatus.CANCELLED: frozenset(),
}


def transition(
    current: TransferStatus, target: TransferStatus, context: TransitionContext
) -> TransferStatus:
    if target not in ALLOWED[current]:
        raise InvalidTransition(f"Unsafe transfer transition: {current} -> {target}")
    if target == TransferStatus.APPROVED and context.actor_role != "dho_approver":
        raise InvalidTransition("Only a District Health Officer can approve a transfer")
    if target == TransferStatus.DELIVERED and context.actor_role != "reconciliation_agent":
        raise InvalidTransition("Only verified reconciliation can confirm delivery")
    return target
