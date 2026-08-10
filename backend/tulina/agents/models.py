from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from ..models import PolicyDecision, StrictModel, TransferRecommendation, TransferStatus


class AgentRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentStepStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    FAILED = "FAILED"


class WatchCycleRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    recipient_facility_id: str = Field(default="F02", pattern=r"^F\d{2}$")
    product_id: str = Field(default="P05", pattern=r"^P\d{2}$")
    trigger: Literal["demo", "schedule", "inventory_event"] = "demo"


class AgentRun(StrictModel):
    run_id: str = Field(pattern=r"^RUN-[A-F0-9]{12}$")
    workflow: Literal["district_watch_cycle"] = "district_watch_cycle"
    status: AgentRunStatus
    trace_id: str
    requested_by: str
    provider: Literal["fixture", "gemini"]
    model_name: str | None = None
    queue_backend: Literal["local", "pubsub"]
    request: WatchCycleRequest
    result_transfer_id: str | None = None
    event_authors: tuple[str, ...] = ()
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentStep(StrictModel):
    step_id: str = Field(pattern=r"^STEP-[A-F0-9]{12}$")
    run_id: str
    sequence: int = Field(ge=1)
    agent_name: str
    tool_name: str
    status: AgentStepStatus
    summary: str
    evidence: dict[str, object] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime | None = None


class AgentRunDetail(StrictModel):
    run: AgentRun
    steps: tuple[AgentStep, ...] = ()


class InventorySnapshotResult(StrictModel):
    position_count: int = Field(gt=0)
    focus_on_hand: int = Field(ge=0)
    source_label: str


class WatchResult(StrictModel):
    need_count: int = Field(ge=0)
    offer_count: int = Field(ge=0)
    focus_need_quantity: int = Field(gt=0)
    focus_days_of_cover: int = Field(ge=0)


class MatchResult(StrictModel):
    candidate_count: int = Field(gt=0)
    recommendation: TransferRecommendation


class GovernanceResult(StrictModel):
    allowed: bool
    requires_human_approval: bool
    decision: PolicyDecision


class GateResult(StrictModel):
    ready: bool
    transfer_status: TransferStatus
    reason: str


class DecisionExplanation(StrictModel):
    headline: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=420)
    evidence_points: tuple[str, ...] = Field(min_length=2, max_length=5)
    human_action: str = Field(min_length=1, max_length=180)


class AgentStepOutcome(StrictModel):
    status: AgentStepStatus
    event_type: str
    summary: str = Field(min_length=1, max_length=300)
    state_key: str
    evidence: dict[str, object]
