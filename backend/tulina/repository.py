from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .models import AuditEvent, StockPosition, TransferRecommendation, TransferStatus
from .observability import audit_context
from .security import sanitize_audit_details
from .state_machine import TransitionContext, transition


class RepositoryError(RuntimeError):
    pass


class Repository(Protocol):
    """Persistence boundary implemented by SQLite and Firestore."""

    backend_name: str

    def reset(self) -> None: ...
    def seed(
        self,
        positions: tuple[StockPosition, ...],
        recommendations: tuple[TransferRecommendation, ...],
        *,
        reset: bool = False,
    ) -> None: ...
    def get_position(self, facility_id: str, product_id: str) -> StockPosition: ...
    def get_transfer(self, transfer_id: str) -> TransferRecommendation: ...
    def list_transfers(self) -> tuple[TransferRecommendation, ...]: ...
    def change_status(
        self, transfer_id: str, target: TransferStatus, context: TransitionContext
    ) -> TransferRecommendation: ...
    def apply_transfer_once(
        self, transfer_id: str, idempotency_key: str, context: TransitionContext
    ) -> bool: ...
    def events(self, trace_id: str | None = None) -> tuple[AuditEvent, ...]: ...
    def audit_status(self) -> dict[str, object]: ...
    def record_event(
        self,
        *,
        trace_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        details: dict[str, object] | None = None,
    ) -> AuditEvent: ...
    def verify_audit_chain(self) -> bool: ...
    def mutation_count(self, transfer_id: str) -> int: ...
    def has_mutation(self, idempotency_key: str) -> bool: ...


