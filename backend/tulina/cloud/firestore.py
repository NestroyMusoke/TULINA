from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from ..agents.models import (
    AgentRun,
    AgentRunDetail,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    WatchCycleRequest,
)
from ..agents.store import AgentStoreError
from ..intake.models import StockCardIntake
from ..intake.store import IntakeStoreError
from ..models import AuditEvent, StockPosition, TransferRecommendation, TransferStatus
from ..observability import audit_context
from ..protocol.models import (
    DeviceRegistration,
    QuarantineCase,
    ReconciliationDecision,
    ReconciliationResult,
    SignedReceipt,
    SignedTulinaNote,
)
from ..protocol.store import ProtocolStoreError
from ..repository import RepositoryError, SQLiteRepository
from ..security import sanitize_audit_details
from ..state_machine import TransitionContext, transition
from .document_store import DocumentStore, DocumentTransaction


def _now() -> datetime:
    return datetime.now(UTC)


def _json(model) -> dict[str, object]:
    return model.model_dump(mode="json")


class FirestoreRepository:
    """Authoritative cloud inventory, workflow, idempotency, and audit adapter."""

    backend_name = "firestore"
    _collections = ("inventory", "transfers", "audit_events", "mutations", "meta")

    def __init__(self, store: DocumentStore):
        self.store = store

    @staticmethod
    def _position_id(facility_id: str, product_id: str) -> str:
        return f"{facility_id}__{product_id}"

    @staticmethod
    def _mutation_id(idempotency_key: str) -> str:
        return hashlib.sha256(idempotency_key.encode()).hexdigest()

    def reset(self) -> None:
        for collection in self._collections:
            self.store.delete_all(collection)

    def seed(
        self,
        positions: tuple[StockPosition, ...],
        recommendations: tuple[TransferRecommendation, ...],
        *,
        reset: bool = False,
    ) -> None:
        if reset:
            self.reset()
        now = _now().isoformat()
        for position in positions:
            self.store.set(
                "inventory",
                self._position_id(position.facility_id, position.product_id),
                {"payload": _json(position), "updated_at": now},
            )
        for recommendation in recommendations:
            if self.store.get("transfers", recommendation.transfer_id) is None:
                self.store.set(
                    "transfers",
                    recommendation.transfer_id,
                    {
                        "transfer_id": recommendation.transfer_id,
                        "status": recommendation.status.value,
                        "payload": _json(recommendation),
                        "updated_at": now,
                    },
                )
        if self.store.get("meta", "audit_chain") is None:
            self.record_event(
                trace_id="TRACE-SEED",
                actor_id="fixture-importer",
                event_type="FIXTURE_SEEDED",
                summary="Validated synthetic fixture state loaded",
                details={
                    "positions": len(positions),
                    "recommendations": len(recommendations),
                },
            )

    def get_position(self, facility_id: str, product_id: str) -> StockPosition:
        row = self.store.get("inventory", self._position_id(facility_id, product_id))
        if row is None:
            raise RepositoryError(f"Unknown inventory position {facility_id}/{product_id}")
        return StockPosition.model_validate(row["payload"])

    def get_transfer(self, transfer_id: str) -> TransferRecommendation:
        row = self.store.get("transfers", transfer_id)
        if row is None:
            raise RepositoryError(f"Unknown transfer {transfer_id}")
        return TransferRecommendation.model_validate(row["payload"])

    def list_transfers(self) -> tuple[TransferRecommendation, ...]:
        rows = self.store.list("transfers", order=(("transfer_id", "asc"),))
        values = [TransferRecommendation.model_validate(row["payload"]) for row in rows]
        return tuple(sorted(values, key=lambda item: item.transfer_id))

    def change_status(
        self, transfer_id: str, target: TransferStatus, context: TransitionContext
    ) -> TransferRecommendation:
        def operation(tx: DocumentTransaction) -> TransferRecommendation:
            row = tx.get("transfers", transfer_id)
            if row is None:
                raise RepositoryError(f"Unknown transfer {transfer_id}")
            current = TransferRecommendation.model_validate(row["payload"])
            next_status = transition(current.status, target, context)
            updated = current.model_copy(update={"status": next_status})
            self._append_event_tx(
                tx,
                trace_id=f"TRACE-{transfer_id}",
                actor_id=context.actor_id,
                event_type=f"TRANSFER_{next_status.value}",
                summary=context.reason,
                details={"from": current.status.value, "to": next_status.value},
            )
            tx.set(
                "transfers",
                transfer_id,
                {
                    "transfer_id": transfer_id,
                    "status": next_status.value,
                    "payload": _json(updated),
                    "updated_at": _now().isoformat(),
                },
            )
            return updated

        return self.store.run_transaction(operation)

    def apply_transfer_once(
        self, transfer_id: str, idempotency_key: str, context: TransitionContext
    ) -> bool:
        mutation_id = self._mutation_id(idempotency_key)

        def operation(tx: DocumentTransaction) -> bool:
            if tx.get("mutations", mutation_id) is not None:
                self._append_event_tx(
                    tx,
                    trace_id=f"TRACE-{transfer_id}",
                    actor_id=context.actor_id,
                    event_type="DUPLICATE_IGNORED",
                    summary="Duplicate receipt applied zero inventory mutations",
                    details={"idempotency_key": idempotency_key},
                )
                return False
            transfer_row = tx.get("transfers", transfer_id)
            if transfer_row is None:
                raise RepositoryError(f"Unknown transfer {transfer_id}")
            recommendation = TransferRecommendation.model_validate(transfer_row["payload"])
            transition(recommendation.status, TransferStatus.DELIVERED, context)
            donor_id = self._position_id(
                recommendation.donor_facility_id, recommendation.product_id
            )
            recipient_id = self._position_id(
                recommendation.recipient_facility_id, recommendation.product_id
            )
            donor_row = tx.get("inventory", donor_id)
            recipient_row = tx.get("inventory", recipient_id)
            if donor_row is None or recipient_row is None:
                raise RepositoryError("Transfer inventory position is missing")
            donor = StockPosition.model_validate(donor_row["payload"])
            recipient = StockPosition.model_validate(recipient_row["payload"])
            donor_after = donor.on_hand - recommendation.quantity
            recipient_after = recipient.on_hand + recommendation.quantity
            if donor_after < donor.safety_quantity:
                raise RepositoryError("Mutation would breach protected donor safety stock")
            updated_donor = donor.model_copy(
                update={
                    "on_hand": donor_after,
                    "days_of_cover": round(donor_after / donor.monthly_use * 30),
                    "safe_release_quantity": max(0, donor_after - donor.safety_quantity),
                }
            )
            updated_recipient = recipient.model_copy(
                update={
                    "on_hand": recipient_after,
                    "days_of_cover": round(recipient_after / recipient.monthly_use * 30),
                    "need_quantity": max(0, recipient.target_quantity - recipient_after),
                }
            )
            now = _now().isoformat()
            self._append_event_tx(
                tx,
                trace_id=f"TRACE-{transfer_id}",
                actor_id=context.actor_id,
                event_type="TRANSFER_DELIVERED",
                summary=context.reason,
                details={
                    "idempotency_key": idempotency_key,
                    "mutation_count": 1,
                    "donor_before": donor.on_hand,
                    "donor_after": donor_after,
                    "recipient_before": recipient.on_hand,
                    "recipient_after": recipient_after,
                },
            )
            tx.set("inventory", donor_id, {"payload": _json(updated_donor), "updated_at": now})
            tx.set(
                "inventory", recipient_id, {"payload": _json(updated_recipient), "updated_at": now}
            )
            delivered = recommendation.model_copy(update={"status": TransferStatus.DELIVERED})
            tx.set(
                "transfers",
                transfer_id,
                {
                    "transfer_id": transfer_id,
                    "status": TransferStatus.DELIVERED.value,
                    "payload": _json(delivered),
                    "updated_at": now,
                },
            )
            tx.set(
                "mutations",
                mutation_id,
                {
                    "idempotency_key": idempotency_key,
                    "transfer_id": transfer_id,
                    "applied_at": now,
                    "donor_before": donor.on_hand,
                    "donor_after": donor_after,
                    "recipient_before": recipient.on_hand,
                    "recipient_after": recipient_after,
                },
            )
            return True

        return self.store.run_transaction(operation)

    def events(self, trace_id: str | None = None) -> tuple[AuditEvent, ...]:
        filters = (("trace_id", "==", trace_id),) if trace_id else ()
        rows = self.store.list(
            "audit_events", filters=filters, order=(("sequence", "asc"),)
        )
        return tuple(AuditEvent.model_validate(row["payload"]) for row in rows)

    def audit_status(self) -> dict[str, object]:
        meta = self.store.get("meta", "audit_chain") or {}
        return {
            "verified": self.verify_audit_chain(),
            "event_count": int(meta.get("last_sequence", 0)),
            "last_sequence": int(meta.get("last_sequence", 0)),
            "head_hash": str(meta.get("head_hash", "GENESIS")),
            "verified_at": _now().isoformat(),
        }

    def record_event(
        self,
        *,
        trace_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        details: dict[str, object] | None = None,
    ) -> AuditEvent:
        return self.store.run_transaction(
            lambda tx: self._append_event_tx(
                tx,
                trace_id=trace_id,
                actor_id=actor_id,
                event_type=event_type,
                summary=summary,
                details=details or {},
            )
        )

    def verify_audit_chain(self) -> bool:
        previous = "GENESIS"
        for event in self.events():
            if event.previous_hash != previous:
                return False
            expected = SQLiteRepository._event_hash(
                previous_hash=event.previous_hash,
                occurred_at=event.occurred_at.isoformat(),
                trace_id=event.trace_id,
                actor_id=event.actor_id,
                event_type=event.event_type,
                summary=event.summary,
                details=event.details,
            )
            if event.event_hash != expected:
                return False
            previous = event.event_hash
        meta = self.store.get("meta", "audit_chain") or {}
        return previous == str(meta.get("head_hash", "GENESIS"))

    def mutation_count(self, transfer_id: str) -> int:
        return len(self.store.list("mutations", filters=(("transfer_id", "==", transfer_id),)))

    def has_mutation(self, idempotency_key: str) -> bool:
        return self.store.get("mutations", self._mutation_id(idempotency_key)) is not None

    def _append_event_tx(
        self,
        tx: DocumentTransaction,
        *,
        trace_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        details: dict[str, object],
    ) -> AuditEvent:
        safe_details = sanitize_audit_details({**details, **audit_context()})
        meta = tx.get("meta", "audit_chain") or {
            "last_sequence": 0,
            "head_hash": "GENESIS",
        }
        sequence = int(meta["last_sequence"]) + 1
        previous_hash = str(meta["head_hash"])
        occurred_at = _now()
        event_hash = SQLiteRepository._event_hash(
            previous_hash=previous_hash,
            occurred_at=occurred_at.isoformat(),
            trace_id=trace_id,
            actor_id=actor_id,
            event_type=event_type,
            summary=summary,
            details=safe_details,
        )
        event = AuditEvent(
            event_id=f"EVT-{uuid4().hex[:12].upper()}",
            sequence=sequence,
            occurred_at=occurred_at,
            trace_id=trace_id,
            actor_id=actor_id,
            event_type=event_type,
            summary=summary,
            previous_hash=previous_hash,
            event_hash=event_hash,
            details=safe_details,
        )
        tx.set(
            "audit_events",
            f"{sequence:020d}",
            {"sequence": sequence, "trace_id": trace_id, "payload": _json(event)},
        )
        tx.set(
            "meta",
            "audit_chain",
            {"last_sequence": sequence, "head_hash": event_hash},
        )
        return event


