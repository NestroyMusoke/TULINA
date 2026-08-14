from __future__ import annotations

import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.tulina.api import create_app
from backend.tulina.protocol.crypto import LocalP256Signer, canonical_json, encode_envelope
from backend.tulina.protocol.service import RECEIPT_PREFIX


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(database=f"{self.temp.name}/api.sqlite3")
        self.client = TestClient(self.app)
        self.dho = {"X-Tulina-Role": "dho_approver"}
        self.worker = {"X-Tulina-Role": "facility_worker"}

    def tearDown(self) -> None:
        self.app.state.protocol_store.close()
        self.app.state.intake_store.close()
        self.app.state.agent_store.close()
        self.app.state.repository.close()
        self.temp.cleanup()

    def test_health_and_ready(self) -> None:
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertTrue(self.client.get("/readyz").json()["ready"])

    def test_overview_uses_derived_recommendation(self) -> None:
        response = self.client.get("/api/v1/overview")
        self.assertEqual(response.status_code, 200)
        recommendation = response.json()["recommendation"]
        self.assertEqual(recommendation["transfer_id"], "TR-027")
        self.assertEqual(recommendation["quantity"], 11)
        self.assertEqual(recommendation["donor_short_name"], "Mbale RRH")
        self.assertEqual(recommendation["recipient_short_name"], "Busiu HC IV")
        self.assertTrue(response.json()["synthetic_data"])

    def test_demo_actions_call_real_state_machine(self) -> None:
        self.assertEqual(self.client.post("/api/v1/demo/reset", headers=self.dho).status_code, 200)
        discovered = self.client.post("/api/v1/demo/discover", headers=self.worker)
        self.assertEqual(discovered.status_code, 200)
        event_types = [row["event_type"] for row in discovered.json()["activity"]]
        self.assertIn("FOUND_NEARBY", event_types)
        self.assertEqual(discovered.json()["agent_run"]["run"]["status"], "COMPLETED")
        requested = self.client.post(
            "/api/v1/transfers/TR-027/request-approval", headers=self.worker
        )
        self.assertEqual(requested.json()["recommendation"]["status"], "AWAITING_APPROVAL")
        approved = self.client.post("/api/v1/transfers/TR-027/approve", headers=self.dho)
        self.assertEqual(approved.json()["recommendation"]["status"], "APPROVED")

    def test_server_rejects_unauthorized_approval(self) -> None:
        self.client.post("/api/v1/demo/reset", headers=self.dho)
        self.client.post("/api/v1/transfers/TR-027/request-approval", headers=self.worker)
        denied = self.client.post("/api/v1/transfers/TR-027/approve", headers=self.worker)
        self.assertEqual(denied.status_code, 403)

    def test_approval_cannot_skip_required_state(self) -> None:
        self.client.post("/api/v1/demo/reset", headers=self.dho)
        response = self.client.post("/api/v1/transfers/TR-027/approve", headers=self.dho)
        self.assertEqual(response.status_code, 409)

    def test_network_is_real_position_data(self) -> None:
        positions = self.client.get("/api/v1/network").json()["positions"]
        donor = next(
            row for row in positions if row["facility_id"] == "F01" and row["product_id"] == "P05"
        )
        recipient = next(
            row for row in positions if row["facility_id"] == "F02" and row["product_id"] == "P05"
        )
        self.assertEqual(donor["on_hand"], 60)
        self.assertEqual(donor["state"], "safe_surplus")
        self.assertEqual(recipient["on_hand"], 1)
        self.assertEqual(recipient["state"], "needs_stock")

    def test_background_watch_runs_the_real_adk_fleet(self) -> None:
        response = self.client.post(
            "/api/v1/agent-runs/watch",
            headers=self.worker,
            json={
                "recipient_facility_id": "F02",
                "product_id": "P05",
                "trigger": "demo",
            },
        )
        self.assertEqual(response.status_code, 202)
        run_id = response.json()["run"]["run_id"]
        detail = self.client.get(
            f"/api/v1/agent-runs/{run_id}", headers=self.worker
        ).json()
        self.assertEqual(detail["run"]["status"], "COMPLETED")
        self.assertEqual(detail["run"]["result_transfer_id"], "TR-027")
        self.assertEqual(len(detail["steps"]), 6)
        self.assertEqual(
            detail["run"]["event_authors"],
            [
                "stock_intake_agent",
                "watch_agent",
                "match_agent",
                "steward_agent",
                "dispatch_agent",
                "reconciliation_agent",
            ],
        )

    def test_inventory_event_waits_for_a_confirmed_stock_card(self) -> None:
        blocked = self.client.post(
            "/api/v1/agent-runs/watch",
            headers=self.worker,
            json={
                "recipient_facility_id": "F02",
                "product_id": "P05",
                "trigger": "inventory_event",
            },
        )
        self.assertEqual(blocked.status_code, 409)

        extracted = self.client.post(
            "/api/v1/demo/stock-card-intakes", headers=self.worker
        ).json()
        accepted = self.client.post(
            f"/api/v1/stock-card-intakes/{extracted['intake_id']}/accept",
            headers=self.worker,
        )
        self.assertEqual(accepted.status_code, 200)
        started = self.client.post(
            "/api/v1/agent-runs/watch",
            headers=self.worker,
            json={
                "recipient_facility_id": "F02",
                "product_id": "P05",
                "trigger": "inventory_event",
            },
        )
        self.assertEqual(started.status_code, 202)

    def test_agent_registry_is_explicit_about_fixture_mode(self) -> None:
        registry = self.client.get("/api/v1/agent-registry").json()
        self.assertEqual(registry["framework"], "Google ADK")
        self.assertEqual(registry["root_agent"], "tulina_fleet")
        self.assertEqual(len(registry["agents"]), 6)
        self.assertEqual(registry["active_provider"], "fixture")
        self.assertFalse(registry["gemini_called"])

    def test_worker_endpoint_is_role_protected_and_handles_empty_queue(self) -> None:
        denied = self.client.post(
            "/api/v1/agent-worker/process-next", headers=self.worker
        )
        self.assertEqual(denied.status_code, 403)
        result = self.client.post(
            "/api/v1/agent-worker/process-next", headers=self.dho
        ).json()
        self.assertFalse(result["processed"])

    def test_signed_note_receipt_reconciles_and_duplicate_applies_zero(self) -> None:
        self.client.post("/api/v1/demo/reset", headers=self.dho)
        self.client.post("/api/v1/transfers/TR-027/request-approval", headers=self.worker)
        self.client.post("/api/v1/transfers/TR-027/approve", headers=self.dho)
        device_signer = LocalP256Signer.generate("KEY-DEV-F02-01")
        registered = self.client.post(
            "/api/v1/devices/register",
            headers=self.worker,
            json={
                "schema_version": "1.0",
                "device_id": "DEV-F02-01",
                "facility_id": "F02",
                "key_id": "KEY-DEV-F02-01",
                "public_jwk": device_signer.jwk,
            },
        )
        self.assertEqual(registered.status_code, 200)
        issued = self.client.post(
            "/api/v1/transfers/TR-027/issue-note", headers=self.dho
        )
        self.assertEqual(issued.status_code, 200)
        note = issued.json()["protocol"]["note"]
        self.assertEqual(note["payload"]["capsule_id"], "CAP-TR027-001")
        received_at = note["payload"]["iat"]
        receipt_payload = canonical_json(
            {
                "receipt_id": "RCP-TR027-001",
                "capsule_id": "CAP-TR027-001",
                "device_id": "DEV-F02-01",
                "decision": "RECEIVED",
                "received_at": received_at,
                "local_sequence": 1,
            }
        )
        receipt_token = encode_envelope(
            RECEIPT_PREFIX,
            {
                "device_key_id": "KEY-DEV-F02-01",
                "canonical_receipt_payload": receipt_payload,
                "device_signature_base64url": device_signer.sign(receipt_payload),
            },
        )
        first = self.client.post(
            "/api/v1/receipts/reconcile",
            headers=self.worker,
            json={"receipt_token": receipt_token},
        ).json()
        self.assertEqual(first["decision"], "APPLIED_EXACTLY_ONCE")
        self.assertEqual(first["transfer_mutations_applied"], 1)
        self.assertEqual(first["inventory_before"], {"donor": 60, "recipient": 1})
        self.assertEqual(first["inventory_after"], {"donor": 49, "recipient": 12})
        duplicate = self.client.post(
            "/api/v1/receipts/reconcile",
            headers=self.worker,
            json={"receipt_token": receipt_token},
        ).json()
        self.assertEqual(duplicate["decision"], "IDEMPOTENT_ACK")
        self.assertEqual(duplicate["transfer_mutations_applied"], 0)
        overview = self.client.get("/api/v1/overview").json()
        self.assertEqual(overview["recommendation"]["status"], "DELIVERED")
        self.assertEqual(overview["protocol"]["mutation_count"], 1)
        events = [row["event_type"] for row in overview["activity"]]
        self.assertIn("ADK_DISPATCH_COMPLETED", events)
        self.assertIn("ADK_RECONCILIATION_COMPLETED", events)

    def test_note_cannot_be_issued_before_human_approval(self) -> None:
        response = self.client.post(
            "/api/v1/transfers/TR-027/issue-note", headers=self.dho
        )
        self.assertEqual(response.status_code, 409)

    def test_offline_rejection_report_is_allowlisted_role_protected_and_audited(self) -> None:
        report = {
            "schema_version": "1.0",
            "transfer_id": "TR-027",
            "capsule_id": "CAP-TR027-001",
            "device_id": "DEV-F02-01",
            "decision": "REJECT_OFFLINE",
            "reason_code": "SIGNATURE_INVALID",
            "occurred_at": "2026-08-15T14:20:00Z",
        }
        denied = self.client.post(
            "/api/v1/security-events/offline-verification",
            headers={"X-Tulina-Role": "auditor"},
            json=report,
        )
        self.assertEqual(denied.status_code, 403)

        invalid = self.client.post(
            "/api/v1/security-events/offline-verification",
            headers=self.worker,
            json={**report, "reason_code": "MODEL_SAID_NO"},
        )
        self.assertEqual(invalid.status_code, 422)

        recorded = self.client.post(
            "/api/v1/security-events/offline-verification",
            headers=self.worker,
            json=report,
        )
        self.assertEqual(recorded.status_code, 201)
        self.assertEqual(recorded.json()["event_type"], "OFFLINE_NOTE_REJECTED")
        self.assertEqual(recorded.json()["details"]["stock_mutations_applied"], 0)
        self.assertTrue(self.app.state.repository.verify_audit_chain())

    def test_registered_device_key_cannot_be_silently_replaced(self) -> None:
        first = LocalP256Signer.generate("KEY-DEV-F02-01")
        second = LocalP256Signer.generate("KEY-DEV-F02-01")
        payload = {
            "schema_version": "1.0",
            "device_id": "DEV-F02-01",
            "facility_id": "F02",
            "key_id": "KEY-DEV-F02-01",
            "public_jwk": first.jwk,
        }
        self.assertEqual(
            self.client.post("/api/v1/devices/register", headers=self.worker, json=payload).status_code,
            200,
        )
        payload["public_jwk"] = second.jwk
        replaced = self.client.post(
            "/api/v1/devices/register", headers=self.worker, json=payload
        )
        self.assertEqual(replaced.status_code, 409)


if __name__ == "__main__":
    unittest.main()