class SQLiteRepository:
    """Durable local adapter with transactional state and hash-chained audit."""

    backend_name = "sqlite"

    def __init__(self, database: str | Path = "data/runtime/tulina.sqlite3"):
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS inventory_positions (
                facility_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (facility_id, product_id)
            );
            CREATE TABLE IF NOT EXISTS transfers (
                transfer_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                occurred_at TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT UNIQUE NOT NULL,
                details TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mutation_ledger (
                idempotency_key TEXT PRIMARY KEY,
                transfer_id TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                donor_before INTEGER NOT NULL,
                donor_after INTEGER NOT NULL,
                recipient_before INTEGER NOT NULL,
                recipient_after INTEGER NOT NULL,
                FOREIGN KEY (transfer_id) REFERENCES transfers(transfer_id)
            );
            CREATE INDEX IF NOT EXISTS idx_audit_trace_sequence
                ON audit_events(trace_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_transfer_status
                ON transfers(status);
            """
        )
        self._connection.commit()

    def reset(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM mutation_ledger")
            self._connection.execute("DELETE FROM audit_events")
            self._connection.execute("DELETE FROM transfers")
            self._connection.execute("DELETE FROM inventory_positions")

    def seed(
        self,
        positions: tuple[StockPosition, ...],
        recommendations: tuple[TransferRecommendation, ...],
        *,
        reset: bool = False,
    ) -> None:
        if reset:
            self.reset()
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connection:
            for position in positions:
                self._connection.execute(
                    """INSERT INTO inventory_positions(facility_id, product_id, payload, updated_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(facility_id, product_id)
                       DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
                    (
                        position.facility_id,
                        position.product_id,
                        position.model_dump_json(),
                        now,
                    ),
                )
            for recommendation in recommendations:
                self._connection.execute(
                    """INSERT INTO transfers(transfer_id, status, payload, updated_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(transfer_id) DO NOTHING""",
                    (
                        recommendation.transfer_id,
                        recommendation.status.value,
                        recommendation.model_dump_json(),
                        now,
                    ),
                )
            if not self._connection.execute("SELECT 1 FROM audit_events LIMIT 1").fetchone():
                self._append_event(
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
        row = self._connection.execute(
            "SELECT payload FROM inventory_positions WHERE facility_id=? AND product_id=?",
            (facility_id, product_id),
        ).fetchone()
        if row is None:
            raise RepositoryError(f"Unknown inventory position {facility_id}/{product_id}")
        return StockPosition.model_validate_json(row["payload"])

    def get_transfer(self, transfer_id: str) -> TransferRecommendation:
        row = self._connection.execute(
            "SELECT payload FROM transfers WHERE transfer_id=?", (transfer_id,)
        ).fetchone()
        if row is None:
            raise RepositoryError(f"Unknown transfer {transfer_id}")
        return TransferRecommendation.model_validate_json(row["payload"])

    def list_transfers(self) -> tuple[TransferRecommendation, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM transfers ORDER BY transfer_id"
        ).fetchall()
        return tuple(TransferRecommendation.model_validate_json(row["payload"]) for row in rows)

    def change_status(
        self, transfer_id: str, target: TransferStatus, context: TransitionContext
    ) -> TransferRecommendation:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.get_transfer(transfer_id)
                next_status = transition(current.status, target, context)
                updated = current.model_copy(update={"status": next_status})
                self._connection.execute(
                    "UPDATE transfers SET status=?, payload=?, updated_at=? WHERE transfer_id=?",
                    (
                        next_status.value,
                        updated.model_dump_json(),
                        datetime.now(UTC).isoformat(),
                        transfer_id,
                    ),
                )
                self._append_event(
                    trace_id=f"TRACE-{transfer_id}",
                    actor_id=context.actor_id,
                    event_type=f"TRANSFER_{next_status.value}",
                    summary=context.reason,
                    details={"from": current.status.value, "to": next_status.value},
                )
                self._connection.commit()
                return updated
            except Exception:
                self._connection.rollback()
                raise

    def apply_transfer_once(
        self, transfer_id: str, idempotency_key: str, context: TransitionContext
    ) -> bool:
        """Apply donor/recipient inventory changes and delivery state in one transaction."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if self._connection.execute(
                    "SELECT 1 FROM mutation_ledger WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone():
                    self._append_event(
                        trace_id=f"TRACE-{transfer_id}",
                        actor_id=context.actor_id,
                        event_type="DUPLICATE_IGNORED",
                        summary="Duplicate receipt applied zero inventory mutations",
                        details={"idempotency_key": idempotency_key},
                    )
                    self._connection.commit()
                    return False
                recommendation = self.get_transfer(transfer_id)
                transition(recommendation.status, TransferStatus.DELIVERED, context)
                donor = self.get_position(
                    recommendation.donor_facility_id, recommendation.product_id
                )
                recipient = self.get_position(
                    recommendation.recipient_facility_id, recommendation.product_id
                )
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
                now = datetime.now(UTC).isoformat()
                for position in (updated_donor, updated_recipient):
                    self._connection.execute(
                        "UPDATE inventory_positions SET payload=?, updated_at=? WHERE facility_id=? AND product_id=?",
                        (
                            position.model_dump_json(),
                            now,
                            position.facility_id,
                            position.product_id,
                        ),
                    )
                delivered = recommendation.model_copy(update={"status": TransferStatus.DELIVERED})
                self._connection.execute(
                    "UPDATE transfers SET status=?, payload=?, updated_at=? WHERE transfer_id=?",
                    (
                        TransferStatus.DELIVERED.value,
                        delivered.model_dump_json(),
                        now,
                        transfer_id,
                    ),
                )
                self._connection.execute(
                    """INSERT INTO mutation_ledger(
                           idempotency_key, transfer_id, applied_at, donor_before, donor_after,
                           recipient_before, recipient_after
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        idempotency_key,
                        transfer_id,
                        now,
                        donor.on_hand,
                        donor_after,
                        recipient.on_hand,
                        recipient_after,
                    ),
                )
                self._append_event(
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
                self._connection.commit()
                return True
            except Exception:
                self._connection.rollback()
                raise

    def events(self, trace_id: str | None = None) -> tuple[AuditEvent, ...]:
        query = "SELECT * FROM audit_events"
        args: tuple[str, ...] = ()
        if trace_id:
            query += " WHERE trace_id=?"
            args = (trace_id,)
        query += " ORDER BY sequence"
        rows = self._connection.execute(query, args).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def audit_status(self) -> dict[str, object]:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count, MAX(sequence) AS last_sequence FROM audit_events"
        ).fetchone()
        head = self._connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return {
            "verified": self.verify_audit_chain(),
            "event_count": int(row["count"]),
            "last_sequence": int(row["last_sequence"] or 0),
            "head_hash": head["event_hash"] if head else "GENESIS",
            "verified_at": datetime.now(UTC).isoformat(),
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
        """Append a non-state-changing operational event to the audit chain."""
        with self._lock, self._connection:
            return self._append_event(
                trace_id=trace_id,
                actor_id=actor_id,
                event_type=event_type,
                summary=summary,
                details=details or {},
            )

    def verify_audit_chain(self) -> bool:
        previous = "GENESIS"
        for event in self.events():
            if event.previous_hash != previous:
                return False
            expected = self._event_hash(
                previous_hash=event.previous_hash,
                occurred_at=event.occurred_at.isoformat(),
                trace_id=event.trace_id,
                actor_id=event.actor_id,
                event_type=event.event_type,
                summary=event.summary,
                details=event.details,
            )
            if expected != event.event_hash:
                return False
            previous = event.event_hash
        return True

    def mutation_count(self, transfer_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM mutation_ledger WHERE transfer_id=?", (transfer_id,)
        ).fetchone()
        return int(row["count"])

    def has_mutation(self, idempotency_key: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM mutation_ledger WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            is not None
        )

    def _append_event(
        self,
        *,
        trace_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        details: dict[str, object],
    ) -> AuditEvent:
        safe_details = sanitize_audit_details({**details, **audit_context()})
        previous_row = self._connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous_row["event_hash"] if previous_row else "GENESIS"
        occurred_at = datetime.now(UTC)
        event_hash = self._event_hash(
            previous_hash=previous_hash,
            occurred_at=occurred_at.isoformat(),
            trace_id=trace_id,
            actor_id=actor_id,
            event_type=event_type,
            summary=summary,
            details=safe_details,
        )
        event_id = f"EVT-{uuid4().hex[:12].upper()}"
        cursor = self._connection.execute(
            """INSERT INTO audit_events(
                   event_id, occurred_at, trace_id, actor_id, event_type, summary,
                   previous_hash, event_hash, details
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                occurred_at.isoformat(),
                trace_id,
                actor_id,
                event_type,
                summary,
                previous_hash,
                event_hash,
                json.dumps(safe_details, sort_keys=True, separators=(",", ":")),
            ),
        )
        return AuditEvent(
            event_id=event_id,
            sequence=cursor.lastrowid,
            occurred_at=occurred_at,
            trace_id=trace_id,
            actor_id=actor_id,
            event_type=event_type,
            summary=summary,
            previous_hash=previous_hash,
            event_hash=event_hash,
            details=safe_details,
        )

    @staticmethod
    def _event_hash(
        *,
        previous_hash: str,
        occurred_at: str,
        trace_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        details: dict[str, object],
    ) -> str:
        canonical = json.dumps(
            {
                "previous_hash": previous_hash,
                "occurred_at": occurred_at,
                "trace_id": trace_id,
                "actor_id": actor_id,
                "event_type": event_type,
                "summary": summary,
                "details": details,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            event_id=row["event_id"],
            sequence=row["sequence"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            trace_id=row["trace_id"],
            actor_id=row["actor_id"],
            event_type=row["event_type"],
            summary=row["summary"],
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
            details=json.loads(row["details"]),
        )
