from __future__ import annotations

from typing import Protocol

from .models import AgentRun, WatchCycleRequest
from .store import SQLiteAgentStore


class JobQueue(Protocol):
    backend_name: str

    def enqueue(
        self,
        *,
        request: WatchCycleRequest,
        requested_by: str,
        provider: str,
        model_name: str | None,
    ) -> AgentRun: ...


class LocalJobQueue:
    backend_name = "local"

    def __init__(self, store: SQLiteAgentStore):
        self.store = store

    def enqueue(
        self,
        *,
        request: WatchCycleRequest,
        requested_by: str,
        provider: str,
        model_name: str | None,
    ) -> AgentRun:
        return self.store.enqueue(
            request=request,
            requested_by=requested_by,
            provider=provider,
            model_name=model_name,
            queue_backend=self.backend_name,
        )


class PubSubJobQueue:
    """Publish durable run references for a Cloud Run push worker."""

    backend_name = "pubsub"

    def __init__(
        self,
        *,
        store: SQLiteAgentStore,
        project_id: str,
        topic: str,
        publisher=None,
    ):
        if not project_id:
            raise ValueError("A Google Cloud project is required for Pub/Sub")
        if publisher is None:
            from google.cloud import pubsub_v1

            publisher = pubsub_v1.PublisherClient()
        self.store = store
        self.publisher = publisher
        self.topic_path = publisher.topic_path(project_id, topic)

    def enqueue(
        self,
        *,
        request: WatchCycleRequest,
        requested_by: str,
        provider: str,
        model_name: str | None,
    ) -> AgentRun:
        run = self.store.enqueue(
            request=request,
            requested_by=requested_by,
            provider=provider,
            model_name=model_name,
            queue_backend=self.backend_name,
        )
        payload = run.model_dump_json().encode("utf-8")
        try:
            self.publisher.publish(
                self.topic_path,
                payload,
                schema_version="1.0",
                workflow=run.workflow,
                trace_id=run.trace_id,
            ).result(timeout=15)
        except Exception as exc:
            self.store.fail_run(run.run_id, error_code="PUBSUB_PUBLISH_FAILED")
            raise RuntimeError("Tulina could not publish the workflow job") from exc
        return run
