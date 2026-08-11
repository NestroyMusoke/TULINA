from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from ..models import TransferStatus
from ..repository import RepositoryError, SQLiteRepository
from ..state_machine import TransitionContext
from .crypto import (
    LocalP256Signer,
    canonical_json,
    decode_envelope,
    encode_envelope,
    fingerprint,
    verify_raw_signature,
)
from .models import (
    DeviceRegistration,
    NotePayload,
    NoteVerification,
    OfflineDecision,
    ProtocolSummary,
    PublicKey,
    ReceiptPayload,
    ReconciliationDecision,
    ReconciliationResult,
    SignedReceipt,
    SignedTulinaNote,
    TrustBundle,
)
from .store import ProtocolStoreError, SQLiteProtocolStore

NOTE_PREFIX = "TULINA1"
RECEIPT_PREFIX = "TULINA_RECEIPT1"


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProtocolError(RuntimeError):
    pass


class ProtocolService:
    def __init__(
        self,
        *,
        repository: SQLiteRepository,
        store: SQLiteProtocolStore,
        clock: Callable[[], datetime] | None = None,
        trusted_keys: tuple[PublicKey, ...] | None = None,
    ):
        self.repository = repository
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        self.signer: LocalP256Signer = store.get_or_create_signer()
        self.trusted_keys = trusted_keys
        self._lock = threading.RLock()

    def trust_bundle(self) -> TrustBundle:
        now = _utc(self.clock())
        jwk = self.signer.jwk
        keys = self.trusted_keys or (
            PublicKey(
                key_id=self.signer.key_id,
                public_jwk=jwk,
                fingerprint=fingerprint(jwk),
            ),
        )
        return TrustBundle(
            bundle_id=f"TRUST-{self.signer.key_id}",
            issued_at=now,
            expires_at=now + timedelta(days=30),
            keys=keys,
        )

    def issue_note(self, transfer_id: str = "TR-027") -> SignedTulinaNote:
        with self._lock:
            existing = self.store.note_for_transfer(transfer_id)
            transfer = self.repository.get_transfer(transfer_id)
            if existing and transfer.status == TransferStatus.IN_TRANSIT:
                return existing
            if transfer.status != TransferStatus.APPROVED:
                raise ProtocolError("A DHO approval is required before issuing a Tulina Note")
            now = _utc(self.clock()).replace(microsecond=0)
            values: dict[str, object] = {
                "v": 1,
                "capsule_id": "CAP-TR027-001",
                "transfer_id": transfer.transfer_id,
                "issuer": "dispatch_agent",
                "donor": transfer.donor_facility_id,
                "recipient": transfer.recipient_facility_id,
                "product": transfer.product_id,
                "batch": transfer.batch_id,
                "qty": transfer.quantity,
                "approval": transfer.approval_id,
                "iat": _timestamp(now),
                "exp": _timestamp(now + timedelta(hours=12)),
                "nonce": "n_7G4WQ3M8HX2V9K1P",
            }
            if existing:
                note = existing
            else:
                canonical_payload = canonical_json(values)
                signature = self.signer.sign(canonical_payload)
                qr_payload = encode_envelope(
                    NOTE_PREFIX,
                    {
                        "key_id": self.signer.key_id,
                        "canonical_payload": canonical_payload,
                        "signature_base64url": signature,
                    },
                )
                note = SignedTulinaNote(
                    key_id=self.signer.key_id,
                    canonical_payload=canonical_payload,
                    signature_base64url=signature,
                    qr_payload=qr_payload,
                    payload=NotePayload.model_validate(values),
                )
                self.store.save_note(note)
            context = TransitionContext(
                actor_id="dispatch_agent",
                actor_role="dispatch_agent",
                reason="Signed one-use Tulina Note issued after human approval",
            )
            self.repository.change_status(transfer_id, TransferStatus.NOTE_ISSUED, context)
            self.repository.change_status(
                transfer_id,
                TransferStatus.IN_TRANSIT,
                TransitionContext(
                    actor_id="dispatch_agent",
                    actor_role="dispatch_agent",
                    reason="Tulina Note ready for designated Busiu recipient device",
                ),
            )
            return note

    def register_device(self, registration: DeviceRegistration) -> DeviceRegistration:
        if registration.device_id != "DEV-F02-01" or registration.facility_id != "F02":
            raise ProtocolError("Only the designated Busiu receiving device can register in this demo")
        self.store.register_device(registration)
        self.repository.record_event(
            trace_id="TRACE-TR-027",
            actor_id=registration.device_id,
            event_type="RECIPIENT_DEVICE_READY",
            summary="Designated device cached trust and registered its receipt key",
            details={"facility_id": registration.facility_id, "key_id": registration.key_id},
        )
        return registration

    @staticmethod
    def decode_note(token: str) -> SignedTulinaNote:
        envelope = decode_envelope(NOTE_PREFIX, token)
        if set(envelope) != {"key_id", "canonical_payload", "signature_base64url"}:
            raise ValueError("Unexpected Tulina Note fields")
        canonical_payload = str(envelope["canonical_payload"])
        raw_payload = json.loads(canonical_payload)
        payload = NotePayload.model_validate(raw_payload)
        return SignedTulinaNote(
            key_id=str(envelope["key_id"]),
            canonical_payload=canonical_payload,
            signature_base64url=str(envelope["signature_base64url"]),
            qr_payload=token,
            payload=payload,
        )

    @staticmethod
    def decode_receipt(token: str) -> SignedReceipt:
        envelope = decode_envelope(RECEIPT_PREFIX, token)
        if set(envelope) != {
            "device_key_id",
            "canonical_receipt_payload",
            "device_signature_base64url",
        }:
            raise ValueError("Unexpected receipt fields")
        canonical_payload = str(envelope["canonical_receipt_payload"])
        payload = ReceiptPayload.model_validate_json(canonical_payload)
        return SignedReceipt(
            device_key_id=str(envelope["device_key_id"]),
            canonical_receipt_payload=canonical_payload,
            device_signature_base64url=str(envelope["device_signature_base64url"]),
            receipt_payload=payload,
            receipt_token=token,
        )

    @staticmethod
    def verify_note(
        token: str,
        *,
        trust_bundle: TrustBundle,
        device_facility_id: str,
        scanned_at: datetime,
        consumed_nonces: set[str] | None = None,
    ) -> NoteVerification:
        skipped = "NOT_EVALUATED"
        try:
            note = ProtocolService.decode_note(token)
        except (ValueError, ValidationError, json.JSONDecodeError):
            return NoteVerification(
                decision=OfflineDecision.REJECT_OFFLINE,
                reason_code="PAYLOAD_UNREADABLE",
                message="Rejected — unreadable Tulina Note",
                parse_check="FAIL",
                key_check=skipped,
                signature_check=skipped,
                recipient_check=skipped,
                expiry_check=skipped,
                nonce_check=skipped,
            )
        key = next((item for item in trust_bundle.keys if item.key_id == note.key_id), None)
        if key is None or _utc(scanned_at) > _utc(trust_bundle.expires_at):
            return NoteVerification(
                decision=OfflineDecision.REJECT_OFFLINE,
                reason_code="ISSUER_KEY_NOT_TRUSTED",
                message="Rejected — issuer not trusted",
                parse_check="PASS",
                key_check="FAIL",
                signature_check=skipped,
                recipient_check=skipped,
                expiry_check=skipped,
                nonce_check=skipped,
                payload=note.payload,
            )
        if not verify_raw_signature(key.public_jwk, note.canonical_payload, note.signature_base64url):
            return NoteVerification(
                decision=OfflineDecision.REJECT_OFFLINE,
                reason_code="SIGNATURE_INVALID",
                message="Rejected — signature invalid",
                parse_check="PASS",
                key_check="PASS",
                signature_check="FAIL",
                recipient_check=skipped,
                expiry_check=skipped,
                nonce_check=skipped,
                payload=note.payload,
            )
        recipient_ok = note.payload.recipient == device_facility_id
        expiry_ok = _utc(note.payload.iat) <= _utc(scanned_at) <= _utc(note.payload.exp)
        nonce_ok = note.payload.nonce not in (consumed_nonces or set())
        if not recipient_ok:
            reason, message = "RECIPIENT_MISMATCH", "Rejected — wrong receiving facility"
        elif not expiry_ok:
            reason, message = "NOTE_EXPIRED", "Rejected — authorization expired"
        elif not nonce_ok:
            reason, message = "NONCE_ALREADY_USED_LOCAL", "Rejected — Tulina Note already used"
        else:
            return NoteVerification(
                decision=OfflineDecision.ACCEPT_OFFLINE,
                reason_code="OK_QUEUED",
                message="Safe to receive",
                parse_check="PASS",
                key_check="PASS",
                signature_check="PASS",
                recipient_check="PASS",
                expiry_check="PASS",
                nonce_check="PASS",
                payload=note.payload,
            )
        return NoteVerification(
            decision=OfflineDecision.REJECT_OFFLINE,
            reason_code=reason,
            message=message,
            parse_check="PASS",
            key_check="PASS",
            signature_check="PASS",
            recipient_check="PASS" if recipient_ok else "FAIL",
            expiry_check="PASS" if expiry_ok else "FAIL",
            nonce_check="PASS" if nonce_ok else "FAIL",
            payload=note.payload,
        )

    def reconcile(self, receipt_token: str) -> ReconciliationResult:
        with self._lock:
            try:
                receipt = self.decode_receipt(receipt_token)
            except (ValueError, ValidationError, json.JSONDecodeError):
                return self._rejected(None, None, "RECEIPT_UNREADABLE", "Needs human review — unreadable receipt")
            payload = receipt.receipt_payload
            previous = self.store.result_for_receipt(payload.receipt_id)
            if previous:
                result = ReconciliationResult(
                    receipt_id=payload.receipt_id,
                    capsule_id=payload.capsule_id,
                    transfer_id=previous.transfer_id,
                    decision=ReconciliationDecision.IDEMPOTENT_ACK,
                    reason_code="DUPLICATE_RECEIPT",
                    message="Already synchronized — zero extra transfer writes",
                    transfer_mutations_applied=0,
                    pending_receipts=0,
                    inventory_before=previous.inventory_after,
                    inventory_after=previous.inventory_after,
                )
                self.store.save_result(result)
                self.repository.record_event(
                    trace_id=f"TRACE-{previous.transfer_id}",
                    actor_id="reconciliation_agent",
                    event_type="DUPLICATE_RECEIPT_RETRY",
                    summary=result.message,
                    details={"receipt_id": payload.receipt_id, "mutation_count": 0},
                )
                return result
            try:
                device = self.store.get_device(payload.device_id)
                note = self.store.get_note(payload.capsule_id)
            except ProtocolStoreError as exc:
                return self._rejected(payload.receipt_id, payload.capsule_id, "IDENTITY_UNKNOWN", str(exc))
            if receipt.device_key_id != device.key_id or not verify_raw_signature(
                device.public_jwk,
                receipt.canonical_receipt_payload,
                receipt.device_signature_base64url,
            ):
                return self._rejected(
                    payload.receipt_id,
                    payload.capsule_id,
                    "DEVICE_SIGNATURE_INVALID",
                    "Needs human review — recipient signature invalid",
                    transfer_id=note.payload.transfer_id,
                )
            verification = self.verify_note(
                note.qr_payload,
                trust_bundle=self.trust_bundle(),
                device_facility_id=device.facility_id,
                scanned_at=payload.received_at,
            )
            if verification.decision != OfflineDecision.ACCEPT_OFFLINE:
                return self._rejected(
                    payload.receipt_id,
                    payload.capsule_id,
                    verification.reason_code,
                    verification.message,
                    transfer_id=note.payload.transfer_id,
                )
            if device.facility_id != note.payload.recipient:
                return self._rejected(
                    payload.receipt_id,
                    payload.capsule_id,
                    "RECIPIENT_MISMATCH",
                    "Needs human review — recipient identity mismatch",
                    transfer_id=note.payload.transfer_id,
                )
            transfer = self.repository.get_transfer(note.payload.transfer_id)
            if transfer.status in {TransferStatus.CANCELLED, TransferStatus.NEEDS_REVIEW}:
                result = ReconciliationResult(
                    receipt_id=payload.receipt_id,
                    capsule_id=payload.capsule_id,
                    transfer_id=note.payload.transfer_id,
                    decision=ReconciliationDecision.QUARANTINE_CONFLICT,
                    reason_code="STATE_CONFLICT",
                    message="Needs human review — cloud state changed during the outage",
                    transfer_mutations_applied=0,
                    pending_receipts=0,
                )
                self.store.save_receipt(receipt, "QUARANTINED")
                self.store.save_result(result)
                self.repository.record_event(
                    trace_id=f"TRACE-{note.payload.transfer_id}",
                    actor_id="reconciliation_agent",
                    event_type="RECEIPT_QUARANTINED",
                    summary=result.message,
                    details={"receipt_id": payload.receipt_id, "mutation_count": 0},
                )
                return result
            key = f"{note.payload.transfer_id}|{note.payload.capsule_id}|{payload.device_id}"
            if self.repository.has_mutation(key):
                result = ReconciliationResult(
                    receipt_id=payload.receipt_id,
                    capsule_id=payload.capsule_id,
                    transfer_id=note.payload.transfer_id,
                    decision=ReconciliationDecision.IDEMPOTENT_ACK,
                    reason_code="DUPLICATE_RECEIPT",
                    message="Already synchronized — zero extra transfer writes",
                    transfer_mutations_applied=0,
                    pending_receipts=0,
                )
                self.store.save_receipt(receipt, "ACKNOWLEDGED")
                self.store.save_result(result)
                return result
            if transfer.status != TransferStatus.IN_TRANSIT or self.store.nonce_consumed(note.payload.nonce):
                return self._rejected(
                    payload.receipt_id,
                    payload.capsule_id,
                    "NONCE_ALREADY_CONSUMED_CLOUD",
                    "Rejected — Tulina Note already reconciled",
                    transfer_id=note.payload.transfer_id,
                )
            before = {
                "donor": self.repository.get_position(transfer.donor_facility_id, transfer.product_id).on_hand,
                "recipient": self.repository.get_position(transfer.recipient_facility_id, transfer.product_id).on_hand,
            }
            try:
                applied = self.repository.apply_transfer_once(
                    note.payload.transfer_id,
                    key,
                    TransitionContext(
                        actor_id="reconciliation_agent",
                        actor_role="reconciliation_agent",
                        reason="Verified recipient receipt applied exactly once",
                    ),
                )
            except RepositoryError as exc:
                return self._rejected(
                    payload.receipt_id,
                    payload.capsule_id,
                    "INVENTORY_CONFLICT",
                    f"Needs human review — {exc}",
                    transfer_id=note.payload.transfer_id,
                )
            after = {
                "donor": self.repository.get_position(transfer.donor_facility_id, transfer.product_id).on_hand,
                "recipient": self.repository.get_position(transfer.recipient_facility_id, transfer.product_id).on_hand,
            }
            if applied:
                self.store.consume_nonce(note.payload.nonce, payload.capsule_id, payload.receipt_id)
            result = ReconciliationResult(
                receipt_id=payload.receipt_id,
                capsule_id=payload.capsule_id,
                transfer_id=note.payload.transfer_id,
                decision=(
                    ReconciliationDecision.APPLIED_EXACTLY_ONCE
                    if applied
                    else ReconciliationDecision.IDEMPOTENT_ACK
                ),
                reason_code="RECEIPT_VERIFIED" if applied else "DUPLICATE_RECEIPT",
                message="Delivery confirmed" if applied else "Already synchronized — zero extra transfer writes",
                transfer_mutations_applied=1 if applied else 0,
                pending_receipts=0,
                inventory_before=before,
                inventory_after=after,
            )
            self.store.save_receipt(receipt, "ACKNOWLEDGED")
            self.store.save_result(result)
            return result

    def summary(self, transfer_id: str = "TR-027") -> ProtocolSummary:
        return ProtocolSummary(
            note=self.store.note_for_transfer(transfer_id),
            latest_reconciliation=self.store.latest_result(),
            mutation_count=self.repository.mutation_count(transfer_id),
            quarantined_count=self.store.quarantined_count(),
        )

    def _rejected(
        self,
        receipt_id: str | None,
        capsule_id: str | None,
        reason_code: str,
        message: str,
        *,
        transfer_id: str | None = None,
    ) -> ReconciliationResult:
        result = ReconciliationResult(
            receipt_id=receipt_id,
            capsule_id=capsule_id,
            transfer_id=transfer_id,
            decision=ReconciliationDecision.REJECTED,
            reason_code=reason_code,
            message=message,
            transfer_mutations_applied=0,
            pending_receipts=0,
        )
        self.store.save_result(result)
        self.repository.record_event(
            trace_id=f"TRACE-{transfer_id or 'PROTOCOL'}",
            actor_id="reconciliation_agent",
            event_type="RECEIPT_REJECTED",
            summary=message,
            details={"receipt_id": receipt_id, "reason_code": reason_code, "mutation_count": 0},
        )
        return result
