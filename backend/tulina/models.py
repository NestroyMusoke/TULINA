from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TransferStatus(StrEnum):
    FOUND = "FOUND"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    NOTE_ISSUED = "NOTE_ISSUED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CANCELLED = "CANCELLED"


class Facility(StrictModel):
    facility_id: str = Field(pattern=r"^F\d{2}$")
    official_name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)
    care_level: str
    care_rank: int = Field(ge=1)
    district: str = Field(min_length=1)
    latitude: float
    longitude: float


class Product(StrictModel):
    product_id: str = Field(pattern=r"^P\d{2}$")
    item: str
    strength: str
    transfer_unit: str
    units_per_transfer: int = Field(gt=0)
    minimum_care_rank: int = Field(ge=1)
    storage_mode: str
    storage_min_c: float | None = None
    storage_max_c: float | None = None
    unit_volume_l: float = Field(gt=0)

    @model_validator(mode="after")
    def cold_range_is_complete(self) -> Product:
        if self.storage_mode != "AMBIENT" and (
            self.storage_min_c is None or self.storage_max_c is None
        ):
            raise ValueError("Cold-chain products need minimum and maximum temperatures")
        return self


class InventoryBatch(StrictModel):
    batch_id: str = Field(pattern=r"^BAT-")
    facility_id: str = Field(pattern=r"^F\d{2}$")
    product_id: str = Field(pattern=r"^P\d{2}$")
    batch_number: str = Field(min_length=1)
    qty_on_hand: int = Field(ge=0)
    expiry_date: date
    quality_status: str
    projected_at_risk_qty: float = Field(default=0, ge=0)


class Consumption(StrictModel):
    facility_id: str
    product_id: str
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    qty_issued: int = Field(ge=0)


class Route(StrictModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    origin: str
    destination: str
    road_km: float = Field(alias="roadKm", gt=0)
    travel_min: float = Field(alias="travelMin", gt=0)


class Vehicle(StrictModel):
    vehicle_id: str
    cold_capable: bool
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    capacity_l: float = Field(gt=0)
    initial_status: str


class StockPosition(StrictModel):
    facility_id: str
    product_id: str
    on_hand: int = Field(ge=0)
    monthly_use: float = Field(ge=0)
    days_of_cover: int = Field(ge=0)
    target_quantity: int = Field(ge=0)
    safety_quantity: int = Field(ge=0)
    need_quantity: int = Field(ge=0)
    safe_release_quantity: int = Field(ge=0)


class WatchSignalType(StrEnum):
    NEED = "NEED"
    OFFER = "OFFER"


class WatchSignal(StrictModel):
    signal_type: WatchSignalType
    facility_id: str
    product_id: str
    quantity: int = Field(gt=0)
    earliest_expiry: date | None = None
    reason: str


class PolicyDecision(StrictModel):
    allowed: bool
    human_approval_required: bool
    checks: dict[str, bool]
    reasons: tuple[str, ...]

    @field_validator("checks")
    @classmethod
    def has_all_required_checks(cls, value: dict[str, bool]) -> dict[str, bool]:
        required = {"donor_cover", "recipient_level", "batch_quality", "route", "transport"}
        if set(value) != required:
            raise ValueError(f"Policy checks must be exactly {sorted(required)}")
        return value


class RecommendationEvidence(StrictModel):
    donor_on_hand: int
    donor_monthly_use: float
    donor_cover_before_days: int
    donor_cover_after_days: int
    recipient_on_hand: int
    recipient_monthly_use: float
    recipient_cover_before_days: int
    recipient_cover_after_days: int
    route_km: float
    route_minutes: int
    expiry_date: date
    projected_expiry_risk_avoided: float
    score_components: dict[str, float]


class TransferRecommendation(StrictModel):
    schema_version: str = "1.0"
    transfer_id: str = Field(pattern=r"^TR-\d{3}$")
    donor_facility_id: str
    recipient_facility_id: str
    product_id: str
    batch_id: str
    quantity: int = Field(gt=0)
    route_id: str
    vehicle_id: str
    approval_id: str
    score: float
    status: TransferStatus = TransferStatus.FOUND
    evidence: RecommendationEvidence
    policy: PolicyDecision
    source_label: str = "Synthetic demonstration data — not current facility stock"


class AuditEvent(StrictModel):
    event_id: str
    sequence: int = Field(ge=1)
    occurred_at: datetime
    trace_id: str
    actor_id: str
    event_type: str
    summary: str
    previous_hash: str
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    details: dict[str, object] = Field(default_factory=dict)
