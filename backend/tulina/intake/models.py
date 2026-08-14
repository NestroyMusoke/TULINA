from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from ..models import SecurityFinding, StrictModel


class StockCardIntakeStatus(StrEnum):
    AWAITING_REVIEW = "AWAITING_REVIEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EvidenceRegion(StrictModel):
    field: str = Field(min_length=1, max_length=60)
    quote: str = Field(min_length=1, max_length=180)
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]

    @model_validator(mode="after")
    def normalized_bbox(self) -> EvidenceRegion:
        if any(value < 0 or value > 1 for value in self.bbox):
            raise ValueError("Evidence coordinates must be normalized from 0 to 1")
        if self.bbox[2] <= self.bbox[0] or self.bbox[3] <= self.bbox[1]:
            raise ValueError("Evidence coordinates must describe a positive rectangle")
        return self


class StockMovement(StrictModel):
    movement_date: date
    reference: str = Field(min_length=1, max_length=80)
    batch_number: str = Field(min_length=1, max_length=80)
    expiry_date: date
    received_packs: int = Field(ge=0)
    issued_packs: int = Field(ge=0)
    balance_packs: int = Field(ge=0)
    temperature_c: float
    remarks: str = Field(max_length=220)


class RawStockCardExtraction(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    facility_name: str = Field(min_length=1, max_length=160)
    product_name: str = Field(min_length=1, max_length=160)
    stock_unit: str = Field(min_length=1, max_length=120)
    card_number: str = Field(min_length=1, max_length=80)
    scenario_date: date
    store_name: str = Field(min_length=1, max_length=120)
    storage_min_c: float
    storage_max_c: float
    on_hand_packs: int = Field(ge=0)
    batch_number: str = Field(min_length=1, max_length=80)
    expiry_date: date
    latest_temperature_c: float
    redistribution_review: bool
    movements: tuple[StockMovement, ...] = Field(min_length=1, max_length=80)
    evidence: tuple[EvidenceRegion, ...] = Field(min_length=5, max_length=30)
    overall_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def storage_range_is_valid(self) -> RawStockCardExtraction:
        if self.storage_max_c <= self.storage_min_c:
            raise ValueError("Storage maximum must be greater than minimum")
        return self


class ValidatedStockObservation(StrictModel):
    facility_id: str = Field(pattern=r"^F\d{2}$")
    product_id: str = Field(pattern=r"^P\d{2}$")
    batch_id: str = Field(pattern=r"^BAT-")
    extraction: RawStockCardExtraction


class CorrectionRecord(StrictModel):
    field: str
    previous_value: str
    corrected_value: str
    corrected_by: str
    corrected_at: datetime


class StockCardCorrectionRequest(StrictModel):
    facility_name: str | None = Field(default=None, min_length=1, max_length=160)
    product_name: str | None = Field(default=None, min_length=1, max_length=160)
    stock_unit: str | None = Field(default=None, min_length=1, max_length=120)
    card_number: str | None = Field(default=None, min_length=1, max_length=80)
    scenario_date: date | None = None
    store_name: str | None = Field(default=None, min_length=1, max_length=120)
    storage_min_c: float | None = None
    storage_max_c: float | None = None
    on_hand_packs: int | None = Field(default=None, ge=0)
    batch_number: str | None = Field(default=None, min_length=1, max_length=80)
    expiry_date: date | None = None
    latest_temperature_c: float | None = None
    redistribution_review: bool | None = None

    @model_validator(mode="after")
    def contains_a_change(self) -> StockCardCorrectionRequest:
        if not self.model_dump(exclude_none=True):
            raise ValueError("Provide at least one corrected field")
        return self


class StockCardIntake(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    intake_id: str = Field(pattern=r"^INT-[A-F0-9]{12}$")
    trace_id: str
    status: StockCardIntakeStatus
    provider: Literal["fixture", "gemini"]
    model_name: str | None = None
    gemini_called: bool
    source_filename: str = Field(min_length=1, max_length=180)
    mime_type: Literal["image/png", "image/jpeg"]
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_size_bytes: int = Field(gt=0)
    extraction: RawStockCardExtraction
    observation: ValidatedStockObservation | None = None
    required_corrections: tuple[str, ...] = ()
    security_findings: tuple[SecurityFinding, ...] = ()
    corrections: tuple[CorrectionRecord, ...] = ()
    source_label: str = "Synthetic demonstration stock card — not current facility data"
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    accepted_by: str | None = None
    accepted_at: datetime | None = None


class IntakeProviderResult(StrictModel):
    extraction: RawStockCardExtraction
    provider: Literal["fixture", "gemini"]
    model_name: str | None = None
    gemini_called: bool
