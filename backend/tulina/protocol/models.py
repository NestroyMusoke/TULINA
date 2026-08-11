from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NotePayload(ProtocolModel):
    v: int = Field(ge=1, le=1)
    capsule_id: str = Field(pattern=r"^CAP-")
    transfer_id: str = Field(pattern=r"^TR-\d{3}$")
    issuer: str
    donor: str = Field(pattern=r"^F\d{2}$")
    recipient: str = Field(pattern=r"^F\d{2}$")
    product: str = Field(pattern=r"^P\d{2}$")
    batch: str = Field(pattern=r"^BAT-")
    qty: int = Field(gt=0)
    approval: str = Field(pattern=r"^APR-")
    iat: datetime
    exp: datetime
    nonce: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def expiry_follows_issue(self) -> NotePayload:
        if self.exp <= self.iat:
            raise ValueError("Tulina Note expiry must follow issuance")
        return self


class PublicKey(ProtocolModel):
    key_id: str
    algorithm: str = "ECDSA_P256_SHA256"
    public_jwk: dict[str, object]
    fingerprint: str

    @field_validator("public_jwk")
    @classmethod
    def valid_p256_jwk(cls, value: dict[str, object]) -> dict[str, object]:
        if value.get("kty") != "EC" or value.get("crv") != "P-256":
            raise ValueError("Only P-256 public keys are accepted")
        if not isinstance(value.get("x"), str) or not isinstance(value.get("y"), str):
            raise ValueError("P-256 public key coordinates are required")
        return value


class TrustBundle(ProtocolModel):
    schema_version: str = "1.0"
    bundle_id: str
    issued_at: datetime
    expires_at: datetime
    keys: tuple[PublicKey, ...]
    source_label: str = "Synthetic demonstration trust bundle"


class SignedTulinaNote(ProtocolModel):
    schema_version: str = "1.0"
    key_id: str
    canonical_payload: str
    signature_base64url: str
    qr_payload: str
    payload: NotePayload
    signature_format: str = "IEEE_P1363_64_BYTE"
    source_label: str = "Synthetic demonstration authorization — not a dispensing record"


class OfflineDecision(StrEnum):
    ACCEPT_OFFLINE = "ACCEPT_OFFLINE"
    REJECT_OFFLINE = "REJECT_OFFLINE"


class NoteVerification(ProtocolModel):
    decision: OfflineDecision
    reason_code: str
    message: str
    parse_check: str
    key_check: str
    signature_check: str
    recipient_check: str
    expiry_check: str
    nonce_check: str
    payload: NotePayload | None = None


class DeviceRegistration(ProtocolModel):
    schema_version: str = "1.0"
    device_id: str
    facility_id: str = Field(pattern=r"^F\d{2}$")
    key_id: str
    public_jwk: dict[str, object]

    @field_validator("public_jwk")
    @classmethod
    def valid_device_key(cls, value: dict[str, object]) -> dict[str, object]:
        if value.get("kty") != "EC" or value.get("crv") != "P-256":
            raise ValueError("Recipient devices must register a P-256 public key")
        if not isinstance(value.get("x"), str) or not isinstance(value.get("y"), str):
            raise ValueError("Device public key coordinates are required")
        return value


class ReceiptPayload(ProtocolModel):
    receipt_id: str = Field(pattern=r"^RCP-")
    capsule_id: str = Field(pattern=r"^CAP-")
    device_id: str = Field(pattern=r"^DEV-")
    decision: str = Field(pattern=r"^RECEIVED$")
    received_at: datetime
    local_sequence: int = Field(ge=1)


class SignedReceipt(ProtocolModel):
    schema_version: str = "1.0"
    device_key_id: str
    canonical_receipt_payload: str
    device_signature_base64url: str
    receipt_payload: ReceiptPayload
    receipt_token: str


class ReceiptSyncRequest(ProtocolModel):
    receipt_token: str = Field(min_length=20, max_length=16_384)


class ReconciliationDecision(StrEnum):
    APPLIED_EXACTLY_ONCE = "APPLIED_EXACTLY_ONCE"
    IDEMPOTENT_ACK = "IDEMPOTENT_ACK"
    QUARANTINE_CONFLICT = "QUARANTINE_CONFLICT"
    REJECTED = "REJECTED"


class ReconciliationResult(ProtocolModel):
    schema_version: str = "1.0"
    receipt_id: str | None
    capsule_id: str | None
    transfer_id: str | None
    decision: ReconciliationDecision
    reason_code: str
    message: str
    transfer_mutations_applied: int = Field(ge=0, le=1)
    pending_receipts: int = Field(ge=0)
    inventory_before: dict[str, int] | None = None
    inventory_after: dict[str, int] | None = None


class ProtocolSummary(ProtocolModel):
    note: SignedTulinaNote | None
    latest_reconciliation: ReconciliationResult | None
    mutation_count: int
    quarantined_count: int
