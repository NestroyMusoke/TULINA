from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mode: Literal["fixture", "gemini", "gcp"] = Field(
        default="fixture", validation_alias="TULINA_MODE"
    )
    queue_backend: Literal["local", "pubsub"] = Field(
        default="local", validation_alias="TULINA_QUEUE"
    )
    repository_backend: Literal["local", "firestore"] = Field(
        default="local", validation_alias="TULINA_REPOSITORY"
    )
    gemini_model: str = Field(
        default="gemini-3.5-flash", validation_alias="GEMINI_MODEL"
    )
    google_api_key: SecretStr | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    use_vertex_ai: bool = Field(
        default=False, validation_alias="GOOGLE_GENAI_USE_VERTEXAI"
    )
    google_cloud_project: str | None = Field(
        default=None, validation_alias="GOOGLE_CLOUD_PROJECT"
    )
    google_cloud_location: str = Field(
        default="us-central1", validation_alias="GOOGLE_CLOUD_LOCATION"
    )
    pubsub_project: str | None = Field(
        default=None, validation_alias="TULINA_GCP_PROJECT"
    )
    pubsub_topic: str = Field(
        default="tulina-workflows", validation_alias="TULINA_PUBSUB_TOPIC"
    )
    pubsub_audience: str | None = Field(
        default=None, validation_alias="TULINA_PUBSUB_AUDIENCE"
    )
    pubsub_service_account: str | None = Field(
        default=None, validation_alias="TULINA_PUBSUB_SERVICE_ACCOUNT"
    )
    firestore_database: str = Field(
        default="(default)", validation_alias="TULINA_FIRESTORE_DATABASE"
    )
    firestore_namespace: str = Field(
        default="tulina-demo", validation_alias="TULINA_FIRESTORE_NAMESPACE"
    )
    kms_key_version: str | None = Field(
        default=None, validation_alias="TULINA_KMS_KEY_VERSION"
    )
    demo_step_delay_ms: int = Field(
        default=80, ge=0, le=2000, validation_alias="TULINA_AGENT_STEP_DELAY_MS"
    )

    @model_validator(mode="after")
    def validate_live_configuration(self) -> AgentSettings:
        version = re.match(r"^gemini-(\d+)(?:\.(\d+))?-", self.gemini_model)
        if version is None:
            raise ValueError("GEMINI_MODEL must be a versioned Gemini model name")
        major, minor = int(version.group(1)), int(version.group(2) or 0)
        if (major, minor) < (3, 5):
            raise ValueError("Tulina requires Gemini 3.5 or newer")
        if self.mode != "fixture":
            vertex = self.use_vertex_ai or self.mode == "gcp"
            if vertex and not (self.google_cloud_project or "").strip():
                raise ValueError(
                    "Set GOOGLE_CLOUD_PROJECT when Vertex AI/GCP mode is enabled"
                )
            if not vertex and (
                self.google_api_key is None
                or not self.google_api_key.get_secret_value().strip()
            ):
                raise ValueError("Set GOOGLE_API_KEY when Gemini API mode is enabled")
        if self.queue_backend == "pubsub" and not (
            self.pubsub_project or self.google_cloud_project
        ):
            raise ValueError(
                "Set TULINA_GCP_PROJECT or GOOGLE_CLOUD_PROJECT for Pub/Sub mode"
            )
        if self.queue_backend == "pubsub" and not (self.pubsub_audience or "").strip():
            raise ValueError("Set TULINA_PUBSUB_AUDIENCE for authenticated push")
        if self.queue_backend == "pubsub" and not (
            self.pubsub_service_account or ""
        ).strip():
            raise ValueError("Set TULINA_PUBSUB_SERVICE_ACCOUNT for authenticated push")
        if self.repository_backend == "firestore" and not self.google_cloud_project:
            raise ValueError("Set GOOGLE_CLOUD_PROJECT for Firestore mode")
        if self.mode == "gcp":
            if self.repository_backend != "firestore":
                raise ValueError("Set TULINA_REPOSITORY=firestore for GCP mode")
            if self.queue_backend != "pubsub":
                raise ValueError("Set TULINA_QUEUE=pubsub for GCP mode")
            if not (self.kms_key_version or "").strip():
                raise ValueError("Set TULINA_KMS_KEY_VERSION for GCP mode")
            if not (self.pubsub_audience or "").strip():
                raise ValueError("Set TULINA_PUBSUB_AUDIENCE to the backend Cloud Run URL")
            if not (self.pubsub_service_account or "").strip():
                raise ValueError("Set TULINA_PUBSUB_SERVICE_ACCOUNT for authenticated push")
        return self

    @property
    def provider_name(self) -> Literal["fixture", "gemini"]:
        return "fixture" if self.mode == "fixture" else "gemini"

    @property
    def model_name(self) -> str | None:
        return None if self.mode == "fixture" else self.gemini_model
