from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .engine import DomainEngine
from .fixtures import load_fixture
from .metrics import metrics_for
from .models import TransferRecommendation, TransferStatus
from .repository import SQLiteRepository
from .state_machine import InvalidTransition, TransitionContext


class Role(StrEnum):
    FACILITY_WORKER = "facility_worker"
    DHO_APPROVER = "dho_approver"
    AUDITOR = "auditor"


def require_role(*allowed: Role):
    def dependency(x_tulina_role: str | None = Header(default=None)) -> Role:
        try:
            role = Role(x_tulina_role or "")
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Choose a valid Tulina demo role") from exc
        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"The {role.value} role cannot perform this action",
            )
        return role

    return dependency


def _recommendation_payload(
    recommendation: TransferRecommendation, engine: DomainEngine
) -> dict[str, object]:
    donor = engine.facilities[recommendation.donor_facility_id]
    recipient = engine.facilities[recommendation.recipient_facility_id]
    product = engine.products[recommendation.product_id]
    batch = next(
        row for row in engine.data.batches if row.batch_id == recommendation.batch_id
    )
    return {
        **recommendation.model_dump(mode="json"),
        "donor_name": donor.official_name,
        "donor_short_name": donor.short_name,
        "recipient_name": recipient.official_name,
        "recipient_short_name": recipient.short_name,
        "product_name": f"{product.item} {product.strength}",
        "transfer_unit": product.transfer_unit.lower(),
        "batch_number": batch.batch_number,
        "metrics": metrics_for(recommendation).model_dump(mode="json"),
    }


def create_app(
    *,
    database: str | Path | None = None,
    fixture: str | Path = "data/fixtures/tulina_source_pack_v2.json",
) -> FastAPI:
    data = load_fixture(fixture)
    engine = DomainEngine(data)
    repository = SQLiteRepository(
        database or os.getenv("TULINA_DATABASE_PATH", "data/runtime/tulina.sqlite3")
    )
    repository.seed(engine.all_positions(), engine.recommendations())

    app = FastAPI(
        title="Tulina API",
        version="1.0.0",
        description="Deterministic district medicine redistribution service",
    )
    app.state.engine = engine
    app.state.repository = repository
    allowed_origins = os.getenv("TULINA_ALLOWED_ORIGINS", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[value.strip() for value in allowed_origins.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Tulina-Role", "X-Request-ID"],
    )

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "tulina-api", "mode": "fixture"}

    @app.get("/readyz")
    def ready() -> dict[str, object]:
        return {
            "ready": repository.verify_audit_chain(),
            "database": "sqlite",
            "fixture_records": len(engine.all_positions()),
        }

    @app.get("/api/v1/overview")
    def overview() -> dict[str, object]:
        recommendation = repository.get_transfer("TR-027")
        return {
            "recommendation": _recommendation_payload(recommendation, engine),
            "activity": [row.model_dump(mode="json") for row in repository.events()][-12:],
            "network": _network_payload(engine, repository),
            "synthetic_data": True,
            "scenario_date": data.raw["metadata"]["scenario_date"],
        }

    @app.get("/api/v1/recommendations/{transfer_id}")
    def recommendation(transfer_id: str) -> dict[str, object]:
        try:
            item = repository.get_transfer(transfer_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Recommendation not found") from exc
        return _recommendation_payload(item, engine)

    @app.get("/api/v1/network")
    def network() -> dict[str, object]:
        return {"positions": _network_payload(engine, repository), "synthetic_data": True}

    @app.get("/api/v1/activity")
    def activity(_: Role = Depends(require_role(Role.DHO_APPROVER, Role.AUDITOR))):
        return {"events": [row.model_dump(mode="json") for row in repository.events()]}

    @app.post("/api/v1/demo/reset")
    def reset(_: Role = Depends(require_role(Role.DHO_APPROVER))) -> dict[str, object]:
        repository.seed(engine.all_positions(), engine.recommendations(), reset=True)
        repository.record_event(
            trace_id="TRACE-TR-027",
            actor_id="demo-controller",
            event_type="DEMO_RESET",
            summary="Judge demo returned to its verified starting state",
            details={"transfer_id": "TR-027"},
        )
        return overview()

    @app.post("/api/v1/demo/discover")
    def discover(
        _: Role = Depends(require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER)),
    ) -> dict[str, object]:
        current = repository.get_transfer("TR-027")
        if current.status != TransferStatus.FOUND:
            raise HTTPException(status_code=409, detail="Reset the demo before discovery")
        offer = engine.stock_position("F01", "P05")
        need = engine.stock_position("F02", "P05")
        repository.record_event(
            trace_id="TRACE-TR-027",
            actor_id="watch-and-match",
            event_type="FOUND_NEARBY",
            summary="Found safe oxytocin stock nearby for Busiu",
            details={
                "donor_safe_release": offer.safe_release_quantity,
                "recipient_need": need.need_quantity,
                "proposed_quantity": current.quantity,
            },
        )
        return overview()

    @app.post("/api/v1/transfers/TR-027/request-approval")
    def request_approval(
        _: Role = Depends(require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER)),
    ) -> dict[str, object]:
        try:
            repository.change_status(
                "TR-027",
                TransferStatus.AWAITING_APPROVAL,
                TransitionContext(
                    actor_id="steward-agent",
                    actor_role="steward_agent",
                    reason="All safety gates passed; DHO decision requested",
                ),
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return overview()

    @app.post("/api/v1/transfers/TR-027/approve")
    def approve(_: Role = Depends(require_role(Role.DHO_APPROVER))) -> dict[str, object]:
        try:
            repository.change_status(
                "TR-027",
                TransferStatus.APPROVED,
                TransitionContext(
                    actor_id="APR-DHO-001",
                    actor_role=Role.DHO_APPROVER.value,
                    reason="District Health Officer approved 11 transfer packs",
                ),
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return overview()

    return app


def _network_payload(engine: DomainEngine, repository: SQLiteRepository) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for calculated in engine.all_positions():
        position = repository.get_position(calculated.facility_id, calculated.product_id)
        facility = engine.facilities[position.facility_id]
        product = engine.products[position.product_id]
        if position.need_quantity > 0:
            state = "needs_stock"
        elif position.monthly_use > 0 and position.on_hand / position.monthly_use > 4:
            state = "safe_surplus"
        else:
            state = "covered"
        rows.append(
            {
                **position.model_dump(mode="json"),
                "facility_name": facility.official_name,
                "facility_short_name": facility.short_name,
                "product_name": f"{product.item} {product.strength}",
                "state": state,
            }
        )
    return rows


app = create_app()
