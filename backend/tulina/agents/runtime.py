from __future__ import annotations

from pathlib import Path

from ..engine import DomainEngine
from ..repository import SQLiteRepository
from .fleet import FleetDependencies, build_fleet
from .providers import build_decision_provider
from .queue import LocalJobQueue, PubSubJobQueue
from .service import AgentWorkflowService
from .settings import AgentSettings
from .store import SQLiteAgentStore
from .tools import ToolCatalog


def build_agent_runtime(
    *,
    engine: DomainEngine,
    repository: SQLiteRepository,
    database: str | Path,
    settings: AgentSettings | None = None,
    publisher=None,
) -> AgentWorkflowService:
    settings = settings or AgentSettings()
    store = SQLiteAgentStore(database)
    provider = build_decision_provider(settings)
    tools = ToolCatalog(engine, repository)
    dependencies = FleetDependencies(
        engine=engine,
        repository=repository,
        store=store,
        tools=tools,
        provider=provider,
        step_delay_ms=settings.demo_step_delay_ms,
    )
    if settings.queue_backend == "pubsub":
        queue = PubSubJobQueue(
            store=store,
            project_id=settings.pubsub_project or settings.google_cloud_project or "",
            topic=settings.pubsub_topic,
            publisher=publisher,
        )
    else:
        queue = LocalJobQueue(store)
    return AgentWorkflowService(
        fleet=build_fleet(dependencies),
        store=store,
        repository=repository,
        queue=queue,
        dependencies=dependencies,
    )
