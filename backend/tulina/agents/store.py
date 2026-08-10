from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import (
    AgentRun,
    AgentRunDetail,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    WatchCycleRequest,
)


class AgentStoreError(RuntimeError):
    pass


class SQLiteAgentStore:
    """Durable workflow and tool timeline for local fixture execution."""

    def __init__(self, database: str | Path):
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
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                workflow TEXT NOT NULL,
                status TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                provider TEXT NOT NULL,
                model_name TEXT,
                queue_backend TEXT NOT NULL,
                request_payload TEXT NOT NULL,
                result_transfer_id TEXT,
                event_authors TEXT NOT NULL,
                error_code TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_steps (
                step_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
                UNIQUE (run_id, sequence),
                UNIQUE (run_id, agent_name)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created
                ON agent_runs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_agent_steps_run_sequence
                ON agent_steps(run_id, sequence);
            """
        )
        self._connection.commit()

    def reset(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM agent_steps")
            self._connection.execute("DELETE FROM agent_runs")

    def enqueue(
        self,
        *,
        request: WatchCycleRequest,
        requested_by: str,
        provider: str,
        model_name: str | None,
        queue_backend: str,
    ) -> AgentRun:
        now = datetime.now(UTC)
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
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO agent_runs(
                       run_id, workflow, status, trace_id, requested_by, provider,
                       model_name, queue_backend, request_payload, event_authors,
                       created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.run_id,
                    run.workflow,
                    run.status.value,
                    run.trace_id,
                    run.requested_by,
                    run.provider,
                    run.model_name,
                    run.queue_backend,
                    run.request.model_dump_json(),
                    "[]",
                    now.isoformat(),
                ),
            )
        return run

    def claim_next(self) -> AgentRun | None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """SELECT run_id FROM agent_runs
                       WHERE status=? ORDER BY created_at, run_id LIMIT 1""",
                    (AgentRunStatus.QUEUED.value,),
                ).fetchone()
                if row is None:
                    self._connection.commit()
                    return None
                now = datetime.now(UTC).isoformat()
                self._connection.execute(
                    "UPDATE agent_runs SET status=?, started_at=? WHERE run_id=? AND status=?",
                    (
                        AgentRunStatus.RUNNING.value,
                        now,
                        row["run_id"],
                        AgentRunStatus.QUEUED.value,
                    ),
                )
                self._connection.commit()
                return self.get_run(row["run_id"])
            except Exception:
                self._connection.rollback()
                raise

    def get_run(self, run_id: str) -> AgentRun:
        row = self._connection.execute(
            "SELECT * FROM agent_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise AgentStoreError(f"Unknown agent run {run_id}")
        return self._run_from_row(row)

    def latest_run(self) -> AgentRun | None:
        row = self._connection.execute(
            "SELECT * FROM agent_runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
        ).fetchone()
        return self._run_from_row(row) if row is not None else None

    def detail(self, run_id: str) -> AgentRunDetail:
        return AgentRunDetail(run=self.get_run(run_id), steps=self.steps(run_id))

    def latest_detail(self) -> AgentRunDetail | None:
        run = self.latest_run()
        return self.detail(run.run_id) if run else None

    def start_step(self, *, run_id: str, agent_name: str, tool_name: str) -> AgentStep:
        now = datetime.now(UTC)
        with self._lock, self._connection:
            sequence_row = self._connection.execute(
                "SELECT COUNT(*) AS count FROM agent_steps WHERE run_id=?", (run_id,)
            ).fetchone()
            step = AgentStep(
                step_id=f"STEP-{uuid4().hex[:12].upper()}",
                run_id=run_id,
                sequence=int(sequence_row["count"]) + 1,
                agent_name=agent_name,
                tool_name=tool_name,
                status=AgentStepStatus.RUNNING,
                summary=f"{agent_name} started",
                started_at=now,
            )
            self._connection.execute(
                """INSERT INTO agent_steps(
                       step_id, run_id, sequence, agent_name, tool_name, status,
                       summary, evidence, started_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    step.step_id,
                    step.run_id,
                    step.sequence,
                    step.agent_name,
                    step.tool_name,
                    step.status.value,
                    step.summary,
                    "{}",
                    now.isoformat(),
                ),
            )
        return step

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
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE agent_steps
                   SET status=?, summary=?, evidence=?, completed_at=? WHERE step_id=?""",
                (
                    status.value,
                    summary,
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                    step_id,
                ),
            )
        return self._step_by_id(step_id)

    def fail_step(self, step_id: str, *, error_code: str) -> AgentStep:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE agent_steps
                   SET status=?, summary=?, evidence=?, completed_at=? WHERE step_id=?""",
                (
                    AgentStepStatus.FAILED.value,
                    "Agent step stopped and needs review",
                    json.dumps({"error_code": error_code}),
                    datetime.now(UTC).isoformat(),
                    step_id,
                ),
            )
        return self._step_by_id(step_id)

    def complete_run(
        self, run_id: str, *, transfer_id: str, event_authors: tuple[str, ...]
    ) -> AgentRun:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE agent_runs
                   SET status=?, result_transfer_id=?, event_authors=?, completed_at=?
                   WHERE run_id=? AND status=?""",
                (
                    AgentRunStatus.COMPLETED.value,
                    transfer_id,
                    json.dumps(event_authors),
                    datetime.now(UTC).isoformat(),
                    run_id,
                    AgentRunStatus.RUNNING.value,
                ),
            )
        return self.get_run(run_id)

    def fail_run(self, run_id: str, *, error_code: str) -> AgentRun:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE agent_runs SET status=?, error_code=?, completed_at=?
                   WHERE run_id=? AND status IN (?, ?)""",
                (
                    AgentRunStatus.FAILED.value,
                    error_code,
                    datetime.now(UTC).isoformat(),
                    run_id,
                    AgentRunStatus.QUEUED.value,
                    AgentRunStatus.RUNNING.value,
                ),
            )
        return self.get_run(run_id)

    def steps(self, run_id: str) -> tuple[AgentStep, ...]:
        rows = self._connection.execute(
            "SELECT * FROM agent_steps WHERE run_id=? ORDER BY sequence", (run_id,)
        ).fetchall()
        return tuple(self._step_from_row(row) for row in rows)

    def _step_by_id(self, step_id: str) -> AgentStep:
        row = self._connection.execute(
            "SELECT * FROM agent_steps WHERE step_id=?", (step_id,)
        ).fetchone()
        if row is None:
            raise AgentStoreError(f"Unknown agent step {step_id}")
        return self._step_from_row(row)

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> AgentRun:
        return AgentRun(
            run_id=row["run_id"],
            workflow=row["workflow"],
            status=row["status"],
            trace_id=row["trace_id"],
            requested_by=row["requested_by"],
            provider=row["provider"],
            model_name=row["model_name"],
            queue_backend=row["queue_backend"],
            request=WatchCycleRequest.model_validate_json(row["request_payload"]),
            result_transfer_id=row["result_transfer_id"],
            event_authors=tuple(json.loads(row["event_authors"])),
            error_code=row["error_code"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
        )

    @staticmethod
    def _step_from_row(row: sqlite3.Row) -> AgentStep:
        return AgentStep(
            step_id=row["step_id"],
            run_id=row["run_id"],
            sequence=row["sequence"],
            agent_name=row["agent_name"],
            tool_name=row["tool_name"],
            status=row["status"],
            summary=row["summary"],
            evidence=json.loads(row["evidence"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
            ),
        )
