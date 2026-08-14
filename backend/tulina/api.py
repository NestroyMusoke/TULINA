from __future__ import annotations

import os
from importlib.metadata import version
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .agents.fleet import FLEET_REGISTRY
from .agents.models import WatchCycleRequest
from .agents.runtime import build_agent_runtime
from .agents.settings import AgentSettings
from .agents.store import AgentStoreError
from .cloud.document_store import DocumentStore, GoogleFirestoreDocumentStore
from .cloud.firestore import (
    FirestoreAgentStore,
    FirestoreIntakeStore,
    FirestoreProtocolStore,
    FirestoreRepository,
)
from .cloud.kms import CloudKmsP256Signer
from .cloud.pubsub import (
    PubSubAuthenticationError,
    PubSubPayloadError,
    PubSubPushEnvelope,
    TokenVerifier,
    decode_agent_run,
    verify_pubsub_oidc,
)
from .engine import DomainEngine
from .fixtures import load_fixture
from .intake.agent import StockIntakeAgentRuntime
from .intake.models import StockCardCorrectionRequest
from .intake.providers import build_stock_card_provider
from .intake.service import MAX_UPLOAD_BYTES, IntakeValidationError, StockCardIntakeService
from .intake.store import IntakeStoreError, SQLiteIntakeStore
from .metrics import metrics_for
from .models import TransferRecommendation, TransferStatus
from .observability import RequestContextMiddleware, current_request_id, install_problem_handlers
from .protocol.agent import ProtocolAgentRuntime
from .protocol.models import (
    DeviceRegistration,
    OfflineVerificationReport,
    QuarantineResolutionRequest,
    ReceiptSyncRequest,
)
from .protocol.service import ProtocolError, ProtocolService
from .protocol.store import ProtocolStore, ProtocolStoreError, SQLiteProtocolStore
from .repository import Repository, SQLiteRepository
from .security import ROLE_PERMISSIONS, Action, Principal, Role, require_action
from .state_machine import InvalidTransition, TransitionContext


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
    document_store: DocumentStore | None = None,
    kms_client=None,
    oidc_verifier: TokenVerifier | None = None,
) -> FastAPI:
    data = load_fixture(fixture)
    engine = DomainEngine(data)
    agent_settings = agent_settings or AgentSettings()
    database_path = database or os.getenv(
        "TULINA_DATABASE_PATH", "data/runtime/tulina.sqlite3"
    )
    cloud_store: DocumentStore | None = None
    if agent_settings.repository_backend == "firestore":
        cloud_store = document_store or GoogleFirestoreDocumentStore(
            project_id=agent_settings.google_cloud_project or "",
            namespace=agent_settings.firestore_namespace,
            database=agent_settings.firestore_database,
        )
        repository: Repository = FirestoreRepository(cloud_store)
        agent_store = FirestoreAgentStore(cloud_store)
        intake_store = FirestoreIntakeStore(cloud_store)
        protocol_store: ProtocolStore = FirestoreProtocolStore(cloud_store)
        signer = CloudKmsP256Signer(
            agent_settings.kms_key_version or "", client=kms_client
        )
    else:
        repository = SQLiteRepository(database_path)
        agent_store = None
        intake_store = SQLiteIntakeStore(database_path)
        protocol_store = SQLiteProtocolStore(database_path)
        signer = None
    repository.seed(engine.all_positions(), engine.recommendations())
    agent_service = build_agent_runtime(
        engine=engine,
        repository=repository,
        database=database_path,
        settings=agent_settings,
        publisher=publisher,
        store=agent_store,
    )
    intake_service = StockCardIntakeService(
        engine=engine,
        repository=repository,
        store=intake_store,
        provider=intake_provider or build_stock_card_provider(agent_settings),
    )
    intake_agent_runtime = StockIntakeAgentRuntime(intake_service)
    protocol_service = ProtocolService(
        repository=repository, store=protocol_store, signer=signer
    )
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
    app.state.document_store = cloud_store
    allowed_origins = os.getenv("TULINA_ALLOWED_ORIGINS", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[value.strip() for value in allowed_origins.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Tulina-Role", "X-Tulina-Actor", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    install_problem_handlers(app)

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "tulina-api", "mode": agent_settings.mode}

    @app.get("/readyz")
    def ready(response: Response) -> dict[str, object]:
        try:
            storage_reachable = cloud_store.ping() if cloud_store else True
            audit_verified = repository.verify_audit_chain()
            signer_reachable = bool(signer.jwk) if signer else True
        except Exception:
            storage_reachable = False
            audit_verified = False
            signer_reachable = False
        is_ready = storage_reachable and audit_verified and signer_reachable
        if not is_ready:
            response.status_code = 503
        return {
            "ready": is_ready,
            "database": repository.backend_name,
            "storage_reachable": storage_reachable,
            "signer_reachable": signer_reachable,
            "fixture_records": len(engine.all_positions()),
            "agent_runtime": "google-adk",
            "queue_backend": agent_service.queue.backend_name,
            "workflow_store": agent_service.store.backend_name,
            "stock_card_provider": intake_service.provider.name,
            "offline_note_signer": "cloud-kms-p256" if signer else "local-p256",
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
            "governance": _governance_payload(repository, protocol_store),
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
        principal: Principal = Depends(require_action(Action.START_WATCH)),
    ) -> dict[str, object]:
        if request.trigger == "inventory_event" and intake_store.latest_accepted() is None:
            raise HTTPException(
                status_code=409,
                detail="Confirm the stock-card observation before starting inventory checks",
            )
        run = agent_service.start_watch_cycle(
            request=request, requested_by=principal.actor_id
        )
        if agent_service.queue.backend_name == "local":
            background_tasks.add_task(agent_service.process_next)
        return agent_service.detail(run.run_id).model_dump(mode="json")

    @app.get("/api/v1/agent-runs/latest")
    def latest_agent_run(
        _: Principal = Depends(require_action(Action.READ_TECHNICAL)),
    ) -> dict[str, object]:
        latest = agent_service.latest_detail()
        if latest is None:
            raise HTTPException(status_code=404, detail="No background run exists")
        return latest.model_dump(mode="json")

    @app.get("/api/v1/agent-runs/{run_id}")
    def agent_run(
        run_id: str,
        _: Principal = Depends(require_action(Action.READ_TECHNICAL)),
    ) -> dict[str, object]:
        try:
            return agent_service.detail(run_id).model_dump(mode="json")
        except AgentStoreError as exc:
            raise HTTPException(status_code=404, detail="Agent run not found") from exc

    @app.post("/api/v1/agent-worker/process-next")
    async def process_next_agent_run(
        _: Principal = Depends(require_action(Action.PROCESS_QUEUE)),
    ) -> dict[str, object]:
        processed = await agent_service.process_next()
        if processed is None:
            return {"processed": False, "run": None}
        return {
            "processed": True,
            "run": agent_service.detail(processed.run_id).model_dump(mode="json"),
        }

    @app.post("/api/v1/internal/pubsub/agent-runs", status_code=204)
    async def process_pubsub_agent_run(
        envelope: PubSubPushEnvelope,
        authorization: str | None = Header(default=None),
    ) -> Response:
        if agent_service.queue.backend_name != "pubsub":
            raise HTTPException(status_code=404, detail="Pub/Sub worker is not configured")
        try:
            verify_pubsub_oidc(
                authorization,
                audience=agent_settings.pubsub_audience or "",
                service_account=agent_settings.pubsub_service_account or "",
                verifier=oidc_verifier,
            )
            published = decode_agent_run(envelope)
            durable = agent_service.store.get_run(published.run_id)
        except PubSubAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except (PubSubPayloadError, AgentStoreError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        durable_reference = (
            durable.run_id,
            durable.trace_id,
            durable.requested_by,
            durable.provider,
            durable.model_name,
            durable.queue_backend,
            durable.request,
            durable.created_at,
        )
        published_reference = (
            published.run_id,
            published.trace_id,
            published.requested_by,
            published.provider,
            published.model_name,
            published.queue_backend,
            published.request,
            published.created_at,
        )
        if durable_reference != published_reference:
            raise HTTPException(
                status_code=409,
                detail="Published workflow reference does not match durable Firestore state",
            )
        await agent_service.process_run(published.run_id)
        return Response(status_code=204)

    @app.get("/api/v1/demo/stock-card-image")
    def demo_stock_card_image() -> FileResponse:
        source = Path(fixture).parent / "stock_card_scan_demo.png"
        if not source.exists():
            raise HTTPException(status_code=404, detail="Demo stock card is unavailable")
        return FileResponse(source, media_type="image/png", filename="tulina-demo-stock-card.png")

    @app.post("/api/v1/demo/stock-card-intakes", status_code=201)
    async def extract_demo_stock_card(
        principal: Principal = Depends(require_action(Action.RECORD_STOCK)),
    ) -> dict[str, object]:
        source = Path(fixture).parent / "stock_card_scan_demo.png"
        if not source.exists():
            raise HTTPException(status_code=404, detail="Demo stock card is unavailable")
        try:
            intake = await intake_agent_runtime.extract(
                image_bytes=source.read_bytes(),
                filename=source.name,
                claimed_mime="image/png",
                actor_id=principal.actor_id,
            )
        except (IntakeValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return intake.model_dump(mode="json")

    @app.post("/api/v1/stock-card-intakes", status_code=201)
    async def upload_stock_card(
        file: UploadFile = File(...),
        principal: Principal = Depends(require_action(Action.RECORD_STOCK)),
    ) -> dict[str, object]:
        image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            intake = await intake_agent_runtime.extract(
                image_bytes=image_bytes,
                filename=file.filename or "stock-card",
                claimed_mime=file.content_type,
                actor_id=principal.actor_id,
            )
        except (IntakeValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            await file.close()
        return intake.model_dump(mode="json")

    @app.get("/api/v1/stock-card-intakes/latest")
    def latest_stock_card_intake(
        _: Principal = Depends(require_action(Action.READ_TECHNICAL)),
    ) -> dict[str, object]:
        intake = intake_store.latest()
        if intake is None:
            raise HTTPException(status_code=404, detail="No stock card has been read")
        return intake.model_dump(mode="json")

    @app.get("/api/v1/stock-card-intakes/{intake_id}")
    def stock_card_intake(
        intake_id: str,
        _: Principal = Depends(require_action(Action.READ_TECHNICAL)),
    ) -> dict[str, object]:
        try:
            return intake_store.get(intake_id).model_dump(mode="json")
        except IntakeStoreError as exc:
            raise HTTPException(status_code=404, detail="Stock-card intake not found") from exc

    @app.patch("/api/v1/stock-card-intakes/{intake_id}")
    def correct_stock_card_intake(
        intake_id: str,
        correction: StockCardCorrectionRequest,
        principal: Principal = Depends(require_action(Action.RECORD_STOCK)),
    ) -> dict[str, object]:
        try:
            intake = intake_service.correct(intake_id, correction, actor_id=principal.actor_id)
        except IntakeStoreError as exc:
            raise HTTPException(status_code=404, detail="Stock-card intake not found") from exc
        except IntakeValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return intake.model_dump(mode="json")

    @app.post("/api/v1/stock-card-intakes/{intake_id}/accept")
    def accept_stock_card_intake(
        intake_id: str,
        principal: Principal = Depends(require_action(Action.RECORD_STOCK)),
    ) -> dict[str, object]:
        try:
            intake = intake_service.accept(intake_id, actor_id=principal.actor_id)
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
    def activity(_: Principal = Depends(require_action(Action.READ_AUDIT))):
        return {"events": [row.model_dump(mode="json") for row in repository.events()]}

    @app.post("/api/v1/demo/reset")
    def reset(_: Principal = Depends(require_action(Action.RESET_DEMO))) -> dict[str, object]:
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
        principal: Principal = Depends(require_action(Action.START_WATCH)),
    ) -> dict[str, object]:
        current = repository.get_transfer("TR-027")
        if current.status != TransferStatus.FOUND:
            raise HTTPException(status_code=409, detail="Reset the demo before discovery")
        agent_service.start_watch_cycle(
            request=WatchCycleRequest(), requested_by=principal.actor_id
        )
        await agent_service.process_next()
        return overview()

    @app.post("/api/v1/transfers/TR-027/request-approval")
    def request_approval(
        _: Principal = Depends(require_action(Action.REQUEST_APPROVAL)),
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
    def approve(
        principal: Principal = Depends(require_action(Action.APPROVE_TRANSFER)),
    ) -> dict[str, object]:
        try:
            repository.change_status(
                "TR-027",
                TransferStatus.APPROVED,
                TransitionContext(
                    actor_id=principal.actor_id,
                    actor_role=Role.DHO_APPROVER.value,
                    reason="District Health Officer approved 11 transfer packs",
                ),
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return overview()

    @app.get("/api/v1/trust-bundle")
    def trust_bundle(
        _: Principal = Depends(require_action(Action.READ_TECHNICAL)),
    ) -> dict[str, object]:
        return protocol_service.trust_bundle().model_dump(mode="json")

    @app.post("/api/v1/devices/register")
    def register_device(
        registration: DeviceRegistration,
        _: Principal = Depends(require_action(Action.REGISTER_DEVICE)),
    ) -> dict[str, object]:
        try:
            saved = protocol_service.register_device(registration)
        except (ProtocolError, ProtocolStoreError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return saved.model_dump(mode="json")

    @app.post("/api/v1/transfers/TR-027/issue-note")
    async def issue_note(
        principal: Principal = Depends(require_action(Action.ISSUE_NOTE)),
    ) -> dict[str, object]:
        try:
            await protocol_agent_runtime.issue("TR-027", principal.actor_id)
        except ProtocolError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return overview()

    @app.get("/api/v1/transfers/TR-027/note")
    def get_note(
        _: Principal = Depends(require_action(Action.READ_TECHNICAL)),
    ) -> dict[str, object]:
        note = protocol_store.note_for_transfer("TR-027")
        if note is None:
            raise HTTPException(status_code=404, detail="The Tulina Note has not been issued")
        return note.model_dump(mode="json")

    @app.post("/api/v1/receipts/reconcile")
    async def reconcile_receipt(
        request: ReceiptSyncRequest,
        principal: Principal = Depends(require_action(Action.RECONCILE_RECEIPT)),
    ) -> dict[str, object]:
        result = await protocol_agent_runtime.reconcile(request.receipt_token, principal.actor_id)
        return result.model_dump(mode="json")

    @app.post("/api/v1/security-events/offline-verification", status_code=201)
    def report_offline_verification(
        report: OfflineVerificationReport,
        principal: Principal = Depends(require_action(Action.REPORT_OFFLINE_REJECTION)),
    ) -> dict[str, object]:
        event = repository.record_event(
            trace_id=f"TRACE-{report.transfer_id}",
            actor_id=principal.actor_id,
            event_type="OFFLINE_NOTE_REJECTED",
            summary="Receiving phone rejected a changed or unsafe Tulina Note before receipt creation",
            details={
                **report.model_dump(mode="json"),
                "evidence_class": "recipient_device_report",
                "stock_mutations_applied": 0,
            },
        )
        return event.model_dump(mode="json")

    @app.get("/api/v1/audit/events")
    def audit_events(
        trace_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        _: Principal = Depends(require_action(Action.READ_AUDIT)),
    ) -> dict[str, object]:
        rows = repository.events(trace_id)
        return {
            "events": [row.model_dump(mode="json") for row in rows[-limit:]],
            "audit_chain": repository.audit_status(),
        }

    @app.get("/api/v1/governance/status")
    def governance_status(
        _: Principal = Depends(require_action(Action.READ_AUDIT)),
    ) -> dict[str, object]:
        return _governance_payload(repository, protocol_store)

    @app.get("/api/v1/exceptions")
    def exceptions(
        _: Principal = Depends(require_action(Action.READ_AUDIT)),
    ) -> dict[str, object]:
        return {
            "cases": [row.model_dump(mode="json") for row in protocol_store.quarantine_cases()]
        }

    @app.post("/api/v1/exceptions/{receipt_id}/resolve")
    def resolve_exception(
        receipt_id: str,
        request: QuarantineResolutionRequest,
        principal: Principal = Depends(require_action(Action.RESOLVE_EXCEPTION)),
    ) -> dict[str, object]:
        try:
            case = protocol_service.resolve_quarantine(
                receipt_id, note=request.note, actor_id=principal.actor_id
            )
        except ProtocolStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return case.model_dump(mode="json")

    return app


def _network_payload(engine: DomainEngine, repository: Repository) -> list[dict[str, object]]:
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


def _governance_payload(
    repository: Repository, protocol_store: ProtocolStore
) -> dict[str, object]:
    return {
        "audit_chain": repository.audit_status(),
        "unresolved_exceptions": protocol_store.unresolved_quarantined_count(),
        "exceptions": [row.model_dump(mode="json") for row in protocol_store.quarantine_cases()],
        "authorization_mode": (
            "fixture-role-headers" if repository.backend_name == "sqlite" else "cloud-run-and-role-headers"
        ),
        "role_permissions": {
            role.value: sorted(action.value for action in actions)
            for role, actions in ROLE_PERMISSIONS.items()
        },
        "request_id": current_request_id(),
        "reasoning_policy": "concise-decision-evidence-only",
    }


app = create_app()
