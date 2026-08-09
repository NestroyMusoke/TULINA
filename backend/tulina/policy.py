from __future__ import annotations

from .models import Facility, InventoryBatch, PolicyDecision, Product, Route, StockPosition, Vehicle


def compatible_vehicle(product: Product, vehicles: tuple[Vehicle, ...], quantity: int) -> Vehicle | None:
    required_volume = product.unit_volume_l * quantity
    for vehicle in vehicles:
        if vehicle.initial_status not in {"AVAILABLE", "AVAILABLE_AT_START"}:
            continue
        if vehicle.capacity_l < required_volume:
            continue
        if product.storage_mode == "AMBIENT":
            return vehicle
        if (
            vehicle.cold_capable
            and vehicle.temp_min_c is not None
            and vehicle.temp_max_c is not None
            and product.storage_min_c is not None
            and product.storage_max_c is not None
            and vehicle.temp_min_c <= product.storage_min_c
            and vehicle.temp_max_c >= product.storage_max_c
        ):
            return vehicle
    return None


def evaluate_transfer(
    *,
    donor: StockPosition,
    recipient: Facility,
    product: Product,
    batch: InventoryBatch,
    quantity: int,
    route: Route | None,
    vehicle: Vehicle | None,
    approval_threshold: int,
) -> PolicyDecision:
    checks = {
        "donor_cover": quantity > 0 and donor.on_hand - quantity >= donor.safety_quantity,
        "recipient_level": recipient.care_rank >= product.minimum_care_rank,
        "batch_quality": batch.quality_status == "AVAILABLE" and batch.qty_on_hand >= quantity,
        "route": route is not None and route.road_km > 0,
        "transport": vehicle is not None,
    }
    human_required = quantity >= approval_threshold
    reasons = (
        f"Donor retains {donor.safety_quantity} packs of protected safety stock",
        "Receiving facility is authorized for this medicine",
        f"Available batch {batch.batch_number} selected by earliest expiry",
        "A viable district route is available",
        "Temperature and carrying capacity are compatible",
        "Named DHO approval required" if human_required else "Facility-level approval permitted by threshold",
    )
    return PolicyDecision(
        allowed=all(checks.values()),
        human_approval_required=human_required,
        checks=checks,
        reasons=reasons,
    )

