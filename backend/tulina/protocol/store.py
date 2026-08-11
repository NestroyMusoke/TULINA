from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from .crypto import LocalP256Signer
from .models import (
    DeviceRegistration,
    ReconciliationResult,
    SignedReceipt,
    SignedTulinaNote,
)


class ProtocolStoreError(RuntimeError):
    pass


class SQLiteProtocolStore:
    def __init__(self, database: str | Path):
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS protocol_signing_keys (
                key_id TEXT PRIMARY KEY,
                private_pem BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tulina_notes (
                capsule_id TEXT PRIMARY KEY,
                transfer_id TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recipient_devices (
                device_id TEXT PRIMARY KEY,
                facility_id TEXT NOT NULL,
                key_id TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS offline_receipts (
                receipt_id TEXT PRIMARY KEY,
                capsule_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                reconciliation_state TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS consumed_nonces (
                nonce TEXT PRIMARY KEY,
                capsule_id TEXT UNIQUE NOT NULL,
                receipt_id TEXT UNIQUE NOT NULL,
                consumed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reconciliation_results (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id TEXT,
                decision TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_protocol_results_receipt
                ON reconciliation_results(receipt_id, sequence);
            """
        )
        self._connection.commit()

    def reset(self) -> None:
        """Reset demo protocol state while retaining the local issuer identity."""
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM reconciliation_results")
            self._connection.execute("DELETE FROM consumed_nonces")
            self._connection.execute("DELETE FROM offline_receipts")
            self._connection.execute("DELETE FROM recipient_devices")
            self._connection.execute("DELETE FROM tulina_notes")

    def get_or_create_signer(self, key_id: str = "KEY-TULINA-LOCAL-v1") -> LocalP256Signer:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT private_pem FROM protocol_signing_keys WHERE key_id=?", (key_id,)
            ).fetchone()
            if row:
                return LocalP256Signer.from_pem(key_id, bytes(row["private_pem"]))
            signer = LocalP256Signer.generate(key_id)
            self._connection.execute(
                "INSERT INTO protocol_signing_keys(key_id, private_pem, created_at) VALUES (?, ?, ?)",
                (key_id, signer.private_pem(), datetime.now(UTC).isoformat()),
            )
            return signer

    def save_note(self, note: SignedTulinaNote) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO tulina_notes(capsule_id, transfer_id, payload, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(capsule_id) DO UPDATE SET payload=excluded.payload""",
                (
                    note.payload.capsule_id,
                    note.payload.transfer_id,
                    note.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_note(self, capsule_id: str) -> SignedTulinaNote:
        row = self._connection.execute(
            "SELECT payload FROM tulina_notes WHERE capsule_id=?", (capsule_id,)
        ).fetchone()
        if row is None:
            raise ProtocolStoreError("Tulina Note is not registered")
        return SignedTulinaNote.model_validate_json(row["payload"])

    def note_for_transfer(self, transfer_id: str) -> SignedTulinaNote | None:
        row = self._connection.execute(
            "SELECT payload FROM tulina_notes WHERE transfer_id=?", (transfer_id,)
        ).fetchone()
        return SignedTulinaNote.model_validate_json(row["payload"]) if row else None

    def register_device(self, registration: DeviceRegistration) -> None:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT facility_id, key_id, payload FROM recipient_devices WHERE device_id=?",
                (registration.device_id,),
            ).fetchone()
            if existing and (
                existing["facility_id"] != registration.facility_id
                or existing["key_id"] != registration.key_id
                or DeviceRegistration.model_validate_json(existing["payload"]).public_jwk
                != registration.public_jwk
            ):
                raise ProtocolStoreError("Device identity is already bound to a different key")
            self._connection.execute(
                """INSERT INTO recipient_devices(device_id, facility_id, key_id, payload, registered_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(device_id) DO UPDATE SET payload=excluded.payload""",
                (
                    registration.device_id,
                    registration.facility_id,
                    registration.key_id,
                    registration.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_device(self, device_id: str) -> DeviceRegistration:
        row = self._connection.execute(
            "SELECT payload FROM recipient_devices WHERE device_id=?", (device_id,)
        ).fetchone()
        if row is None:
            raise ProtocolStoreError("Recipient device is not registered")
        return DeviceRegistration.model_validate_json(row["payload"])

    def save_receipt(self, receipt: SignedReceipt, state: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO offline_receipts(
                       receipt_id, capsule_id, device_id, payload, reconciliation_state, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(receipt_id) DO UPDATE SET reconciliation_state=excluded.reconciliation_state""",
                (
                    receipt.receipt_payload.receipt_id,
                    receipt.receipt_payload.capsule_id,
                    receipt.receipt_payload.device_id,
                    receipt.model_dump_json(),
                    state,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def consume_nonce(self, nonce: str, capsule_id: str, receipt_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO consumed_nonces(nonce, capsule_id, receipt_id, consumed_at) VALUES (?, ?, ?, ?)",
                (nonce, capsule_id, receipt_id, datetime.now(UTC).isoformat()),
            )

    def nonce_consumed(self, nonce: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM consumed_nonces WHERE nonce=?", (nonce,)
            ).fetchone()
            is not None
        )

    def save_result(self, result: ReconciliationResult) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO reconciliation_results(receipt_id, decision, payload, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    result.receipt_id,
                    result.decision.value,
                    result.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def latest_result(self) -> ReconciliationResult | None:
        row = self._connection.execute(
            "SELECT payload FROM reconciliation_results ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return ReconciliationResult.model_validate_json(row["payload"]) if row else None

    def result_for_receipt(self, receipt_id: str) -> ReconciliationResult | None:
        row = self._connection.execute(
            """SELECT payload FROM reconciliation_results
               WHERE receipt_id=? AND decision='APPLIED_EXACTLY_ONCE'
               ORDER BY sequence DESC LIMIT 1""",
            (receipt_id,),
        ).fetchone()
        return ReconciliationResult.model_validate_json(row["payload"]) if row else None

    def quarantined_count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM reconciliation_results WHERE decision='QUARANTINE_CONFLICT'"
        ).fetchone()
        return int(row["count"])
