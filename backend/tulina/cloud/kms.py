from __future__ import annotations

import hashlib
import re
from functools import cached_property
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from google.protobuf import wrappers_pb2

from ..protocol.crypto import base64url_encode, public_jwk, raw_signature

_KEY_VERSION = re.compile(
    r"^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+/cryptoKeyVersions/[^/]+$"
)


def _crc32c(value: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in value:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return (~crc) & 0xFFFFFFFF


def _wrapped_int(value: Any) -> int:
    return int(value.value if hasattr(value, "value") else value)


class CloudKmsP256Signer:
    """P-256 signing port backed by a non-exportable Cloud KMS key version."""

    def __init__(self, key_version_name: str, *, client: Any = None):
        if not _KEY_VERSION.fullmatch(key_version_name):
            raise ValueError(
                "TULINA_KMS_KEY_VERSION must be a full Cloud KMS CryptoKeyVersion resource"
            )
        if client is None:
            from google.cloud import kms

            client = kms.KeyManagementServiceClient()
        self.key_version_name = key_version_name
        self.client = client
        key_name = key_version_name.split("/cryptoKeys/", 1)[1].replace(
            "/cryptoKeyVersions/", "-v"
        )
        self.key_id = f"KMS-{key_name}"

    @cached_property
    def jwk(self) -> dict[str, object]:
        response = self.client.get_public_key(
            request={"name": self.key_version_name}
        )
        if str(response.name) != self.key_version_name:
            raise RuntimeError("Cloud KMS public-key response failed name integrity check")
        pem = str(response.pem)
        if hasattr(response, "pem_crc32c") and _wrapped_int(response.pem_crc32c) != _crc32c(
            pem.encode("utf-8")
        ):
            raise RuntimeError("Cloud KMS public-key response failed CRC32C integrity check")
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
            key.curve, ec.SECP256R1
        ):
            raise ValueError("Tulina requires a Cloud KMS EC_SIGN_P256_SHA256 key")
        return public_jwk(key)

    def sign(self, canonical_payload: str) -> str:
        digest = hashlib.sha256(canonical_payload.encode("utf-8")).digest()
        digest_crc32c = _crc32c(digest)
        response = self.client.asymmetric_sign(
            request={
                "name": self.key_version_name,
                "digest": {"sha256": digest},
                "digest_crc32c": wrappers_pb2.Int64Value(value=digest_crc32c),
            }
        )
        if str(response.name) != self.key_version_name:
            raise RuntimeError("Cloud KMS signature response failed name integrity check")
        if hasattr(response, "verified_digest_crc32c") and not response.verified_digest_crc32c:
            raise RuntimeError("Cloud KMS rejected the request CRC32C integrity check")
        signature = bytes(response.signature)
        if hasattr(response, "signature_crc32c") and _wrapped_int(
            response.signature_crc32c
        ) != _crc32c(signature):
            raise RuntimeError("Cloud KMS signature response failed CRC32C integrity check")
        return base64url_encode(raw_signature(signature))
