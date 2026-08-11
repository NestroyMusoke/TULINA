from __future__ import annotations

import os
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .agents.fleet import FLEET_REGISTRY
from .agents.models import WatchCycleRequest
from .agents.runtime import build_agent_runtime
from .agents.settings import AgentSettings
from .agents.store import AgentStoreError
from .engine import DomainEngine
from .fixtures import load_fixture
from .intake.agent import StockIntakeAgentRuntime
from .intake.models import StockCardCorrectionRequest
from .intake.providers import build_stock_card_provider
from .intake.service import MAX_UPLOAD_BYTES, IntakeValidationError, StockCardIntakeService
from .intake.store import IntakeStoreError, SQLiteIntakeStore
from .metrics import metrics_for
from .models import TransferRecommendation, TransferStatus
from .protocol.agent import ProtocolAgentRuntime
from .protocol.models import DeviceRegistration, ReceiptSyncRequest
from .protocol.service import ProtocolError, ProtocolService
from .protocol.store import ProtocolStoreError, SQLiteProtocolStore
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
    agent_settings: AgentSettings | None = None,
    publisher=None,
    intake_provider=None,
) -> FastAPI:
    data = load_fixture(fixture)
    engine = DomainEngine(data)
    database_path = database or os.getenv(
        "TULINA_DATABASE_PATH", "data/runtime/tulina.sqlite3"
    )
    repository = SQLiteRepository(database_path)
    repository.seed(engine.all_positions(), engine.recommendations())
    agent_settings = agent_settings or AgentSettings()
    agent_service = build_agent_runtime(
        engine=engine,
        repository=repository,
        database=database_path,
        settings=agent_settings,
        publisher=publisher,
    )
    intake_store = SQLiteIntakeStore(database_path)
    intake_service = StockCardIntakeService(
        engine=engine,
        repository=repository,
        store=intake_store,
        provider=intake_provider or build_stock_card_provider(agent_settings),
    )
    intake_agent_runtime = StockIntakeAgentRuntime(intake_service)
    protocol_store = SQLiteProtocolStore(database_path)
    protocol_service = ProtocolService(repository=repository, store=protocol_store)
    protocol_agent_runtime = ProtocolAgentRuntime(protocol_service)

    app = FastAPI(
        title="Tulina API",
        version="1.0.0",
        description="Deterministic district medicine redistribution service",
    )
    app.state.engine = engine
    app.state.repository = repository
    app.state.agent_service = agent_service
    app.state.agent_store = agent_service.store
    app.state.agent_settings = agent_settings
    app.state.intake_store = intake_store
    app.state.intake_service = intake_service
    app.state.intake_agent_runtime = intake_agent_runtime
    app.state.protocol_store = protocol_store
    app.state.protocol_service = protocol_service
    app.state.protocol_agent_runtime = protocol_agent_runtime
    allowed_origins = os.getenv("TULINA_ALLOWED_ORIGINS", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[value.strip() for value in allowed_origins.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Tulina-Role", "X-Request-ID"],
    )

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "tulina-api", "mode": agent_settings.mode}

    @app.get("/readyz")
    def ready() -> dict[str, object]:
        return {
            "ready": repository.verify_audit_chain(),
            "database": "sqlite",
            "fixture_records": len(engine.all_positions()),
            "agent_runtime": "google-adk",
            "queue_backend": agent_service.queue.backend_name,
            "stock_card_provider": intake_service.provider.name,
            "offline_note_signer": "local-p256",
        }

    @app.get("/api/v1/overview")
    def overview() -> dict[str, object]:
        recommendation = repository.get_transfer("TR-027")
        latest_agent_run = agent_service.latest_detail()
        latest_intake = intake_store.latest()
        return {
            "recommendation": _recommendation_payload(recommendation, engine),
            "activity": [row.model_dump(mode="json") for row in repository.events()][-12:],
            "network": _network_payload(engine, repository),
            "agent_run": latest_agent_run.model_dump(mode="json") if latest_agent_run else None,
            "stock_card_intake": latest_intake.model_dump(mode="json") if latest_intake else None,
            "protocol": protocol_service.summary().model_dump(mode="json"),
            "synthetic_data": True,
            "scenario_date": data.raw["metadata"]["scenario_date"],
        }

    @app.get("/api/v1/agent-registry")
    def agent_registry() -> dict[str, object]:
        latest = agent_service.latest_detail()
        return {
            "framework": "Google ADK",
            "framework_version": version("google-adk"),
            "root_agent": agent_service.fleet.name,
            "agents": FLEET_REGISTRY,
            "active_provider": agent_settings.provider_name,
            "configured_model": agent_settings.gemini_model,
            "gemini_called": bool(latest and latest.run.provider == "gemini"),
            "queue_backend": agent_service.queue.backend_name,
        }

    @app.post("/api/v1/agent-runs/watch", status_code=202)
    def start_watch_cycle(
        request: WatchCycleRequest,
        background_tasks: BackgroundTasks,
        role: Role = Depends(require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER)),
    ) -> dict[str, object]:
        if request.trigger == "inventory_event" and intake_store.latest_accepted() is None:
            raise HTTPException(
                status_code=409,
                detail="Confirm the stock-card observation before starting inventory checks",
            )
        run = agent_service.start_watch_cycle(
            request=request, requested_by=role.value
        )
        if agent_service.queue.backend_name == "local":
            background_tasks.add_task(agent_service.process_next)
        return agent_service.detail(run.run_id).model_dump(mode="json")

    @app.get("/api/v1/agent-runs/latest")
    def latest_agent_run(
        _: Role = Depends(
            require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER, Role.AUDITOR)
        ),
    ) -> dict[str, object]:
        latest = agent_service.latest_detail()
        if latest is None:
            raise HTTPException(status_code=404, detail="No background run exists")
        return latest.model_dump(mode="json")

    @app.get("/api/v1/agent-runs/{run_id}")
    def agent_run(
        run_id: str,
        _: Role = Depends(
            require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER, Role.AUDITOR)
        ),
    ) -> dict[str, object]:
        try:
            return agent_service.detail(run_id).model_dump(mode="json")
        except AgentStoreError as exc:
            raise HTTPException(status_code=404, detail="Agent run not found") from exc

    @app.post("/api/v1/agent-worker/process-next")
    async def process_next_agent_run(
        _: Role = Depends(require_role(Role.DHO_APPROVER, Role.AUDITOR)),
    ) -> dict[str, object]:
        processed = await agent_service.process_next()
        if processed is None:
            return {"processed": False, "run": None}
        return {
            "processed": True,
            "run": agent_service.detail(processed.run_id).model_dump(mode="json"),
        }

    @app.get("/api/v1/demo/stock-card-image")
    def demo_stock_card_image() -> FileResponse:
        source = Path(fixture).parent / "stock_card_scan_demo.png"
        if not source.exists():
            raise HTTPException(status_code=404, detail="Demo stock card is unavailable")
        return FileResponse(source, media_type="image/png", filename="tulina-demo-stock-card.png")

    @app.post("/api/v1/demo/stock-card-intakes", status_code=201)
    async def extract_demo_stock_card(
        role: Role = Depends(require_role(Role.FACILITY_WORKER)),
    ) -> dict[str, object]:
        source = Path(fixture).parent / "stock_card_scan_demo.png"
        if not source.exists():
            raise HTTPException(status_code=404, detail="Demo stock card is unavailable")
        try:
            intake = await intake_agent_runtime.extract(
                image_bytes=source.read_bytes(),
                filename=source.name,
                claimed_mime="image/png",
                actor_id=role.value,
            )
        except (IntakeValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return intake.model_dump(mode="json")

    @app.post("/api/v1/stock-card-intakes", status_code=201)
    async def upload_stock_card(
        file: UploadFile = File(...),
        role: Role = Depends(require_role(Role.FACILITY_WORKER)),
    ) -> dict[str, object]:
        image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            intake = await intake_agent_runtime.extract(
                image_bytes=image_bytes,
                filename=file.filename or "stock-card",
                claimed_mime=file.content_type,
                actor_id=role.value,
            )
        except (IntakeValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await file.close()
        return intake.model_dump(mode="json")

    @app.get("/api/v1/stock-card-intakes/latest")
    def latest_stock_card_intake(
        _: Role = Depends(
            require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER, Role.AUDITOR)
        ),
    ) -> dict[str, object]:
        intake = intake_store.latest()
        if intake is None:
            raise HTTPException(status_code=404, detail="No stock card has been read")
        return intake.model_dump(mode="json")

    @app.get("/api/v1/stock-card-intakes/{intake_id}")
    def stock_card_intake(
        intake_id: str,
        _: Role = Depends(
            require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER, Role.AUDITOR)
        ),
    ) -> dict[str, object]:
        try:
            return intake_store.get(intake_id).model_dump(mode="json")
        except IntakeStoreError as exc:
            raise HTTPException(status_code=404, detail="Stock-card intake not found") from exc

    @app.patch("/api/v1/stock-card-intakes/{intake_id}")
    def correct_stock_card_intake(
        intake_id: str,
        correction: StockCardCorrectionRequest,
        role: Role = Depends(require_role(Role.FACILITY_WORKER)),
    ) -> dict[str, object]:
        try:
            intake = intake_service.correct(intake_id, correction, actor_id=role.value)
        except IntakeStoreError as exc:
            raise HTTPException(status_code=404, detail="Stock-card intake not found") from exc
        except IntakeValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return intake.model_dump(mode="json")

    @app.post("/api/v1/stock-card-intakes/{intake_id}/accept")
    def accept_stock_card_intake(
        intake_id: str,
        role: Role = Depends(require_role(Role.FACILITY_WORKER)),
    ) -> dict[str, object]:
        try:
            intake = intake_service.accept(intake_id, actor_id=role.value)
        except IntakeStoreError as exc:
            raise HTTPException(status_code=404, detail="Stock-card intake not found") from exc
        except IntakeValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return intake.model_dump(mode="json")

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
        agent_service.store.reset()
        intake_store.reset()
        protocol_store.reset()
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
    async def discover(
        _: Role = Depends(require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER)),
    ) -> dict[str, object]:
        current = repository.get_transfer("TR-027")
        if current.status != TransferStatus.FOUND:
            raise HTTPException(status_code=409, detail="Reset the demo before discovery")
        agent_service.start_watch_cycle(
            request=WatchCycleRequest(), requested_by=Role.FACILITY_WORKER.value
        )
        await agent_service.process_next()
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

    @app.get("/api/v1/trust-bundle")
    def trust_bundle(
        _: Role = Depends(require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER, Role.AUDITOR)),
    ) -> dict[str, object]:
        return protocol_service.trust_bundle().model_dump(mode="json")

    @app.post("/api/v1/devices/register")
    def register_device(
        registration: DeviceRegistration,
        _: Role = Depends(require_role(Role.FACILITY_WORKER)),
    ) -> dict[str, object]:
        try:
            saved = protocol_service.register_device(registration)
        except (ProtocolError, ProtocolStoreError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return saved.model_dump(mode="json")

    @app.post("/api/v1/transfers/TR-027/issue-note")
    async def issue_note(_: Role = Depends(require_role(Role.DHO_APPROVER))) -> dict[str, object]:
        try:
            await protocol_agent_runtime.issue("TR-027", Role.DHO_APPROVER.value)
        except ProtocolError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return overview()

    @app.get("/api/v1/transfers/TR-027/note")
    def get_note(
        _: Role = Depends(require_role(Role.FACILITY_WORKER, Role.DHO_APPROVER, Role.AUDITOR)),
    ) -> dict[str, object]:
        note = protocol_store.note_for_transfer("TR-027")
        if note is None:
            raise HTTPException(status_code=404, detail="The Tulina Note has not been issued")
        return note.model_dump(mode="json")

    @app.post("/api/v1/receipts/reconcile")
    async def reconcile_receipt(
        request: ReceiptSyncRequest,
        role: Role = Depends(require_role(Role.FACILITY_WORKER)),
    ) -> dict[str, object]:
        result = await protocol_agent_runtime.reconcile(request.receipt_token, role.value)
        return result.model_dump(mode="json")

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
