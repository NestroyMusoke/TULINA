from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from .models import StockCardIntake


class IntakeStoreError(RuntimeError):
    pass


class IntakeStore(Protocol):
    backend_name: str

    def reset(self) -> None: ...
    def save(self, intake: StockCardIntake) -> StockCardIntake: ...
    def get(self, intake_id: str) -> StockCardIntake: ...
    def latest(self) -> StockCardIntake | None: ...
    def latest_accepted(self) -> StockCardIntake | None: ...


class SQLiteIntakeStore:
    backend_name = "sqlite"
    def __init__(self, database: str | Path):
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS stock_card_intakes (
                intake_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_stock_card_intakes_created
                ON stock_card_intakes(created_at DESC, intake_id DESC);
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def reset(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM stock_card_intakes")

    def save(self, intake: StockCardIntake) -> StockCardIntake:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO stock_card_intakes(
                       intake_id, status, trace_id, payload, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(intake_id) DO UPDATE SET
                       status=excluded.status,
                       payload=excluded.payload,
                       updated_at=excluded.updated_at""",
                (
                    intake.intake_id,
                    intake.status.value,
                    intake.trace_id,
                    intake.model_dump_json(),
                    intake.created_at.isoformat(),
                    intake.updated_at.isoformat(),
                ),
            )
        return intake

    def get(self, intake_id: str) -> StockCardIntake:
        row = self._connection.execute(
            "SELECT payload FROM stock_card_intakes WHERE intake_id=?", (intake_id,)
        ).fetchone()
        if row is None:
            raise IntakeStoreError(f"Unknown stock-card intake {intake_id}")
        return StockCardIntake.model_validate_json(row["payload"])

    def latest(self) -> StockCardIntake | None:
        row = self._connection.execute(
            "SELECT payload FROM stock_card_intakes ORDER BY created_at DESC, intake_id DESC LIMIT 1"
        ).fetchone()
        return StockCardIntake.model_validate_json(row["payload"]) if row else None

    def latest_accepted(self) -> StockCardIntake | None:
        row = self._connection.execute(
            """SELECT payload FROM stock_card_intakes
               WHERE status='ACCEPTED' ORDER BY created_at DESC, intake_id DESC LIMIT 1"""
        ).fetchone()
        return StockCardIntake.model_validate_json(row["payload"]) if row else None
