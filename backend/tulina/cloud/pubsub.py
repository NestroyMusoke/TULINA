from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Callable
from typing import Any

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..agents.models import AgentRun


class PubSubMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: str = Field(min_length=4, max_length=100_000)
    message_id: str = Field(alias="messageId", min_length=1)
    attributes: dict[str, str] = Field(default_factory=dict)


class PubSubPushEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: PubSubMessage
    subscription: str = Field(min_length=1)


class PubSubAuthenticationError(PermissionError):
    pass


class PubSubPayloadError(ValueError):
    pass


TokenVerifier = Callable[[str, GoogleAuthRequest, str], dict[str, Any]]


def verify_pubsub_oidc(
    authorization: str | None,
    *,
    audience: str,
    service_account: str,
    verifier: TokenVerifier | None = None,
) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise PubSubAuthenticationError("Authenticated Pub/Sub bearer token is required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise PubSubAuthenticationError("Authenticated Pub/Sub bearer token is required")
    verify = verifier or id_token.verify_oauth2_token
    try:
        claims = verify(token, GoogleAuthRequest(), audience)
    except Exception as exc:
        raise PubSubAuthenticationError("Pub/Sub bearer token is invalid") from exc
    email = str(claims.get("email", ""))
    email_verified = claims.get("email_verified") in {True, "true", "True"}
    if not email_verified or not secrets.compare_digest(email, service_account):
        raise PubSubAuthenticationError("Pub/Sub service identity is not authorized")
    return claims


def decode_agent_run(envelope: PubSubPushEnvelope) -> AgentRun:
    if envelope.message.attributes.get("schema_version") != "1.0":
        raise PubSubPayloadError("Unsupported Pub/Sub workflow schema")
    if envelope.message.attributes.get("workflow") != "district_watch_cycle":
        raise PubSubPayloadError("Unsupported Pub/Sub workflow")
    try:
        payload = base64.b64decode(envelope.message.data, validate=True)
        run = AgentRun.model_validate_json(payload)
    except (binascii.Error, UnicodeDecodeError, ValidationError) as exc:
        raise PubSubPayloadError("Pub/Sub workflow payload is invalid") from exc
    if run.trace_id != envelope.message.attributes.get("trace_id"):
        raise PubSubPayloadError("Pub/Sub trace identity does not match the durable run")
    return run