class FirestoreAgentStore:
    backend_name = "firestore"

    def __init__(self, store: DocumentStore):
        self.store = store

    def reset(self) -> None:
        self.store.delete_all("agent_steps")
        self.store.delete_all("agent_runs")

    def enqueue(
        self,
        *,
        request: WatchCycleRequest,
        requested_by: str,
        provider: str,
        model_name: str | None,
        queue_backend: str,
    ) -> AgentRun:
        now = _now()
        run = AgentRun(
            run_id=f"RUN-{uuid4().hex[:12].upper()}",
            status=AgentRunStatus.QUEUED,
            trace_id=f"TRACE-AGENT-{uuid4().hex[:10].upper()}",
            requested_by=requested_by,
            provider=provider,
            model_name=model_name,
            queue_backend=queue_backend,
            request=request,
            created_at=now,
        )
        self.store.set(
            "agent_runs",
            run.run_id,
            {
                "run_id": run.run_id,
                "status": run.status.value,
                "created_at": now.isoformat(),
                "step_count": 0,
                "payload": _json(run),
            },
        )
        return run

    def claim(self, run_id: str) -> AgentRun | None:
        def operation(tx: DocumentTransaction) -> AgentRun | None:
            row = tx.get("agent_runs", run_id)
            if row is None:
                raise AgentStoreError(f"Unknown agent run {run_id}")
            run = AgentRun.model_validate(row["payload"])
            if run.status != AgentRunStatus.QUEUED:
                return None
            updated = run.model_copy(update={"status": AgentRunStatus.RUNNING, "started_at": _now()})
            tx.set(
                "agent_runs",
                run_id,
                {**row, "status": updated.status.value, "payload": _json(updated)},
            )
            return updated

        return self.store.run_transaction(operation)

    def claim_next(self) -> AgentRun | None:
        candidates = self.store.list(
            "agent_runs",
            filters=(("status", "==", AgentRunStatus.QUEUED.value),),
            order=(("created_at", "asc"),),
            limit=5,
        )
        for row in candidates:
            claimed = self.claim(str(row["run_id"]))
            if claimed is not None:
                return claimed
        return None

    def get_run(self, run_id: str) -> AgentRun:
        row = self.store.get("agent_runs", run_id)
        if row is None:
            raise AgentStoreError(f"Unknown agent run {run_id}")
        return AgentRun.model_validate(row["payload"])

    def latest_run(self) -> AgentRun | None:
        rows = self.store.list("agent_runs", order=(("created_at", "desc"),), limit=1)
        return AgentRun.model_validate(rows[0]["payload"]) if rows else None

    def detail(self, run_id: str) -> AgentRunDetail:
        return AgentRunDetail(run=self.get_run(run_id), steps=self.steps(run_id))

    def latest_detail(self) -> AgentRunDetail | None:
        run = self.latest_run()
        return self.detail(run.run_id) if run else None

    def start_step(self, *, run_id: str, agent_name: str, tool_name: str) -> AgentStep:
        def operation(tx: DocumentTransaction) -> AgentStep:
            row = tx.get("agent_runs", run_id)
            if row is None:
                raise AgentStoreError(f"Unknown agent run {run_id}")
            sequence = int(row.get("step_count", 0)) + 1
            step = AgentStep(
                step_id=f"STEP-{uuid4().hex[:12].upper()}",
                run_id=run_id,
                sequence=sequence,
                agent_name=agent_name,
                tool_name=tool_name,
                status=AgentStepStatus.RUNNING,
                summary=f"{agent_name} started",
                started_at=_now(),
            )
            tx.set("agent_runs", run_id, {**row, "step_count": sequence})
            tx.set(
                "agent_steps",
                step.step_id,
                {"run_id": run_id, "sequence": sequence, "payload": _json(step)},
            )
            return step

        return self.store.run_transaction(operation)

    def finish_step(
        self,
        step_id: str,
        *,
        status: AgentStepStatus,
        summary: str,
        evidence: dict[str, object],
    ) -> AgentStep:
        if status not in {AgentStepStatus.COMPLETED, AgentStepStatus.WAITING}:
            raise AgentStoreError(f"Invalid successful step status {status}")
        return self._update_step(
            step_id,
            status=status,
            summary=summary,
            evidence=evidence,
        )

    def fail_step(self, step_id: str, *, error_code: str) -> AgentStep:
        return self._update_step(
            step_id,
            status=AgentStepStatus.FAILED,
            summary="Agent step stopped and needs review",
            evidence={"error_code": error_code},
        )

    def _update_step(
        self,
        step_id: str,
        *,
        status: AgentStepStatus,
        summary: str,
        evidence: dict[str, object],
    ) -> AgentStep:
        row = self.store.get("agent_steps", step_id)
        if row is None:
            raise AgentStoreError(f"Unknown agent step {step_id}")
        step = AgentStep.model_validate(row["payload"]).model_copy(
            update={
                "status": status,
                "summary": summary,
                "evidence": evidence,
                "completed_at": _now(),
            }
        )
        self.store.set("agent_steps", step_id, {**row, "payload": _json(step)})
        return step

    def complete_run(
        self, run_id: str, *, transfer_id: str, event_authors: tuple[str, ...]
    ) -> AgentRun:
        return self._finish_run(
            run_id,
            status=AgentRunStatus.COMPLETED,
            result_transfer_id=transfer_id,
            event_authors=event_authors,
        )

    def fail_run(self, run_id: str, *, error_code: str) -> AgentRun:
        return self._finish_run(
            run_id, status=AgentRunStatus.FAILED, error_code=error_code
        )

    def _finish_run(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        result_transfer_id: str | None = None,
        event_authors: tuple[str, ...] = (),
        error_code: str | None = None,
    ) -> AgentRun:
        row = self.store.get("agent_runs", run_id)
        if row is None:
            raise AgentStoreError(f"Unknown agent run {run_id}")
        run = AgentRun.model_validate(row["payload"])
        if run.status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED}:
            return run
        updated = run.model_copy(
            update={
                "status": status,
                "result_transfer_id": result_transfer_id,
                "event_authors": event_authors,
                "error_code": error_code,
                "completed_at": _now(),
            }
        )
        self.store.set(
            "agent_runs",
            run_id,
            {**row, "status": status.value, "payload": _json(updated)},
        )
        return updated

    def steps(self, run_id: str) -> tuple[AgentStep, ...]:
        rows = self.store.list(
            "agent_steps",
            filters=(("run_id", "==", run_id),),
            order=(("sequence", "asc"),),
        )
        return tuple(AgentStep.model_validate(row["payload"]) for row in rows)


