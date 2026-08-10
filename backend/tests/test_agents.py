from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from google.adk.agents import BaseAgent

from backend.tulina.agents.fleet import FleetDependencies, build_fleet
from backend.tulina.agents.models import (
    AgentRunStatus,
    AgentStepStatus,
    WatchCycleRequest,
)
from backend.tulina.agents.providers import FixtureDecisionProvider, GeminiDecisionProvider
from backend.tulina.agents.queue import LocalJobQueue, PubSubJobQueue
from backend.tulina.agents.service import AgentWorkflowService
from backend.tulina.agents.settings import AgentSettings
from backend.tulina.agents.store import SQLiteAgentStore
from backend.tulina.agents.tools import ToolCatalog
from backend.tulina.engine import DomainEngine
from backend.tulina.fixtures import load_fixture
from backend.tulina.models import TransferStatus
from backend.tulina.repository import SQLiteRepository


class FleetIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "agents.sqlite3"
        self.engine = DomainEngine(load_fixture())
        self.repository = SQLiteRepository(self.database)
        self.repository.seed(
            self.engine.all_positions(), self.engine.recommendations(), reset=True
        )
        self.store = SQLiteAgentStore(self.database)
        self.dependencies = FleetDependencies(
            engine=self.engine,
            repository=self.repository,
            store=self.store,
            tools=ToolCatalog(self.engine, self.repository),
            provider=FixtureDecisionProvider(),
            step_delay_ms=0,
        )
        self.fleet = build_fleet(self.dependencies)
        self.service = AgentWorkflowService(
            fleet=self.fleet,
            store=self.store,
            repository=self.repository,
            queue=LocalJobQueue(self.store),
            dependencies=self.dependencies,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.repository.close()
        self.temp.cleanup()

    def test_google_adk_hierarchy_has_six_real_agents(self) -> None:
        self.assertIsInstance(self.fleet, BaseAgent)
        self.assertEqual(
            [agent.name for agent in self.fleet.sub_agents],
            [
                "stock_intake_agent",
                "watch_agent",
                "match_agent",
                "steward_agent",
                "dispatch_agent",
                "reconciliation_agent",
            ],
        )
        self.assertEqual(self.fleet.find_agent("match_agent").name, "match_agent")

    async def test_background_run_derives_tr027_and_persists_every_step(self) -> None:
        queued = self.service.start_watch_cycle(
            request=WatchCycleRequest(), requested_by="facility_worker"
        )
        self.assertEqual(queued.status, AgentRunStatus.QUEUED)

        completed = await self.service.process_next()

        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, AgentRunStatus.COMPLETED)
        self.assertEqual(completed.result_transfer_id, "TR-027")
        self.assertEqual(len(completed.event_authors), 6)
        steps = self.store.steps(completed.run_id)
        self.assertEqual(len(steps), 6)
        self.assertEqual(steps[2].tool_name, "rank_safe_transfers")
        self.assertEqual(steps[2].evidence["recommendation"]["quantity"], 11)
        self.assertEqual(steps[4].status, AgentStepStatus.WAITING)
        self.assertEqual(steps[5].status, AgentStepStatus.WAITING)
        self.assertEqual(
            self.repository.get_transfer("TR-027").status, TransferStatus.FOUND
        )
        self.assertTrue(self.repository.verify_audit_chain())

    async def test_invalid_focus_fails_closed_and_is_audited(self) -> None:
        queued = self.service.start_watch_cycle(
            request=WatchCycleRequest(
                recipient_facility_id="F01", product_id="P05"
            ),
            requested_by="facility_worker",
        )
        failed = await self.service.process_next()
        self.assertEqual(failed.status, AgentRunStatus.FAILED)
        self.assertEqual(failed.error_code, "VALUEERROR")
        steps = self.store.steps(queued.run_id)
        self.assertEqual(steps[-1].status, AgentStepStatus.FAILED)
        self.assertTrue(self.repository.verify_audit_chain())

    async def test_empty_queue_does_not_repeat_a_run(self) -> None:
        self.assertIsNone(await self.service.process_next())

    async def test_gemini_provider_requests_and_validates_structured_output(self) -> None:
        parsed = {
            "headline": "Safe stock was found nearby",
            "summary": "The validated match retains donor cover and restores Busiu cover.",
            "evidence_points": [
                "All deterministic gates passed.",
                "The route and cold-chain vehicle are compatible.",
            ],
            "human_action": "A District Health Officer must decide.",
        }

        class FakeModels:
            def __init__(self):
                self.calls = []

            async def generate_content(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(parsed=parsed, text="")

        models = FakeModels()
        client = SimpleNamespace(aio=SimpleNamespace(models=models))
        with patch.dict(
            "os.environ",
            {
                "TULINA_MODE": "gemini",
                "GOOGLE_API_KEY": "test-key-not-a-secret",
                "GEMINI_MODEL": "gemini-3.5-flash",
            },
            clear=True,
        ):
            settings = AgentSettings(_env_file=None)
        provider = GeminiDecisionProvider(settings, client=client)
        recommendation = next(
            row for row in self.engine.recommendations() if row.transfer_id == "TR-027"
        )

        explanation = await provider.explain(recommendation)

        self.assertEqual(explanation.human_action, parsed["human_action"])
        self.assertEqual(models.calls[0]["model"], "gemini-3.5-flash")
        self.assertNotIn("test-key-not-a-secret", models.calls[0]["contents"])


class _PublishFuture:
    def result(self, timeout: int):
        return "message-1"


class _FakePublisher:
    def __init__(self):
        self.published = []

    @staticmethod
    def topic_path(project_id: str, topic: str) -> str:
        return f"projects/{project_id}/topics/{topic}"

    def publish(self, topic_path: str, payload: bytes, **attributes):
        self.published.append((topic_path, payload, attributes))
        return _PublishFuture()


class QueueAndSettingsTests(unittest.TestCase):
    def test_pubsub_adapter_publishes_only_a_durable_run_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteAgentStore(Path(temp) / "queue.sqlite3")
            publisher = _FakePublisher()
            queue = PubSubJobQueue(
                store=store,
                project_id="demo-project",
                topic="tulina-workflows",
                publisher=publisher,
            )
            run = queue.enqueue(
                request=WatchCycleRequest(),
                requested_by="facility_worker",
                provider="fixture",
                model_name=None,
            )
            self.assertEqual(run.queue_backend, "pubsub")
            self.assertEqual(
                publisher.published[0][0],
                "projects/demo-project/topics/tulina-workflows",
            )
            self.assertIn(run.run_id.encode(), publisher.published[0][1])
            self.assertEqual(publisher.published[0][2]["schema_version"], "1.0")
            store.close()

    def test_live_mode_rejects_missing_credentials(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "TULINA_MODE": "gemini",
                "GOOGLE_API_KEY": "",
                "GOOGLE_GENAI_USE_VERTEXAI": "false",
                "GEMINI_MODEL": "gemini-3.5-flash",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                AgentSettings(_env_file=None)

    def test_models_older_than_gemini_35_are_rejected(self) -> None:
        with patch.dict(
            "os.environ",
            {"TULINA_MODE": "fixture", "GEMINI_MODEL": "gemini-2.5-flash"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                AgentSettings(_env_file=None)


if __name__ == "__main__":
    unittest.main()
