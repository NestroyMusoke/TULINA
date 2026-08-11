from __future__ import annotations

import json
from typing import Any

from .crypto import encode_envelope
from .models import (
    DeviceRegistration,
    NotePayload,
    PublicKey,
    ReceiptPayload,
    SignedReceipt,
    SignedTulinaNote,
)
from .service import NOTE_PREFIX, RECEIPT_PREFIX


def fixture_note(raw: dict[str, Any]) -> SignedTulinaNote:
    row = raw["relay_capsules"][0]
    canonical = row["canonical_payload"]
    signature = row["signature_base64url"]
    key_id = row["issuer_key_id"]
    token = encode_envelope(
        NOTE_PREFIX,
        {
            "key_id": key_id,
            "canonical_payload": canonical,
            "signature_base64url": signature,
        },
    )
    return SignedTulinaNote(
        key_id=key_id,
        canonical_payload=canonical,
        signature_base64url=signature,
        qr_payload=token,
        payload=NotePayload.model_validate_json(canonical),
        source_label="Preserved synthetic cryptographic fixture",
    )


def fixture_issuer_key(raw: dict[str, Any]) -> PublicKey:
    row = raw["relay_capsules"][0]
    return PublicKey(
        key_id=row["issuer_key_id"],
        public_jwk=json.loads(row["issuer_public_jwk"]),
        fingerprint=row["issuer_key_fingerprint"],
    )


def fixture_device(raw: dict[str, Any], device_id: str = "DEV-F02-01") -> DeviceRegistration:
    row = next(item for item in raw["device_registry"] if item["device_id"] == device_id)
    return DeviceRegistration(
        device_id=row["device_id"],
        facility_id=row["facility_id"],
        key_id=row["device_key_id"],
        public_jwk=json.loads(row["device_public_jwk"]),
    )


def fixture_receipt(raw: dict[str, Any], test_id: str) -> SignedReceipt:
    row = next(item for item in raw["offline_receipts"] if item["test_id"] == test_id)
    canonical = row["canonical_receipt_payload"]
    if not canonical or not row["device_signature_base64url"]:
        raise ValueError(f"{test_id} has no signed receipt fixture")
    device = next(
        item for item in raw["device_registry"] if item["device_id"] == row["device_id"]
    )
    token = encode_envelope(
        RECEIPT_PREFIX,
        {
            "device_key_id": device["device_key_id"],
            "canonical_receipt_payload": canonical,
            "device_signature_base64url": row["device_signature_base64url"],
        },
    )
    return SignedReceipt(
        device_key_id=device["device_key_id"],
        canonical_receipt_payload=canonical,
        device_signature_base64url=row["device_signature_base64url"],
        receipt_payload=ReceiptPayload.model_validate_json(canonical),
        receipt_token=token,
    )
