from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ..engine import DomainEngine
from ..fixtures import load_fixture
from ..repository import SQLiteRepository
from .models import AgentRunStatus, WatchCycleRequest
from .runtime import build_agent_runtime
from .settings import AgentSettings


async def run_cycle(database: Path, *, reset: bool) -> int:
    engine = DomainEngine(load_fixture())
    repository = SQLiteRepository(database)
    service = None
    try:
        repository.seed(engine.all_positions(), engine.recommendations(), reset=reset)
        service = build_agent_runtime(
            engine=engine,
            repository=repository,
            database=database,
            settings=AgentSettings(),
        )
        if reset:
            service.store.reset()
        queued = service.start_watch_cycle(
            request=WatchCycleRequest(trigger="schedule"), requested_by="scheduled_worker"
        )
        completed = await service.process_next()
        detail = service.detail(queued.run_id)
        print(detail.model_dump_json(indent=2))
        return 0 if completed and completed.status == AgentRunStatus.COMPLETED else 1
    finally:
        if service is not None:
            service.store.close()
        repository.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Tulina's asynchronous Google ADK watch cycle without chat input."
    )
    parser.add_argument(
        "--database", type=Path, default=Path("work/agent-cycle.sqlite3")
    )
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run_cycle(args.database, reset=args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
