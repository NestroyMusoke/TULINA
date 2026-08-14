from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from ..engine import DomainEngine
from ..models import SecurityFinding
from ..repository import Repository
from ..security import scan_untrusted_text
from .models import (
    CorrectionRecord,
    RawStockCardExtraction,
    StockCardCorrectionRequest,
    StockCardIntake,
    StockCardIntakeStatus,
    ValidatedStockObservation,
)
from .providers import StockCardProvider
from .store import IntakeStore

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
CONFIDENCE_THRESHOLD = 0.85
REQUIRED_EVIDENCE = {
    "facility_name",
    "product_name",
    "on_hand_packs",
    "batch_number",
    "expiry_date",
    "storage_range",
    "redistribution_review",
}


class IntakeValidationError(ValueError):
    pass


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _verified_mime(image_bytes: bytes, claimed_mime: str | None) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    else:
        raise IntakeValidationError("Upload a PNG or JPEG stock-card image")
    if claimed_mime and claimed_mime.lower() not in {detected, "image/jpg"}:
        raise IntakeValidationError("The file contents do not match the declared image type")
    return detected


class StockCardIntakeService:
    def __init__(
        self,
        *,
        engine: DomainEngine,
        repository: Repository,
        store: IntakeStore,
        provider: StockCardProvider,
    ):
        self.engine = engine
        self.repository = repository
        self.store = store
        self.provider = provider

    async def extract(
        self,
        *,
        image_bytes: bytes,
        filename: str,
        claimed_mime: str | None,
        actor_id: str,
    ) -> StockCardIntake:
        if not image_bytes:
            raise IntakeValidationError("The uploaded stock-card image is empty")
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise IntakeValidationError("Stock-card images must be 8 MB or smaller")
        mime_type = _verified_mime(image_bytes, claimed_mime)
        digest = hashlib.sha256(image_bytes).hexdigest()
        result = await self.provider.extract(image_bytes, mime_type)
        extraction, security_findings = self._quarantine_instructions(result.extraction)
        observation, issues = self._validate(extraction)
        now = datetime.now(UTC)
        intake = StockCardIntake(
            intake_id=f"INT-{uuid4().hex[:12].upper()}",
            trace_id=f"TRACE-INTAKE-{uuid4().hex[:10].upper()}",
            status=(
                StockCardIntakeStatus.NEEDS_REVIEW
                if issues
                else StockCardIntakeStatus.AWAITING_REVIEW
            ),
            provider=result.provider,
            model_name=result.model_name,
            gemini_called=result.gemini_called,
            source_filename=Path(filename).name or "stock-card",
            mime_type=mime_type,
            image_sha256=digest,
            image_size_bytes=len(image_bytes),
            extraction=extraction,
            observation=observation,
            required_corrections=tuple(sorted(issues)),
            security_findings=security_findings,
            created_at=now,
            updated_at=now,
        )
        self.store.save(intake)
        self.repository.record_event(
            trace_id=intake.trace_id,
            actor_id="stock_intake_agent",
            event_type="STOCK_CARD_EXTRACTED",
            summary=(
                "Stock card extracted and ready for human confirmation"
                if not issues
                else "Stock card extracted with fields needing human review"
            ),
            details={
                "intake_id": intake.intake_id,
                "provider": intake.provider,
                "gemini_called": intake.gemini_called,
                "required_corrections": list(intake.required_corrections),
                "uploaded_by": actor_id,
            },
        )
        if security_findings:
            self.repository.record_event(
                trace_id=intake.trace_id,
                actor_id="stock_intake_agent",
                event_type="UNTRUSTED_INSTRUCTION_QUARANTINED",
                summary="Instruction-like stock-card text was isolated; inventory facts were preserved",
                details={
                    "intake_id": intake.intake_id,
                    "finding_codes": [finding.code for finding in security_findings],
                    "source_fields": [finding.source_field for finding in security_findings],
                },
            )
        return intake

    @staticmethod
    def _quarantine_instructions(
        extraction: RawStockCardExtraction,
    ) -> tuple[RawStockCardExtraction, tuple[SecurityFinding, ...]]:
        findings: list[SecurityFinding] = []
        movements = []
        for index, movement in enumerate(extraction.movements):
            detected = scan_untrusted_text(
                movement.remarks, source_field=f"movements[{index}].remarks"
            )
            findings.extend(detected)
            movements.append(
                movement.model_copy(
                    update={
                        "remarks": (
                            "Instruction-like text quarantined; operational facts preserved"
                            if detected
                            else movement.remarks
                        )
                    }
                )
            )
        evidence = []
        for index, item in enumerate(extraction.evidence):
            detected = scan_untrusted_text(
                item.quote, source_field=f"evidence[{index}].quote"
            )
            findings.extend(detected)
            evidence.append(
                item.model_copy(
                    update={
                        "quote": "Instruction-like text quarantined" if detected else item.quote
                    }
                )
            )
        sanitized = extraction.model_copy(
            update={"movements": tuple(movements), "evidence": tuple(evidence)}
        )
        return sanitized, tuple(findings)

    def correct(
        self,
        intake_id: str,
        correction: StockCardCorrectionRequest,
        *,
        actor_id: str,
    ) -> StockCardIntake:
        intake = self.store.get(intake_id)
        if intake.status == StockCardIntakeStatus.ACCEPTED:
            raise IntakeValidationError("Accepted stock observations cannot be edited")
        extraction = intake.extraction
        updates = correction.model_dump(exclude_none=True)
        correction_events = list(intake.corrections)
        now = datetime.now(UTC)
        for field, value in updates.items():
            previous = getattr(extraction, field)
            correction_events.append(
                CorrectionRecord(
                    field=field,
                    previous_value=str(previous),
                    corrected_value=str(value),
                    corrected_by=actor_id,
                    corrected_at=now,
                )
            )
        try:
            corrected_extraction = RawStockCardExtraction.model_validate(
                {**extraction.model_dump(mode="python"), **updates}
            )
        except ValidationError as exc:
            raise IntakeValidationError("Corrected fields are not internally consistent") from exc
        observation, issues = self._validate(corrected_extraction, human_fields=set(updates))
        updated = intake.model_copy(
            update={
                "status": (
                    StockCardIntakeStatus.NEEDS_REVIEW
                    if issues
                    else StockCardIntakeStatus.AWAITING_REVIEW
                ),
                "extraction": corrected_extraction,
                "observation": observation,
                "required_corrections": tuple(sorted(issues)),
                "corrections": tuple(correction_events),
                "updated_at": now,
            }
        )
        self.store.save(updated)
        self.repository.record_event(
            trace_id=updated.trace_id,
            actor_id=actor_id,
            event_type="STOCK_CARD_CORRECTED",
            summary="Facility worker corrected extracted stock-card fields",
            details={"intake_id": intake_id, "fields": sorted(updates)},
        )
        return updated

    def accept(self, intake_id: str, *, actor_id: str) -> StockCardIntake:
        intake = self.store.get(intake_id)
        if intake.status == StockCardIntakeStatus.ACCEPTED:
            return intake
        if intake.required_corrections:
            raise IntakeValidationError(
                "Correct the highlighted fields before accepting this stock observation"
            )
        if intake.observation is None:
            raise IntakeValidationError("No validated stock observation is available")
        now = datetime.now(UTC)
        accepted = intake.model_copy(
            update={
                "status": StockCardIntakeStatus.ACCEPTED,
                "accepted_by": actor_id,
                "accepted_at": now,
                "updated_at": now,
            }
        )
        self.store.save(accepted)
        self.repository.record_event(
            trace_id=accepted.trace_id,
            actor_id=actor_id,
            event_type="STOCK_CARD_ACCEPTED",
            summary="Facility worker confirmed the structured stock observation",
            details={
                "intake_id": intake_id,
                "facility_id": accepted.observation.facility_id,
                "product_id": accepted.observation.product_id,
                "batch_id": accepted.observation.batch_id,
                "on_hand_packs": accepted.observation.extraction.on_hand_packs,
            },
        )
        return accepted

    def _validate(
        self,
        extraction: RawStockCardExtraction,
        *,
        human_fields: set[str] | None = None,
    ) -> tuple[ValidatedStockObservation | None, set[str]]:
        human_fields = human_fields or set()
        issues: set[str] = set()
        facility = next(
            (
                row
                for row in self.engine.data.facilities
                if _normalized(extraction.facility_name)
                in {_normalized(row.official_name), _normalized(row.short_name)}
            ),
            None,
        )
        if facility is None:
            issues.add("facility_name")
        product = next(
            (
                row
                for row in self.engine.data.products
                if _normalized(row.item) in _normalized(extraction.product_name)
                and _normalized(row.strength) in _normalized(extraction.product_name)
            ),
            None,
        )
        if product is None:
            issues.add("product_name")
        batch = next(
            (
                row
                for row in self.engine.data.batches
                if _normalized(row.batch_number) == _normalized(extraction.batch_number)
                and (facility is None or row.facility_id == facility.facility_id)
                and (product is None or row.product_id == product.product_id)
            ),
            None,
        )
        if batch is None:
            issues.add("batch_number")
        elif extraction.expiry_date != batch.expiry_date:
            issues.add("expiry_date")
        if extraction.movements[-1].balance_packs != extraction.on_hand_packs:
            issues.add("on_hand_packs")
        if product is not None and (
            extraction.storage_min_c != product.storage_min_c
            or extraction.storage_max_c != product.storage_max_c
        ):
            issues.add("storage_range")
        evidence_by_field = {row.field: row for row in extraction.evidence}
        issues.update(REQUIRED_EVIDENCE - evidence_by_field.keys())
        for field, evidence in evidence_by_field.items():
            human_confirmed = (
                bool({"storage_min_c", "storage_max_c"} & human_fields)
                if field == "storage_range"
                else field in human_fields
            )
            if evidence.confidence < CONFIDENCE_THRESHOLD and not human_confirmed:
                issues.add(field)
        if facility is None or product is None or batch is None:
            return None, issues
        return (
            ValidatedStockObservation(
                facility_id=facility.facility_id,
                product_id=product.product_id,
                batch_id=batch.batch_id,
                extraction=extraction,
            ),
            issues,
        )
