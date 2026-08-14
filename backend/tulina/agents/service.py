from __future__ import annotations

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..repository import Repository
from .fleet import FleetDependencies, TulinaFleetAgent
from .models import AgentRun, AgentRunDetail, MatchResult, WatchCycleRequest
from .queue import JobQueue
from .store import AgentStore

ADK_APP_NAME = "agents"


class AgentWorkflowService:
    def __init__(
        self,
        *,
        fleet: TulinaFleetAgent,
        store: AgentStore,
        repository: Repository,
        queue: JobQueue,
        dependencies: FleetDependencies,
    ):
        self.fleet = fleet
        self.store = store
        self.repository = repository
        self.queue = queue
        self.dependencies = dependencies
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app=App(name=ADK_APP_NAME, root_agent=fleet),
            session_service=self.session_service,
        )

    def start_watch_cycle(
        self, *, request: WatchCycleRequest, requested_by: str
    ) -> AgentRun:
        run = self.queue.enqueue(
            request=request,
            requested_by=requested_by,
            provider=self.dependencies.provider.name,
            model_name=self.dependencies.provider.model_name,
        )
        self.repository.record_event(
            trace_id=run.trace_id,
            actor_id="agent_runtime",
            event_type="AGENT_RUN_QUEUED",
            summary="District watch cycle queued for background processing",
            details={
                "run_id": run.run_id,
                "queue_backend": run.queue_backend,
                "trigger": request.trigger,
            },
        )
        return run

    async def process_next(self) -> AgentRun | None:
        run = self.store.claim_next()
        return await self._process_claimed(run)

    async def process_run(self, run_id: str) -> AgentRun | None:
        """Claim one Pub/Sub referenced run; duplicate deliveries become no-ops."""
        run = self.store.claim(run_id)
        return await self._process_claimed(run)

    async def _process_claimed(self, run: AgentRun | None) -> AgentRun | None:
        if run is None:
            return None
        self.repository.record_event(
            trace_id=run.trace_id,
            actor_id="agent_runtime",
            event_type="AGENT_RUN_STARTED",
            summary="Google ADK began the district watch cycle",
            details={"run_id": run.run_id, "root_agent": self.fleet.name},
        )
        event_authors: list[str] = []
        try:
            await self.session_service.create_session(
                app_name=ADK_APP_NAME,
                user_id=run.requested_by,
                session_id=run.run_id,
                state={
                    "run_id": run.run_id,
                    "trace_id": run.trace_id,
                    "request": run.request.model_dump(mode="json"),
                },
            )
            message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Scheduled district inventory event: run the validated "
                            "background watch workflow."
                        )
                    )
                ],
            )
            async for event in self.runner.run_async(
                user_id=run.requested_by,
                session_id=run.run_id,
                new_message=message,
            ):
                if event.author and event.author != "user":
                    event_authors.append(event.author)
            session = await self.session_service.get_session(
                app_name=ADK_APP_NAME,
                user_id=run.requested_by,
                session_id=run.run_id,
            )
            if session is None or "match_result" not in session.state:
                raise RuntimeError("ADK workflow finished without a validated match")
            match = MatchResult.model_validate(session.state["match_result"])
            completed = self.store.complete_run(
                run.run_id,
                transfer_id=match.recommendation.transfer_id,
                event_authors=tuple(event_authors),
            )
            self.repository.record_event(
                trace_id=run.trace_id,
                actor_id="agent_runtime",
                event_type="AGENT_RUN_COMPLETED",
                summary="Background fleet completed and left the decision with a human",
                details={
                    "run_id": run.run_id,
                    "transfer_id": match.recommendation.transfer_id,
                    "adk_event_count": len(event_authors),
                },
            )
            return completed
        except Exception as exc:
            error_code = type(exc).__name__.upper()
            failed = self.store.fail_run(run.run_id, error_code=error_code)
            self.repository.record_event(
                trace_id=run.trace_id,
                actor_id="agent_runtime",
                event_type="AGENT_RUN_FAILED",
                summary="Background fleet stopped and routed the run for review",
                details={"run_id": run.run_id, "error_code": error_code},
            )
            return failed

    def detail(self, run_id: str) -> AgentRunDetail:
        return self.store.detail(run_id)

    def latest_detail(self) -> AgentRunDetail | None:
        return self.store.latest_detail()
