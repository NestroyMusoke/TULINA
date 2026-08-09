from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from statistics import mean

from .fixtures import FixtureData
from .models import (
    InventoryBatch,
    RecommendationEvidence,
    StockPosition,
    TransferRecommendation,
    WatchSignal,
    WatchSignalType,
)
from .policy import compatible_vehicle, evaluate_transfer


def days_of_cover(on_hand: int | float, monthly_use: float) -> int:
    return 999 if monthly_use <= 0 else round(float(on_hand) / monthly_use * 30)


def _stable_transfer_id(donor: str, recipient: str, product: str) -> str:
    digest = hashlib.sha256(f"{donor}|{recipient}|{product}".encode()).hexdigest()
    return f"TR-{100 + int(digest[:6], 16) % 900:03d}"


class DomainEngine:
    """Deterministic stock, watch, match, and policy calculations."""

    def __init__(self, data: FixtureData):
        self.data = data
        self.facilities = {row.facility_id: row for row in data.facilities}
        self.products = {row.product_id: row for row in data.products}
        self.routes = {(row.origin, row.destination): row for row in data.routes}
        consumption: dict[tuple[str, str], list[int]] = defaultdict(list)
        for row in data.consumption:
            consumption[(row.facility_id, row.product_id)].append(row.qty_issued)
        self.monthly_use = {key: mean(values) for key, values in consumption.items()}

    def stock_position(self, facility_id: str, product_id: str) -> StockPosition:
        available = [
            batch
            for batch in self.data.batches
            if batch.facility_id == facility_id
            and batch.product_id == product_id
            and batch.quality_status == "AVAILABLE"
        ]
        on_hand = sum(batch.qty_on_hand for batch in available)
        monthly_use = self.monthly_use.get((facility_id, product_id), 0.0)
        target = math.ceil(monthly_use * self.data.controls["Target_Months_Of_Stock"])
        safety = math.ceil(monthly_use * self.data.controls["Safety_Months_Of_Stock"])
        return StockPosition(
            facility_id=facility_id,
            product_id=product_id,
            on_hand=on_hand,
            monthly_use=monthly_use,
            days_of_cover=days_of_cover(on_hand, monthly_use),
            target_quantity=target,
            safety_quantity=safety,
            need_quantity=max(0, target - on_hand),
            safe_release_quantity=max(0, on_hand - safety),
        )

    def all_positions(self) -> tuple[StockPosition, ...]:
        keys = sorted({(row.facility_id, row.product_id) for row in self.data.consumption})
        return tuple(self.stock_position(*key) for key in keys)

    def watch(self) -> tuple[WatchSignal, ...]:
        signals: list[WatchSignal] = []
        excess_trigger = self.data.controls["Excess_Trigger_Months"]
        for position in self.all_positions():
            if position.need_quantity > 0:
                signals.append(
                    WatchSignal(
                        signal_type=WatchSignalType.NEED,
                        facility_id=position.facility_id,
                        product_id=position.product_id,
                        quantity=position.need_quantity,
                        reason=f"{position.days_of_cover} days of cover; target is {self.data.controls['Target_Months_Of_Stock']} months",
                    )
                )
            if (
                position.monthly_use > 0
                and position.on_hand / position.monthly_use > excess_trigger
                and position.safe_release_quantity > 0
            ):
                batches = self._available_batches(position.facility_id, position.product_id)
                signals.append(
                    WatchSignal(
                        signal_type=WatchSignalType.OFFER,
                        facility_id=position.facility_id,
                        product_id=position.product_id,
                        quantity=position.safe_release_quantity,
                        earliest_expiry=batches[0].expiry_date,
                        reason=f"Safe surplus after retaining {position.safety_quantity} packs",
                    )
                )
        return tuple(signals)

    def recommendations(self) -> tuple[TransferRecommendation, ...]:
        signals = self.watch()
        needs = [signal for signal in signals if signal.signal_type == WatchSignalType.NEED]
        offers = [signal for signal in signals if signal.signal_type == WatchSignalType.OFFER]
        canonical: dict[tuple[str, str, str], dict] = {}
        # Baseline plan identities win over disruption/replan records for the main demo.
        ordered_inputs = sorted(
            self.data.raw["expected_transfer_inputs"],
            key=lambda row: (row.get("plan_id") != "MOBIUS", row["transfer_id"]),
        )
        for row in ordered_inputs:
            key = (row["donor_facility_id"], row["recipient_facility_id"], row["product_id"])
            canonical.setdefault(key, row)
        results: list[TransferRecommendation] = []
        for need in needs:
            recipient = self.facilities[need.facility_id]
            recipient_position = self.stock_position(need.facility_id, need.product_id)
            for offer in offers:
                if offer.product_id != need.product_id or offer.facility_id == need.facility_id:
                    continue
                donor_position = self.stock_position(offer.facility_id, offer.product_id)
                product = self.products[need.product_id]
                batch = self._available_batches(offer.facility_id, offer.product_id)[0]
                quantity = min(need.quantity, offer.quantity, batch.qty_on_hand)
                route = self.routes.get((offer.facility_id, need.facility_id))
                vehicle = compatible_vehicle(product, self.data.vehicles, quantity)
                policy = evaluate_transfer(
                    donor=donor_position,
                    recipient=recipient,
                    product=product,
                    batch=batch,
                    quantity=quantity,
                    route=route,
                    vehicle=vehicle,
                    approval_threshold=self.data.controls["Approval_Threshold"],
                )
                if not policy.allowed or route is None or vehicle is None:
                    continue
                expiry_days = max(0, (batch.expiry_date - self.data.scenario_date).days)
                score_parts = {
                    "need": round(quantity * 4.0, 2),
                    "expiry": round(max(0, 180 - expiry_days) / 12, 2),
                    "distance": round(-route.road_km / 8, 2),
                }
                score = round(sum(score_parts.values()), 2)
                identity = canonical.get((offer.facility_id, need.facility_id, need.product_id), {})
                transfer_id = identity.get(
                    "transfer_id", _stable_transfer_id(offer.facility_id, need.facility_id, need.product_id)
                )
                results.append(
                    TransferRecommendation(
                        transfer_id=transfer_id,
                        donor_facility_id=offer.facility_id,
                        recipient_facility_id=need.facility_id,
                        product_id=need.product_id,
                        batch_id=batch.batch_id,
                        quantity=quantity,
                        route_id=identity.get("route_id", f"ROUTE-{offer.facility_id}-{need.facility_id}"),
                        vehicle_id=vehicle.vehicle_id,
                        approval_id=identity.get("approval_id", "PENDING-DHO"),
                        score=score,
                        evidence=RecommendationEvidence(
                            donor_on_hand=donor_position.on_hand,
                            donor_monthly_use=donor_position.monthly_use,
                            donor_cover_before_days=donor_position.days_of_cover,
                            donor_cover_after_days=days_of_cover(
                                donor_position.on_hand - quantity, donor_position.monthly_use
                            ),
                            recipient_on_hand=recipient_position.on_hand,
                            recipient_monthly_use=recipient_position.monthly_use,
                            recipient_cover_before_days=recipient_position.days_of_cover,
                            recipient_cover_after_days=days_of_cover(
                                recipient_position.on_hand + quantity,
                                recipient_position.monthly_use,
                            ),
                            route_km=round(route.road_km, 1),
                            route_minutes=round(route.travel_min),
                            expiry_date=batch.expiry_date,
                            projected_expiry_risk_avoided=min(
                                float(quantity), batch.projected_at_risk_qty
                            ),
                            score_components=score_parts,
                        ),
                        policy=policy,
                    )
                )
        return tuple(sorted(results, key=lambda item: (-item.score, item.transfer_id)))

    def _available_batches(self, facility_id: str, product_id: str) -> list[InventoryBatch]:
        return sorted(
            (
                batch
                for batch in self.data.batches
                if batch.facility_id == facility_id
                and batch.product_id == product_id
                and batch.quality_status == "AVAILABLE"
                and batch.qty_on_hand > 0
            ),
            key=lambda batch: (batch.expiry_date, batch.batch_id),
        )