class FirestoreIntakeStore:
    backend_name = "firestore"

    def __init__(self, store: DocumentStore):
        self.store = store

    def reset(self) -> None:
        self.store.delete_all("stock_card_intakes")

    def save(self, intake: StockCardIntake) -> StockCardIntake:
        self.store.set(
            "stock_card_intakes",
            intake.intake_id,
            {
                "intake_id": intake.intake_id,
                "status": intake.status.value,
                "created_at": intake.created_at.isoformat(),
                "payload": _json(intake),
            },
        )
        return intake

    def get(self, intake_id: str) -> StockCardIntake:
        row = self.store.get("stock_card_intakes", intake_id)
        if row is None:
            raise IntakeStoreError(f"Unknown stock-card intake {intake_id}")
        return StockCardIntake.model_validate(row["payload"])

    def latest(self) -> StockCardIntake | None:
        rows = self.store.list(
            "stock_card_intakes", order=(("created_at", "desc"),), limit=1
        )
        return StockCardIntake.model_validate(rows[0]["payload"]) if rows else None

    def latest_accepted(self) -> StockCardIntake | None:
        rows = self.store.list(
            "stock_card_intakes",
            filters=(("status", "==", "ACCEPTED"),),
            order=(("created_at", "desc"),),
            limit=1,
        )
        return StockCardIntake.model_validate(rows[0]["payload"]) if rows else None


