from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from backend.tulina.engine import DomainEngine
from backend.tulina.fixtures import load_fixture
from backend.tulina.models import TransferStatus
from backend.tulina.protocol.crypto import encode_envelope
from backend.tulina.protocol.fixtures import (
    fixture_device,
    fixture_issuer_key,
    fixture_note,
    fixture_receipt,
)
from backend.tulina.protocol.models import (
    OfflineDecision,
    ReconciliationDecision,
    TrustBundle,
)
from backend.tulina.protocol.service import NOTE_PREFIX, ProtocolService
from backend.tulina.protocol.store import SQLiteProtocolStore
from backend.tulina.repository import SQLiteRepository
from backend.tulina.state_machine import TransitionContext


class ProtocolVectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "protocol.sqlite3"
        self.data = load_fixture()
        self.engine = DomainEngine(self.data)
        self.repo = SQLiteRepository(self.database)
        self.repo.seed(self.engine.all_positions(), self.engine.recommendations(), reset=True)
        self.store = SQLiteProtocolStore(self.database)
        self.issuer_key = fixture_issuer_key(self.data.raw)
        self.service = ProtocolService(
            repository=self.repo,
            store=self.store,
            clock=lambda: datetime(2026, 8, 15, 14, 16, tzinfo=UTC),
            trusted_keys=(self.issuer_key,),
        )
        self.note = fixture_note(self.data.raw)
        self.bundle = TrustBundle(
            bundle_id="TRUST-FIXTURE-v1",
            issued_at=datetime(2026, 8, 15, 8, tzinfo=UTC),
            expires_at=datetime(2026, 9, 15, 8, tzinfo=UTC),
            keys=(self.issuer_key,),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.repo.close()
        self.temp.cleanup()

    @staticmethod
    def context(actor: str, role: str, reason: str) -> TransitionContext:
        return TransitionContext(actor_id=actor, actor_role=role, reason=reason)

    def move_to_transit(self) -> None:
        self.repo.change_status(
            "TR-027",
            TransferStatus.AWAITING_APPROVAL,
            self.context("steward_agent", "steward_agent", "Safe move found"),
        )
        self.repo.change_status(
            "TR-027",
            TransferStatus.APPROVED,
            self.context("APR-DHO-001", "dho_approver", "Human approval"),
        )
        self.repo.change_status(
            "TR-027",
            TransferStatus.NOTE_ISSUED,
            self.context("dispatch_agent", "dispatch_agent", "Note issued"),
        )
        self.repo.change_status(
            "TR-027",
            TransferStatus.IN_TRANSIT,
            self.context("dispatch_agent", "dispatch_agent", "Dispatched"),
        )
        self.store.save_note(self.note)
        self.store.register_device(fixture_device(self.data.raw))

    def verify(self, token: str, *, facility: str = "F02", scanned_at: str, consumed=None):
        return self.service.verify_note(
            token,
            trust_bundle=self.bundle,
            device_facility_id=facility,
            scanned_at=datetime.fromisoformat(scanned_at.replace("Z", "+00:00")),
            consumed_nonces=consumed,
        )

    def test_tst_01_valid_offline_receipt_and_reconnect_applies_once(self) -> None:
        self.move_to_transit()
        edge = self.verify(
            self.note.qr_payload,
            scanned_at="2026-08-15T14:12:00Z",
        )
        self.assertEqual(edge.decision, OfflineDecision.ACCEPT_OFFLINE)
        receipt = fixture_receipt(self.data.raw, "TST-01")
        result = self.service.reconcile(receipt.receipt_token)
        self.assertEqual(result.decision, ReconciliationDecision.APPLIED_EXACTLY_ONCE)
        self.assertEqual(result.transfer_mutations_applied, 1)
        self.assertEqual(result.inventory_before, {"donor": 60, "recipient": 1})
        self.assertEqual(result.inventory_after, {"donor": 49, "recipient": 12})

    def test_tst_02_quantity_tamper_fails_signature(self) -> None:
        tampered_canonical = self.note.canonical_payload.replace('"qty":11', '"qty":17')
        tampered = encode_envelope(
            NOTE_PREFIX,
            {
                "key_id": self.note.key_id,
                "canonical_payload": tampered_canonical,
                "signature_base64url": self.note.signature_base64url,
            },
        )
        result = self.verify(tampered, scanned_at="2026-08-15T14:13:00Z")
        self.assertEqual(result.reason_code, "SIGNATURE_INVALID")
        self.assertEqual(result.signature_check, "FAIL")

    def test_tst_03_same_nonce_is_rejected_locally(self) -> None:
        result = self.verify(
            self.note.qr_payload,
            scanned_at="2026-08-15T14:14:00Z",
            consumed={self.note.payload.nonce},
        )
        self.assertEqual(result.reason_code, "NONCE_ALREADY_USED_LOCAL")
        self.assertEqual(result.nonce_check, "FAIL")

    def test_tst_04_wrong_recipient_is_rejected(self) -> None:
        result = self.verify(
            self.note.qr_payload,
            facility="F03",
            scanned_at="2026-08-15T14:13:30Z",
        )
        self.assertEqual(result.reason_code, "RECIPIENT_MISMATCH")

    def test_tst_05_expired_note_is_rejected(self) -> None:
        result = self.verify(self.note.qr_payload, scanned_at="2026-08-16T02:06:00Z")
        self.assertEqual(result.reason_code, "NOTE_EXPIRED")
        self.assertEqual(result.expiry_check, "FAIL")

    def test_tst_06_unknown_issuer_is_rejected_before_signature_check(self) -> None:
        rogue = encode_envelope(
            NOTE_PREFIX,
            {
                "key_id": "KEY-ROGUE-v1",
                "canonical_payload": self.note.canonical_payload,
                "signature_base64url": self.note.signature_base64url,
            },
        )
        result = self.verify(rogue, scanned_at="2026-08-15T14:13:45Z")
        self.assertEqual(result.reason_code, "ISSUER_KEY_NOT_TRUSTED")
        self.assertEqual(result.signature_check, "NOT_EVALUATED")

    def test_tst_07_cloud_state_conflict_is_quarantined(self) -> None:
        self.move_to_transit()
        self.repo.change_status(
            "TR-027",
            TransferStatus.CANCELLED,
            self.context("APR-DHO-001", "dho_approver", "Cancelled during outage"),
        )
        receipt = fixture_receipt(self.data.raw, "TST-07")
        result = self.service.reconcile(receipt.receipt_token)
        self.assertEqual(result.decision, ReconciliationDecision.QUARANTINE_CONFLICT)
        self.assertEqual(result.transfer_mutations_applied, 0)
        self.assertEqual(self.repo.mutation_count("TR-027"), 0)

    def test_tst_08_duplicate_upload_is_idempotent(self) -> None:
        self.move_to_transit()
        receipt = fixture_receipt(self.data.raw, "TST-01")
        first = self.service.reconcile(receipt.receipt_token)
        duplicate = self.service.reconcile(receipt.receipt_token)
        self.assertEqual(first.transfer_mutations_applied, 1)
        self.assertEqual(duplicate.decision, ReconciliationDecision.IDEMPOTENT_ACK)
        self.assertEqual(duplicate.transfer_mutations_applied, 0)
        self.assertEqual(self.repo.mutation_count("TR-027"), 1)

    def test_tst_09_malformed_qr_is_rejected(self) -> None:
        result = self.verify("TULINA1.not-valid-base64", scanned_at="2026-08-15T14:13:50Z")
        self.assertEqual(result.reason_code, "PAYLOAD_UNREADABLE")
        self.assertEqual(result.parse_check, "FAIL")

    def test_source_pack_has_one_test_for_every_protocol_vector(self) -> None:
        self.assertEqual(
            {row["test_id"] for row in self.data.raw["relay_test_vectors"]},
            {f"TST-{index:02d}" for index in range(1, 10)},
        )


if __name__ == "__main__":
    unittest.main()
