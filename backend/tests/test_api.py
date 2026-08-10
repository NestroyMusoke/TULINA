from __future__ import annotations

import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.tulina.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(database=f"{self.temp.name}/api.sqlite3")
        self.client = TestClient(self.app)
        self.dho = {"X-Tulina-Role": "dho_approver"}
        self.worker = {"X-Tulina-Role": "facility_worker"}

    def tearDown(self) -> None:
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
        self.assertEqual(discovered.json()["activity"][-1]["event_type"], "FOUND_NEARBY")
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


if __name__ == "__main__":
    unittest.main()