class FirestoreProtocolStore:
    backend_name = "firestore"

    def __init__(self, store: DocumentStore):
        self.store = store

    def reset(self) -> None:
        for collection in (
            "tulina_notes",
            "recipient_devices",
            "offline_receipts",
            "consumed_nonces",
            "reconciliation_results",
            "quarantine_resolutions",
            "protocol_meta",
        ):
            self.store.delete_all(collection)

    def save_note(self, note: SignedTulinaNote) -> None:
        existing = self.note_for_transfer(note.payload.transfer_id)
        if existing is not None and existing.payload.capsule_id != note.payload.capsule_id:
            raise ProtocolStoreError("A different Tulina Note already exists for this transfer")
        self.store.set(
            "tulina_notes",
            note.payload.capsule_id,
            {
                "capsule_id": note.payload.capsule_id,
                "transfer_id": note.payload.transfer_id,
                "created_at": _now().isoformat(),
                "payload": _json(note),
            },
        )

    def get_note(self, capsule_id: str) -> SignedTulinaNote:
        row = self.store.get("tulina_notes", capsule_id)
        if row is None:
            raise ProtocolStoreError("Tulina Note is not registered")
        return SignedTulinaNote.model_validate(row["payload"])

    def note_for_transfer(self, transfer_id: str) -> SignedTulinaNote | None:
        rows = self.store.list(
            "tulina_notes", filters=(("transfer_id", "==", transfer_id),), limit=1
        )
        return SignedTulinaNote.model_validate(rows[0]["payload"]) if rows else None

    def register_device(self, registration: DeviceRegistration) -> None:
        row = self.store.get("recipient_devices", registration.device_id)
        if row is not None:
            existing = DeviceRegistration.model_validate(row["payload"])
            if (
                existing.facility_id != registration.facility_id
                or existing.key_id != registration.key_id
                or existing.public_jwk != registration.public_jwk
            ):
                raise ProtocolStoreError("Device identity is already bound to a different key")
        self.store.set(
            "recipient_devices",
            registration.device_id,
            {
                "device_id": registration.device_id,
                "key_id": registration.key_id,
                "payload": _json(registration),
            },
        )

    def get_device(self, device_id: str) -> DeviceRegistration:
        row = self.store.get("recipient_devices", device_id)
        if row is None:
            raise ProtocolStoreError("Recipient device is not registered")
        return DeviceRegistration.model_validate(row["payload"])

    def save_receipt(self, receipt: SignedReceipt, state: str) -> None:
        self.store.set(
            "offline_receipts",
            receipt.receipt_payload.receipt_id,
            {
                "receipt_id": receipt.receipt_payload.receipt_id,
                "state": state,
                "created_at": _now().isoformat(),
                "payload": _json(receipt),
            },
        )

    def consume_nonce(self, nonce: str, capsule_id: str, receipt_id: str) -> None:
        nonce_id = hashlib.sha256(nonce.encode()).hexdigest()

        def operation(tx: DocumentTransaction) -> None:
            if tx.get("consumed_nonces", nonce_id) is not None:
                raise ProtocolStoreError("Tulina Note nonce is already consumed")
            tx.set(
                "consumed_nonces",
                nonce_id,
                {
                    "nonce": nonce,
                    "capsule_id": capsule_id,
                    "receipt_id": receipt_id,
                    "consumed_at": _now().isoformat(),
                },
            )

        self.store.run_transaction(operation)

    def nonce_consumed(self, nonce: str) -> bool:
        return (
            self.store.get("consumed_nonces", hashlib.sha256(nonce.encode()).hexdigest())
            is not None
        )

    def save_result(self, result: ReconciliationResult) -> None:
        def operation(tx: DocumentTransaction) -> None:
            meta = tx.get("protocol_meta", "results") or {"last_sequence": 0}
            sequence = int(meta["last_sequence"]) + 1
            tx.set("protocol_meta", "results", {"last_sequence": sequence})
            tx.set(
                "reconciliation_results",
                f"{sequence:020d}",
                {
                    "sequence": sequence,
                    "receipt_id": result.receipt_id,
                    "decision": result.decision.value,
                    "created_at": _now().isoformat(),
                    "payload": _json(result),
                },
            )

        self.store.run_transaction(operation)

    def latest_result(self) -> ReconciliationResult | None:
        rows = self.store.list(
            "reconciliation_results", order=(("sequence", "desc"),), limit=1
        )
        return ReconciliationResult.model_validate(rows[0]["payload"]) if rows else None

    def result_for_receipt(self, receipt_id: str) -> ReconciliationResult | None:
        rows = self.store.list(
            "reconciliation_results",
            filters=(("receipt_id", "==", receipt_id),),
            order=(("sequence", "desc"),),
        )
        for row in rows:
            result = ReconciliationResult.model_validate(row["payload"])
            if result.decision == ReconciliationDecision.APPLIED_EXACTLY_ONCE:
                return result
        return None

    def quarantined_count(self) -> int:
        return len(
            self.store.list(
                "reconciliation_results",
                filters=(("decision", "==", ReconciliationDecision.QUARANTINE_CONFLICT.value),),
            )
        )

    def unresolved_quarantined_count(self) -> int:
        return sum(1 for case in self.quarantine_cases() if case.resolution is None)

    def quarantine_cases(self) -> tuple[QuarantineCase, ...]:
        rows = self.store.list(
            "reconciliation_results",
            filters=(("decision", "==", ReconciliationDecision.QUARANTINE_CONFLICT.value),),
            order=(("sequence", "desc"),),
        )
        cases: list[QuarantineCase] = []
        seen: set[str] = set()
        for row in rows:
            result = ReconciliationResult.model_validate(row["payload"])
            if result.receipt_id is None or result.receipt_id in seen:
                continue
            seen.add(result.receipt_id)
            resolution = self.store.get("quarantine_resolutions", result.receipt_id)
            cases.append(
                QuarantineCase(
                    receipt_id=result.receipt_id,
                    transfer_id=result.transfer_id,
                    reason_code=result.reason_code,
                    message=result.message,
                    resolution=(str(resolution["resolution"]) if resolution else None),
                    resolution_note=(str(resolution["note"]) if resolution else None),
                    resolved_by=(str(resolution["resolved_by"]) if resolution else None),
                    resolved_at=(resolution["resolved_at"] if resolution else None),
                )
            )
        return tuple(cases)

    def resolve_quarantine(
        self, receipt_id: str, *, note: str, resolved_by: str
    ) -> QuarantineCase:
        case = next(
            (item for item in self.quarantine_cases() if item.receipt_id == receipt_id),
            None,
        )
        if case is None:
            raise ProtocolStoreError("Quarantined receipt not found")
        if case.resolution is None:
            self.store.set(
                "quarantine_resolutions",
                receipt_id,
                {
                    "resolution": "ACKNOWLEDGE_NO_MUTATION",
                    "note": note,
                    "resolved_by": resolved_by,
                    "resolved_at": _now().isoformat(),
                },
            )
        return next(
            item for item in self.quarantine_cases() if item.receipt_id == receipt_id
        )
