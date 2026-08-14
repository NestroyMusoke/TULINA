from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import Header, HTTPException

from .models import SecurityFinding


class Role(StrEnum):
    FACILITY_WORKER = "facility_worker"
    DHO_APPROVER = "dho_approver"
    AUDITOR = "auditor"


class Action(StrEnum):
    START_WATCH = "start_watch"
    READ_TECHNICAL = "read_technical"
    PROCESS_QUEUE = "process_queue"
    RECORD_STOCK = "record_stock"
    RESET_DEMO = "reset_demo"
    REQUEST_APPROVAL = "request_approval"
    APPROVE_TRANSFER = "approve_transfer"
    REGISTER_DEVICE = "register_device"
    ISSUE_NOTE = "issue_note"
    RECONCILE_RECEIPT = "reconcile_receipt"
    READ_AUDIT = "read_audit"
    RESOLVE_EXCEPTION = "resolve_exception"


ROLE_PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.FACILITY_WORKER: frozenset(
        {
            Action.START_WATCH,
            Action.READ_TECHNICAL,
            Action.RECORD_STOCK,
            Action.REQUEST_APPROVAL,
            Action.REGISTER_DEVICE,
            Action.RECONCILE_RECEIPT,
        }
    ),
    Role.DHO_APPROVER: frozenset(
        {
            Action.START_WATCH,
            Action.READ_TECHNICAL,
            Action.PROCESS_QUEUE,
            Action.RESET_DEMO,
            Action.REQUEST_APPROVAL,
            Action.APPROVE_TRANSFER,
            Action.ISSUE_NOTE,
            Action.READ_AUDIT,
            Action.RESOLVE_EXCEPTION,
        }
    ),
    Role.AUDITOR: frozenset({Action.READ_TECHNICAL, Action.READ_AUDIT}),
}

DEFAULT_ACTORS = {
    Role.FACILITY_WORKER: Role.FACILITY_WORKER.value,
    Role.DHO_APPROVER: "APR-DHO-001",
    Role.AUDITOR: Role.AUDITOR.value,
}

ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,79}$")


@dataclass(frozen=True)
class Principal:
    role: Role
    actor_id: str


def require_action(action: Action):
    """Enforce the fixture-mode authorization matrix at the server boundary."""

    def dependency(
        x_tulina_role: str | None = Header(default=None),
        x_tulina_actor: str | None = Header(default=None),
    ) -> Principal:
        try:
            role = Role(x_tulina_role or "")
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Choose a valid Tulina demo role") from exc
        if action not in ROLE_PERMISSIONS[role]:
            raise HTTPException(
                status_code=403,
                detail=f"The {role.value} role cannot perform this action",
            )
        actor_id = x_tulina_actor or DEFAULT_ACTORS[role]
        if not ACTOR_PATTERN.fullmatch(actor_id):
            raise HTTPException(status_code=400, detail="The Tulina actor identifier is invalid")
        return Principal(role=role, actor_id=actor_id)

    return dependency


_INSTRUCTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("IGNORE_POLICY", re.compile(r"\bignore\b.{0,50}\b(policy|rules?|instructions?)\b", re.I)),
    ("ROLE_OVERRIDE", re.compile(r"\b(system|assistant|developer)\s*(prompt|message|role)\b", re.I)),
    ("TOOL_COMMAND", re.compile(r"\b(call|invoke|run|execute)\b.{0,35}\b(tool|function|command)\b", re.I)),
    ("SECRET_REQUEST", re.compile(r"\b(reveal|print|return|send)\b.{0,35}\b(secret|api key|token|password)\b", re.I)),
    (
        "AUTHORITY_OVERRIDE",
        re.compile(
            r"\b(approve|dispatch|transfer|send)\b.{0,50}\b(all|everything|without approval)\b",
            re.I,
        ),
    ),
)


def scan_untrusted_text(text: str, *, source_field: str) -> tuple[SecurityFinding, ...]:
    findings: list[SecurityFinding] = []
    for code, pattern in _INSTRUCTION_PATTERNS:
        if pattern.search(text):
            findings.append(
                SecurityFinding(
                    code=code,
                    source_field=source_field,
                    message="Instruction-like text was isolated from operational facts",
                    action="QUARANTINED_INSTRUCTION_PRESERVED_FACTS",
                )
            )
    return tuple(findings)


