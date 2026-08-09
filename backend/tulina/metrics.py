from __future__ import annotations

from pydantic import Field

from .models import StrictModel, TransferRecommendation


class TransferMetrics(StrictModel):
    transfer_id: str
    recipient_cover_restored_days: int = Field(ge=0)
    donor_cover_retained_days: int = Field(ge=0)
    projected_expiry_risk_avoided: float = Field(ge=0)
    distance_km: float = Field(gt=0)


def metrics_for(recommendation: TransferRecommendation) -> TransferMetrics:
    evidence = recommendation.evidence
    return TransferMetrics(
        transfer_id=recommendation.transfer_id,
        recipient_cover_restored_days=(
            evidence.recipient_cover_after_days - evidence.recipient_cover_before_days
        ),
        donor_cover_retained_days=evidence.donor_cover_after_days,
        projected_expiry_risk_avoided=evidence.projected_expiry_risk_avoided,
        distance_km=evidence.route_km,
    )

