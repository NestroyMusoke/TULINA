from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def public_jwk(public_key: ec.EllipticCurvePublicKey) -> dict[str, object]:
    numbers = public_key.public_numbers()
    size = (public_key.curve.key_size + 7) // 8
    return {
        "kty": "EC",
        "x": base64url_encode(numbers.x.to_bytes(size, "big")),
        "y": base64url_encode(numbers.y.to_bytes(size, "big")),
        "crv": "P-256",
    }


def load_public_jwk(jwk: dict[str, object]) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("Unsupported public key")
    x = int.from_bytes(base64url_decode(str(jwk["x"])), "big")
    y = int.from_bytes(base64url_decode(str(jwk["y"])), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def fingerprint(jwk: dict[str, object]) -> str:
    canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def raw_signature(der_signature: bytes) -> bytes:
    r, s = decode_dss_signature(der_signature)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify_raw_signature(
    public_key_jwk: dict[str, object], message: str, signature_base64url: str
) -> bool:
    try:
        raw = base64url_decode(signature_base64url)
        if len(raw) != 64:
            return False
        r = int.from_bytes(raw[:32], "big")
        s = int.from_bytes(raw[32:], "big")
        load_public_jwk(public_key_jwk).verify(
            encode_dss_signature(r, s), message.encode("utf-8"), ec.ECDSA(hashes.SHA256())
        )
    except (InvalidSignature, KeyError, TypeError, ValueError):
        return False
    return True


def encode_envelope(prefix: str, value: dict[str, object]) -> str:
    return f"{prefix}.{base64url_encode(canonical_json(value).encode('utf-8'))}"


def decode_envelope(prefix: str, token: str) -> dict[str, object]:
    expected = f"{prefix}."
    if not token.startswith(expected):
        raise ValueError("Unsupported Tulina protocol payload")
    raw = base64url_decode(token[len(expected) :]).decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Protocol envelope must be an object")
    return value


@dataclass(frozen=True)
class LocalP256Signer:
    """Development signer backed by a generated key persisted outside source control."""

    key_id: str
    private_key: ec.EllipticCurvePrivateKey

    @classmethod
    def generate(cls, key_id: str = "KEY-TULINA-LOCAL-v1") -> LocalP256Signer:
        return cls(key_id=key_id, private_key=ec.generate_private_key(ec.SECP256R1()))

    @classmethod
    def from_pem(cls, key_id: str, pem: bytes) -> LocalP256Signer:
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("Local Tulina signer must use P-256")
        return cls(key_id=key_id, private_key=key)

    def private_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @property
    def jwk(self) -> dict[str, object]:
        return public_jwk(self.private_key.public_key())

    def sign(self, canonical_payload: str) -> str:
        der = self.private_key.sign(canonical_payload.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return base64url_encode(raw_signature(der))
