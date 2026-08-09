from __future__ import annotations

import unittest

from backend.tulina.engine import DomainEngine
from backend.tulina.fixtures import load_fixture
from backend.tulina.policy import compatible_vehicle, evaluate_transfer


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_fixture()
        cls.engine = DomainEngine(cls.data)
        cls.product = cls.engine.products["P05"]
        cls.batch = next(batch for batch in cls.data.batches if batch.batch_id == "BAT-F01-P05-01")
        cls.donor = cls.engine.stock_position("F01", "P05")
        cls.recipient = cls.engine.facilities["F02"]
        cls.route = cls.engine.routes[("F01", "F02")]
        cls.vehicle = compatible_vehicle(cls.product, cls.data.vehicles, 11)

    def decision(self, **overrides):
        arguments = {
            "donor": self.donor,
            "recipient": self.recipient,
            "product": self.product,
            "batch": self.batch,
            "quantity": 11,
            "route": self.route,
            "vehicle": self.vehicle,
            "approval_threshold": 10,
        }
        arguments.update(overrides)
        return evaluate_transfer(**arguments)

    def test_cold_vehicle_is_required(self) -> None:
        decision = self.decision(vehicle=None)
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.checks["transport"])

    def test_route_is_required(self) -> None:
        decision = self.decision(route=None)
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.checks["route"])

    def test_donor_safety_stock_cannot_be_breached(self) -> None:
        decision = self.decision(quantity=49)
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.checks["donor_cover"])

    def test_recipient_care_level_is_enforced(self) -> None:
        lower_level = self.recipient.model_copy(update={"care_rank": 2})
        decision = self.decision(recipient=lower_level)
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.checks["recipient_level"])

    def test_human_approval_threshold_is_deterministic(self) -> None:
        self.assertTrue(self.decision(quantity=11).human_approval_required)
        self.assertFalse(self.decision(quantity=9).human_approval_required)


if __name__ == "__main__":
    unittest.main()
