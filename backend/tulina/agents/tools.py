from __future__ import annotations

from google.adk.tools import FunctionTool

from ..engine import DomainEngine
from ..models import TransferRecommendation, TransferStatus, WatchSignalType
from ..repository import SQLiteRepository
from .models import (
    GateResult,
    GovernanceResult,
    InventorySnapshotResult,
    MatchResult,
    WatchResult,
)


class ToolCatalog:
    """Validated deterministic functions exposed as genuine Google ADK tools."""

    def __init__(self, engine: DomainEngine, repository: SQLiteRepository):
        self.validate_inventory_snapshot = FunctionTool(
            self._validate_inventory_snapshot(engine, repository)
        )
        self.detect_stock_signals = FunctionTool(self._detect_stock_signals(engine))
        self.rank_safe_transfers = FunctionTool(self._rank_safe_transfers(engine))
        self.evaluate_governance = FunctionTool(self._evaluate_governance(repository))
        self.check_dispatch_gate = FunctionTool(self._check_dispatch_gate(repository))
        self.check_reconciliation_gate = FunctionTool(
            self._check_reconciliation_gate(repository)
        )

    @staticmethod
    def _validate_inventory_snapshot(
        engine: DomainEngine, repository: SQLiteRepository
    ):
        def validate_inventory_snapshot(
            recipient_facility_id: str, product_id: str
        ) -> dict[str, object]:
            """Validate the durable stock snapshot before a background watch cycle."""
            positions = engine.all_positions()
            focus = repository.get_position(recipient_facility_id, product_id)
            return InventorySnapshotResult(
                position_count=len(positions),
                focus_on_hand=focus.on_hand,
                source_label="Validated synthetic fixture; not current facility stock",
            ).model_dump(mode="json")

        return validate_inventory_snapshot

    @staticmethod
    def _detect_stock_signals(engine: DomainEngine):
        def detect_stock_signals(
            recipient_facility_id: str, product_id: str
        ) -> dict[str, object]:
            """Calculate district needs and safe offers from validated inventory records."""
            signals = engine.watch()
            needs = [row for row in signals if row.signal_type == WatchSignalType.NEED]
            offers = [row for row in signals if row.signal_type == WatchSignalType.OFFER]
            focus = next(
                (
                    row
                    for row in needs
                    if row.facility_id == recipient_facility_id
                    and row.product_id == product_id
                ),
                None,
            )
            if focus is None:
                raise ValueError("The requested facility and product do not have a stock need")
            position = engine.stock_position(recipient_facility_id, product_id)
            return WatchResult(
                need_count=len(needs),
                offer_count=len(offers),
                focus_need_quantity=focus.quantity,
                focus_days_of_cover=position.days_of_cover,
            ).model_dump(mode="json")

        return detect_stock_signals

    @staticmethod
    def _rank_safe_transfers(engine: DomainEngine):
        def rank_safe_transfers(
            recipient_facility_id: str, product_id: str
        ) -> dict[str, object]:
            """Rank policy-safe transfer candidates for one documented medicine need."""
            candidates = [
                row
                for row in engine.recommendations()
                if row.recipient_facility_id == recipient_facility_id
                and row.product_id == product_id
            ]
            if not candidates:
                raise ValueError("No policy-safe donor matches the requested medicine need")
            selected = max(candidates, key=lambda row: (row.score, row.transfer_id))
            validated = TransferRecommendation.model_validate(selected.model_dump())
            return MatchResult(
                candidate_count=len(candidates), recommendation=validated
            ).model_dump(mode="json")

        return rank_safe_transfers

    @staticmethod
    def _evaluate_governance(repository: SQLiteRepository):
        def evaluate_governance(transfer_id: str) -> dict[str, object]:
            """Revalidate every policy gate and identify the required human authority."""
            recommendation = repository.get_transfer(transfer_id)
            decision = recommendation.policy
            if not decision.allowed or not all(decision.checks.values()):
                raise ValueError("Governance blocked this recommendation")
            return GovernanceResult(
                allowed=True,
                requires_human_approval=decision.human_approval_required,
                decision=decision,
            ).model_dump(mode="json")

        return evaluate_governance

    @staticmethod
    def _check_dispatch_gate(repository: SQLiteRepository):
        def check_dispatch_gate(transfer_id: str) -> dict[str, object]:
            """Check whether human approval allows dispatch; never issue a note here."""
            status = repository.get_transfer(transfer_id).status
            ready = status == TransferStatus.APPROVED
            return GateResult(
                ready=ready,
                transfer_status=status,
                reason=(
                    "Human approval is present"
                    if ready
                    else "Waiting for the District Health Officer"
                ),
            ).model_dump(mode="json")

        return check_dispatch_gate

    @staticmethod
    def _check_reconciliation_gate(repository: SQLiteRepository):
        def check_reconciliation_gate(transfer_id: str) -> dict[str, object]:
            """Check whether a signed receipt is ready; never mutate inventory here."""
            status = repository.get_transfer(transfer_id).status
            ready = status == TransferStatus.IN_TRANSIT
            return GateResult(
                ready=ready,
                transfer_status=status,
                reason=(
                    "A receipt may be verified"
                    if ready
                    else "No signed receipt is ready for reconciliation"
                ),
            ).model_dump(mode="json")

        return check_reconciliation_gate
