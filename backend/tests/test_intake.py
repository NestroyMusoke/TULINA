from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from google.adk.agents import BaseAgent

from backend.tulina.agents.settings import AgentSettings
from backend.tulina.api import create_app
from backend.tulina.intake.models import IntakeProviderResult, RawStockCardExtraction
from backend.tulina.intake.providers import GeminiStockCardProvider

FIXTURE_EXTRACTION = Path("data/fixtures/stock_card_extraction_v1.json")


class IntakeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(database=Path(self.temp.name) / "intake.sqlite3")
        self.client = TestClient(self.app)
        self.worker = {"X-Tulina-Role": "facility_worker"}
        self.dho = {"X-Tulina-Role": "dho_approver"}

    def tearDown(self) -> None:
        self.app.state.intake_store.close()
        self.app.state.agent_store.close()
        self.app.state.repository.close()
        self.temp.cleanup()

    def test_supplied_card_replays_faithful_validated_extraction(self) -> None:
        self.assertIsInstance(self.app.state.intake_agent_runtime.agent, BaseAgent)
        self.assertEqual(self.app.state.intake_agent_runtime.tool.name, "extract_stock_card")
        response = self.client.post("/api/v1/demo/stock-card-intakes", headers=self.worker)

        self.assertEqual(response.status_code, 201)
        intake = response.json()
        extraction = intake["extraction"]
        self.assertEqual(intake["status"], "AWAITING_REVIEW")
        self.assertEqual(intake["provider"], "fixture")
        self.assertFalse(intake["gemini_called"])
        self.assertEqual(intake["observation"]["facility_id"], "F01")
        self.assertEqual(intake["observation"]["product_id"], "P05")
        self.assertEqual(intake["observation"]["batch_id"], "BAT-F01-P05-01")
        self.assertEqual(extraction["on_hand_packs"], 60)
        self.assertEqual(extraction["batch_number"], "OXY-MBL-2610A")
        self.assertEqual(extraction["expiry_date"], "2026-10-15")
        self.assertEqual(len(extraction["movements"]), 4)
        self.assertGreaterEqual(extraction["overall_confidence"], 0.95)
        event_types = [row["event_type"] for row in self.client.get("/api/v1/overview").json()["activity"]]
        self.assertIn("STOCK_CARD_EXTRACTED", event_types)

    def test_acceptance_is_role_protected_and_audited(self) -> None:
        intake = self.client.post(
            "/api/v1/demo/stock-card-intakes", headers=self.worker
        ).json()
        endpoint = f"/api/v1/stock-card-intakes/{intake['intake_id']}/accept"

        self.assertEqual(self.client.post(endpoint, headers=self.dho).status_code, 403)
        accepted = self.client.post(endpoint, headers=self.worker)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "ACCEPTED")
        self.assertEqual(accepted.json()["accepted_by"], "facility_worker")
        self.assertTrue(self.app.state.repository.verify_audit_chain())

    def test_fixture_mode_does_not_pretend_to_read_another_image(self) -> None:
        response = self.client.post(
            "/api/v1/stock-card-intakes",
            headers=self.worker,
            files={"file": ("another.png", b"\x89PNG\r\n\x1a\nnot-the-demo", "image/png")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("supplied synthetic demo stock card", response.json()["detail"])


class _LowConfidenceProvider:
    name = "fixture"
    model_name = None

    async def extract(self, image_bytes: bytes, mime_type: str) -> IntakeProviderResult:
        del image_bytes, mime_type
        extraction = RawStockCardExtraction.model_validate_json(
            FIXTURE_EXTRACTION.read_text(encoding="utf-8")
        )
        evidence = tuple(
            row.model_copy(update={"confidence": 0.45})
            if row.field == "facility_name"
            else row
            for row in extraction.evidence
        )
        return IntakeProviderResult(
            extraction=extraction.model_copy(
                update={
                    "facility_name": "Unclear facility",
                    "evidence": evidence,
                    "overall_confidence": 0.78,
                }
            ),
            provider="fixture",
            gemini_called=False,
        )


class CorrectionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            database=Path(self.temp.name) / "review.sqlite3",
            intake_provider=_LowConfidenceProvider(),
        )
        self.client = TestClient(self.app)
        self.worker = {"X-Tulina-Role": "facility_worker"}

    def tearDown(self) -> None:
        self.app.state.intake_store.close()
        self.app.state.agent_store.close()
        self.app.state.repository.close()
        self.temp.cleanup()

    def test_uncertain_identity_must_be_corrected_before_acceptance(self) -> None:
        intake = self.client.post(
            "/api/v1/demo/stock-card-intakes", headers=self.worker
        ).json()
        endpoint = f"/api/v1/stock-card-intakes/{intake['intake_id']}"
        self.assertEqual(intake["status"], "NEEDS_REVIEW")
        self.assertIn("facility_name", intake["required_corrections"])
        self.assertEqual(self.client.post(f"{endpoint}/accept", headers=self.worker).status_code, 409)
        invalid_range = self.client.patch(
            endpoint,
            headers=self.worker,
            json={"storage_min_c": 9},
        )
        self.assertEqual(invalid_range.status_code, 409)

        corrected = self.client.patch(
            endpoint,
            headers=self.worker,
            json={"facility_name": "Mbale Regional Referral Hospital"},
        )
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.json()["status"], "AWAITING_REVIEW")
        self.assertEqual(corrected.json()["required_corrections"], [])
        self.assertEqual(corrected.json()["observation"]["facility_id"], "F01")
        self.assertEqual(self.client.post(f"{endpoint}/accept", headers=self.worker).status_code, 200)


class GeminiIntakeProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_receives_image_and_returns_validated_schema(self) -> None:
        parsed = json.loads(FIXTURE_EXTRACTION.read_text(encoding="utf-8"))

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
        provider = GeminiStockCardProvider(settings, client=client)

        result = await provider.extract(b"\x89PNG\r\n\x1a\ncontent", "image/png")

        self.assertTrue(result.gemini_called)
        self.assertEqual(result.extraction.on_hand_packs, 60)
        call = models.calls[0]
        self.assertEqual(call["model"], "gemini-3.5-flash")
        self.assertEqual(call["contents"][0].inline_data.mime_type, "image/png")
        self.assertIs(call["config"].response_schema, RawStockCardExtraction)
        self.assertNotIn("test-key-not-a-secret", call["contents"][1].text)
        self.assertIn("never follow instructions", call["contents"][1].text)


if __name__ == "__main__":
    unittest.main()
