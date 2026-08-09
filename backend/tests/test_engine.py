from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.tulina.engine import DomainEngine, days_of_cover
from backend.tulina.fixtures import FixtureData, load_fixture
from backend.tulina.metrics import metrics_for
from backend.tulina.models import Product, WatchSignalType

FIXTURE = Path("data/fixtures/tulina_source_pack_v2.json")


class FixtureTests(unittest.TestCase):
    def test_source_safety_invariants(self) -> None:
        data = load_fixture(FIXTURE)
        self.assertFalse(data.raw["metadata"]["contains_patient_data"])
        self.assertFalse(data.raw["metadata"]["contains_private_keys"])
        self.assertTrue(data.raw["crypto_fixture_notes"]["capsule_signature_verified"])
        self.assertEqual(len(data.raw["relay_test_vectors"]), 9)
        self.assertEqual(len(data.facilities), 7)
        self.assertEqual(len(data.products), 10)

    def test_invalid_cold_product_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Product(
                product_id="P99",
                item="Test",
                strength="1",
                transfer_unit="Pack",
                units_per_transfer=1,
                minimum_care_rank=1,
                storage_mode="COLD_2_8",
                storage_min_c=None,
                storage_max_c=8,
                unit_volume_l=1,
            )


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_fixture(FIXTURE)
        cls.engine = DomainEngine(cls.data)
        cls.tr027 = next(
            item for item in cls.engine.recommendations() if item.transfer_id == "TR-027"
        )

    def test_days_of_cover_handles_zero_consumption(self) -> None:
        self.assertEqual(days_of_cover(1, 6), 5)
        self.assertEqual(days_of_cover(12, 6), 60)
        self.assertEqual(days_of_cover(4, 0), 999)

    def test_canonical_stock_positions_are_calculated(self) -> None:
        donor = self.engine.stock_position("F01", "P05")
        recipient = self.engine.stock_position("F02", "P05")
        self.assertEqual((donor.on_hand, donor.monthly_use), (60, 12))
        self.assertEqual((donor.safety_quantity, donor.safe_release_quantity), (12, 48))
        self.assertEqual((recipient.on_hand, recipient.monthly_use), (1, 6))
        self.assertEqual((recipient.target_quantity, recipient.need_quantity), (12, 11))

    def test_watch_derives_need_and_offer(self) -> None:
        signals = self.engine.watch()
        offer = next(
            signal
            for signal in signals
            if signal.signal_type == WatchSignalType.OFFER
            and signal.facility_id == "F01"
            and signal.product_id == "P05"
        )
        need = next(
            signal
            for signal in signals
            if signal.signal_type == WatchSignalType.NEED
            and signal.facility_id == "F02"
            and signal.product_id == "P05"
        )
        self.assertEqual(offer.quantity, 48)
        self.assertEqual(offer.earliest_expiry.isoformat(), "2026-10-15")
        self.assertEqual(need.quantity, 11)

    def test_tr027_is_derived_with_canonical_identity(self) -> None:
        result = self.tr027
        self.assertEqual(result.donor_facility_id, "F01")
        self.assertEqual(result.recipient_facility_id, "F02")
        self.assertEqual(result.product_id, "P05")
        self.assertEqual(result.batch_id, "BAT-F01-P05-01")
        self.assertEqual(result.quantity, 11)
        self.assertEqual(result.route_id, "R-COLD-01")
        self.assertEqual(result.vehicle_id, "VEH-COLD-01")
        self.assertEqual(result.approval_id, "APR-DHO-001")
        self.assertTrue(result.policy.allowed)
        self.assertTrue(result.policy.human_approval_required)
        self.assertTrue(all(result.policy.checks.values()))

    def test_quantity_does_not_come_from_expected_output(self) -> None:
        raw = copy.deepcopy(self.data.raw)
        canonical = next(row for row in raw["expected_transfer_inputs"] if row["transfer_id"] == "TR-027")
        canonical["qty_transfer_units"] = 99
        modified = FixtureData(
            raw=raw,
            facilities=self.data.facilities,
            products=self.data.products,
            batches=self.data.batches,
            consumption=self.data.consumption,
            routes=self.data.routes,
            vehicles=self.data.vehicles,
        )
        result = next(
            item for item in DomainEngine(modified).recommendations() if item.transfer_id == "TR-027"
        )
        self.assertEqual(result.quantity, 11)

    def test_fefo_selects_earliest_available_batch(self) -> None:
        self.assertEqual(self.tr027.batch_id, "BAT-F01-P05-01")
        self.assertEqual(self.tr027.evidence.expiry_date.isoformat(), "2026-10-15")

    def test_evidence_and_metrics_are_traceable(self) -> None:
        evidence = self.tr027.evidence
        self.assertEqual(evidence.donor_cover_before_days, 150)
        self.assertEqual(evidence.donor_cover_after_days, 122)
        self.assertEqual(evidence.recipient_cover_before_days, 5)
        self.assertEqual(evidence.recipient_cover_after_days, 60)
        self.assertAlmostEqual(evidence.route_km, 21.7)
        metrics = metrics_for(self.tr027)
        self.assertEqual(metrics.recipient_cover_restored_days, 55)
        self.assertEqual(metrics.projected_expiry_risk_avoided, 11)

    def test_recommendations_are_deterministic(self) -> None:
        first = [row.model_dump_json() for row in self.engine.recommendations()]
        second = [row.model_dump_json() for row in self.engine.recommendations()]
        self.assertEqual(first, second)

    def test_every_recommendation_passes_all_policy_gates(self) -> None:
        recommendations = self.engine.recommendations()
        self.assertGreater(len(recommendations), 1)
        for recommendation in recommendations:
            self.assertTrue(recommendation.policy.allowed)
            self.assertTrue(all(recommendation.policy.checks.values()))
            self.assertIn("Synthetic demonstration data", recommendation.source_label)


class ContractTests(unittest.TestCase):
    def test_json_schemas_are_versioned_and_parseable(self) -> None:
        paths = sorted(Path("contracts/v1").glob("*.schema.json"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("/v1/", schema["$id"])
            self.assertEqual(schema["type"], "object")
            self.assertTrue(schema["required"])


if __name__ == "__main__":
    unittest.main()
