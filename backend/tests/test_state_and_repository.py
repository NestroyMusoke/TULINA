from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.tulina.engine import DomainEngine
from backend.tulina.fixtures import load_fixture
from backend.tulina.models import TransferStatus
from backend.tulina.repository import SQLiteRepository
from backend.tulina.state_machine import InvalidTransition, TransitionContext, transition


class StateMachineTests(unittest.TestCase):
    def test_cannot_skip_human_approval(self) -> None:
        context = TransitionContext("worker", "facility_worker", "try dispatch")
        with self.assertRaises(InvalidTransition):
            transition(TransferStatus.FOUND, TransferStatus.IN_TRANSIT, context)

    def test_only_dho_can_approve(self) -> None:
        context = TransitionContext("worker", "facility_worker", "approve")
        with self.assertRaises(InvalidTransition):
            transition(TransferStatus.AWAITING_APPROVAL, TransferStatus.APPROVED, context)

    def test_only_reconciliation_can_confirm_delivery(self) -> None:
        context = TransitionContext("worker", "facility_worker", "received")
        with self.assertRaises(InvalidTransition):
            transition(TransferStatus.IN_TRANSIT, TransferStatus.DELIVERED, context)


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "tulina.sqlite3"
        self.engine = DomainEngine(load_fixture())
        self.repo = SQLiteRepository(self.database)
        self.repo.seed(self.engine.all_positions(), self.engine.recommendations(), reset=True)

    def tearDown(self) -> None:
        self.repo.close()
        self.temp.cleanup()

    @staticmethod
    def context(actor: str, role: str, reason: str) -> TransitionContext:
        return TransitionContext(actor_id=actor, actor_role=role, reason=reason)

    def move_to_transit(self) -> None:
        self.repo.change_status(
            "TR-027",
            TransferStatus.AWAITING_APPROVAL,
            self.context("steward-agent", "steward_agent", "Policy checks passed"),
        )
        self.repo.change_status(
            "TR-027",
            TransferStatus.APPROVED,
            self.context("APR-DHO-001", "dho_approver", "DHO approved"),
        )
        self.repo.change_status(
            "TR-027",
            TransferStatus.NOTE_ISSUED,
            self.context("dispatch-agent", "dispatch_agent", "Note issued"),
        )
        self.repo.change_status(
            "TR-027",
            TransferStatus.IN_TRANSIT,
            self.context("dispatch-agent", "dispatch_agent", "Stock collected"),
        )

    def test_seed_persists_recommendation_and_positions(self) -> None:
        transfer = self.repo.get_transfer("TR-027")
        self.assertEqual(transfer.quantity, 11)
        self.assertEqual(self.repo.get_position("F01", "P05").on_hand, 60)
        self.assertEqual(self.repo.get_position("F02", "P05").on_hand, 1)
        self.assertTrue(self.repo.verify_audit_chain())

    def test_database_survives_reopen(self) -> None:
        self.repo.close()
        self.repo = SQLiteRepository(self.database)
        self.assertEqual(self.repo.get_transfer("TR-027").batch_id, "BAT-F01-P05-01")
        self.assertTrue(self.repo.verify_audit_chain())

    def test_repository_enforces_transition_rules(self) -> None:
        with self.assertRaises(InvalidTransition):
            self.repo.change_status(
                "TR-027",
                TransferStatus.APPROVED,
                self.context("worker", "facility_worker", "unsafe approval"),
            )
        self.assertEqual(self.repo.get_transfer("TR-027").status, TransferStatus.FOUND)

    def test_exactly_once_inventory_mutation(self) -> None:
        self.move_to_transit()
        key = "TR-027|CAP-TR027-001|DEV-F02-01"
        context = self.context(
            "reconciliation-agent", "reconciliation_agent", "Verified receipt applied"
        )
        self.assertTrue(self.repo.apply_transfer_once("TR-027", key, context))
        self.assertFalse(self.repo.apply_transfer_once("TR-027", key, context))
        self.assertEqual(self.repo.mutation_count("TR-027"), 1)
        self.assertEqual(self.repo.get_position("F01", "P05").on_hand, 49)
        self.assertEqual(self.repo.get_position("F02", "P05").on_hand, 12)
        self.assertEqual(self.repo.get_transfer("TR-027").status, TransferStatus.DELIVERED)
        self.assertTrue(self.repo.verify_audit_chain())

    def test_failed_mutation_rolls_back(self) -> None:
        key = "TR-027|CAP-TR027-001|DEV-F02-01"
        with self.assertRaises(InvalidTransition):
            self.repo.apply_transfer_once(
                "TR-027",
                key,
                self.context("reconciliation-agent", "reconciliation_agent", "too early"),
            )
        self.assertEqual(self.repo.mutation_count("TR-027"), 0)
        self.assertEqual(self.repo.get_position("F01", "P05").on_hand, 60)

    def test_hash_chain_detects_tampering(self) -> None:
        self.assertTrue(self.repo.verify_audit_chain())
        self.repo._connection.execute(
            "UPDATE audit_events SET summary='tampered' WHERE sequence=1"
        )
        self.repo._connection.commit()
        self.assertFalse(self.repo.verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