class SecurityBoundaryError(ValueError):
    pass


_DENIED_OUTPUT_KEYS = {
    "api_key",
    "authorization",
    "chain_of_thought",
    "hidden_reasoning",
    "private_key",
    "private_pem",
    "prompt",
    "raw_model_response",
    "system_prompt",
}
MAX_TOOL_OUTPUT_BYTES = 128 * 1024
MAX_GENERATED_OUTPUT_BYTES = 32 * 1024


def guard_tool_output(tool_name: str, result: object) -> dict[str, object]:
    """Reject malformed, oversized, or authority-smuggling tool output before validation."""
    if not isinstance(result, dict):
        raise SecurityBoundaryError(f"{tool_name} returned a non-object result")
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode()
    if len(encoded) > MAX_TOOL_OUTPUT_BYTES:
        raise SecurityBoundaryError(f"{tool_name} output exceeded the validated boundary")
    denied = _find_denied_keys(result)
    if denied:
        raise SecurityBoundaryError(f"{tool_name} returned forbidden fields")
    if "error" in result:
        raise SecurityBoundaryError(f"{tool_name} reported a guarded failure")
    return result


_AUTHORITY_CLAIM = re.compile(
    r"\b(i|we|tulina|agent|model)\s+(have\s+)?(approve[ds]?|authori[sz]ed|dispatch(?:ed)?|executed)\b",
    re.I,
)
_HIDDEN_REASONING_MARKER = re.compile(
    r"\b(chain[- ]of[- ]thought|hidden reasoning|system prompt|developer message)\b",
    re.I,
)


def guard_generated_output(provider_name: str, result: object) -> None:
    """Prevent generated explanations from claiming authority or exposing prompt internals."""
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    if len(encoded) > MAX_GENERATED_OUTPUT_BYTES:
        raise SecurityBoundaryError(f"{provider_name} explanation exceeded the validated boundary")
    if _find_denied_keys(payload):
        raise SecurityBoundaryError(f"{provider_name} explanation returned forbidden fields")
    text = " ".join(_string_values(payload))
    if _AUTHORITY_CLAIM.search(text) or _HIDDEN_REASONING_MARKER.search(text):
        raise SecurityBoundaryError(f"{provider_name} explanation crossed the authority boundary")


def _find_denied_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in _DENIED_OUTPUT_KEYS:
                found.add(normalized)
            found.update(_find_denied_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            found.update(_find_denied_keys(child))
    return found


def _string_values(value: object) -> list[str]:
    if isinstance(value, Mapping):
        return [text for child in value.values() for text in _string_values(child)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [text for child in value for text in _string_values(child)]
    return [value] if isinstance(value, str) else []


_AUDIT_REDACT_KEYS = {
    "api_key",
    "authorization",
    "canonical_payload",
    "device_signature_base64url",
    "image_base64",
    "private_key",
    "private_pem",
    "prompt",
    "qr_payload",
    "raw_model_response",
    "receipt_token",
    "secret",
    "signature_base64url",
}


def sanitize_audit_details(details: Mapping[str, object]) -> dict[str, object]:
    """Retain decision evidence while preventing secrets or large raw inputs in audit state."""
    return {str(key): _sanitize_audit_value(str(key), value, depth=0) for key, value in details.items()}


def _sanitize_audit_value(key: str, value: Any, *, depth: int) -> object:
    if key.casefold() in _AUDIT_REDACT_KEYS:
        return "[REDACTED]"
    if depth >= 6:
        return "[MAX_DEPTH]"
    if isinstance(value, Mapping):
        return {
            str(child_key): _sanitize_audit_value(str(child_key), child, depth=depth + 1)
            for child_key, child in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_audit_value(key, child, depth=depth + 1) for child in value[:100]]
    if isinstance(value, str):
        return value if len(value) <= 500 else f"{value[:497]}..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)
