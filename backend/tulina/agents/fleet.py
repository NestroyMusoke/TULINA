from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import FunctionTool, ToolContext
from pydantic import PrivateAttr

from ..engine import DomainEngine
from ..repository import SQLiteRepository
from .models import (
    AgentStepOutcome,
    AgentStepStatus,
    GateResult,
    GovernanceResult,
    InventorySnapshotResult,
    MatchResult,
    WatchCycleRequest,
    WatchResult,
)
from .providers import DecisionProvider
from .store import SQLiteAgentStore
from .tools import ToolCatalog


@dataclass(frozen=True)
class FleetDependencies:
    engine: DomainEngine
    repository: SQLiteRepository
    store: SQLiteAgentStore
    tools: ToolCatalog
    provider: DecisionProvider
    step_delay_ms: int = 0


class RecordedToolAgent(BaseAgent):
    """Base ADK agent that persists every validated tool execution."""

    _dependencies: FleetDependencies = PrivateAttr()
    _tool: FunctionTool = PrivateAttr()

    def __init__(
        self,
        *,
        name: str,
        description: str,
        dependencies: FleetDependencies,
        tool: FunctionTool,
    ):
        super().__init__(name=name, description=description)
        self._dependencies = dependencies
        self._tool = tool

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        run_id = str(ctx.session.state["run_id"])
        step = self._dependencies.store.start_step(
            run_id=run_id, agent_name=self.name, tool_name=self._tool.name
        )
        run = self._dependencies.store.get_run(run_id)
        self._dependencies.repository.record_event(
            trace_id=run.trace_id,
            actor_id=self.name,
            event_type="AGENT_STEP_STARTED",
            summary=f"{self.description} started",
            details={"run_id": run_id, "tool_name": self._tool.name},
        )
        try:
            if self._dependencies.step_delay_ms:
                await asyncio.sleep(self._dependencies.step_delay_ms / 1000)
            outcome = await self.execute(ctx)
            self._dependencies.store.finish_step(
                step.step_id,
                status=outcome.status,
                summary=outcome.summary,
                evidence=outcome.evidence,
            )
            self._dependencies.repository.record_event(
                trace_id=run.trace_id,
                actor_id=self.name,
                event_type=outcome.event_type,
                summary=outcome.summary,
                details={
                    "run_id": run_id,
                    "tool_name": self._tool.name,
                    "step_status": outcome.status.value,
                },
            )
            yield Event(
                author=self.name,
                output=outcome.model_dump(mode="json"),
                actions=EventActions(
                    state_delta={outcome.state_key: outcome.evidence}
                ),
            )
        except Exception as exc:
            error_code = type(exc).__name__.upper()
            self._dependencies.store.fail_step(step.step_id, error_code=error_code)
            self._dependencies.repository.record_event(
                trace_id=run.trace_id,
                actor_id=self.name,
                event_type="AGENT_STEP_FAILED",
                summary=f"{self.description} stopped and needs review",
                details={"run_id": run_id, "error_code": error_code},
            )
            raise

    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        raise NotImplementedError

    async def run_tool(
        self, ctx: InvocationContext, args: dict[str, object]
    ) -> dict[str, object]:
        result = await self._tool.run_async(
            args=args, tool_context=ToolContext(ctx)
        )
        if not isinstance(result, dict):
            raise TypeError(f"{self._tool.name} returned a non-object result")
        if "error" in result:
            raise ValueError(str(result["error"]))
        return result

    @staticmethod
    def request(ctx: InvocationContext) -> WatchCycleRequest:
        return WatchCycleRequest.model_validate(ctx.session.state["request"])


class StockIntakeAgent(RecordedToolAgent):
    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        request = self.request(ctx)
        result = InventorySnapshotResult.model_validate(
            await self.run_tool(
                ctx,
                {
                    "recipient_facility_id": request.recipient_facility_id,
                    "product_id": request.product_id,
                },
            )
        )
        return AgentStepOutcome(
            status=AgentStepStatus.COMPLETED,
            event_type="STOCK_INTAKE_READY",
            summary=f"Validated {result.position_count} stock positions for the watch cycle",
            state_key="stock_snapshot",
            evidence=result.model_dump(mode="json"),
        )


class WatchAgent(RecordedToolAgent):
    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        request = self.request(ctx)
        result = WatchResult.model_validate(
            await self.run_tool(
                ctx,
                {
                    "recipient_facility_id": request.recipient_facility_id,
                    "product_id": request.product_id,
                },
            )
        )
        return AgentStepOutcome(
            status=AgentStepStatus.COMPLETED,
            event_type="WATCH_SIGNALS_CREATED",
            summary=(
                f"Detected {result.need_count} needs and {result.offer_count} safe offers; "
                f"the focus clinic has {result.focus_days_of_cover} days of cover"
            ),
            state_key="watch_result",
            evidence=result.model_dump(mode="json"),
        )


class MatchAgent(RecordedToolAgent):
    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        request = self.request(ctx)
        result = MatchResult.model_validate(
            await self.run_tool(
                ctx,
                {
                    "recipient_facility_id": request.recipient_facility_id,
                    "product_id": request.product_id,
                },
            )
        )
        selected = result.recommendation
        donor = self._dependencies.engine.facilities[selected.donor_facility_id]
        recipient = self._dependencies.engine.facilities[selected.recipient_facility_id]
        product = self._dependencies.engine.products[selected.product_id]
        return AgentStepOutcome(
            status=AgentStepStatus.COMPLETED,
            event_type="FOUND_NEARBY",
            summary=(
                f"Found {selected.quantity} safe packs of {product.item} at "
                f"{donor.short_name} for {recipient.short_name}"
            ),
            state_key="match_result",
            evidence=result.model_dump(mode="json"),
        )


class StewardAgent(RecordedToolAgent):
    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        match = MatchResult.model_validate(ctx.session.state["match_result"])
        result = GovernanceResult.model_validate(
            await self.run_tool(
                ctx, {"transfer_id": match.recommendation.transfer_id}
            )
        )
        explanation = await self._dependencies.provider.explain(match.recommendation)
        evidence = {
            **result.model_dump(mode="json"),
            "explanation": explanation.model_dump(mode="json"),
            "provider": self._dependencies.provider.name,
            "model_name": self._dependencies.provider.model_name,
        }
        return AgentStepOutcome(
            status=AgentStepStatus.COMPLETED,
            event_type="STEWARDSHIP_REVIEW_COMPLETED",
            summary=(
                "All safety gates passed; a District Health Officer decision is required"
                if result.requires_human_approval
                else "All safety gates passed; facility-level approval is permitted"
            ),
            state_key="governance_result",
            evidence=evidence,
        )


class DispatchAgent(RecordedToolAgent):
    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        match = MatchResult.model_validate(ctx.session.state["match_result"])
        result = GateResult.model_validate(
            await self.run_tool(
                ctx, {"transfer_id": match.recommendation.transfer_id}
            )
        )
        return AgentStepOutcome(
            status=(
                AgentStepStatus.COMPLETED if result.ready else AgentStepStatus.WAITING
            ),
            event_type=(
                "DISPATCH_READY" if result.ready else "DISPATCH_WAITING_FOR_APPROVAL"
            ),
            summary=result.reason,
            state_key="dispatch_gate",
            evidence=result.model_dump(mode="json"),
        )


class ReconciliationAgent(RecordedToolAgent):
    async def execute(self, ctx: InvocationContext) -> AgentStepOutcome:
        match = MatchResult.model_validate(ctx.session.state["match_result"])
        result = GateResult.model_validate(
            await self.run_tool(
                ctx, {"transfer_id": match.recommendation.transfer_id}
            )
        )
        return AgentStepOutcome(
            status=(
                AgentStepStatus.COMPLETED if result.ready else AgentStepStatus.WAITING
            ),
            event_type=(
                "RECONCILIATION_READY"
                if result.ready
                else "RECONCILIATION_WAITING_FOR_RECEIPT"
            ),
            summary=result.reason,
            state_key="reconciliation_gate",
            evidence=result.model_dump(mode="json"),
        )


class TulinaFleetAgent(BaseAgent):
    """ADK parent agent with explicit, inspectable six-agent control flow."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        for agent in self.sub_agents:
            async for event in agent.run_async(ctx):
                yield event


def build_fleet(dependencies: FleetDependencies) -> TulinaFleetAgent:
    agents = [
        StockIntakeAgent(
            name="stock_intake_agent",
            description="Stock Intake Agent validation preflight",
            dependencies=dependencies,
            tool=dependencies.tools.validate_inventory_snapshot,
        ),
        WatchAgent(
            name="watch_agent",
            description="Watch Agent district stock monitoring",
            dependencies=dependencies,
            tool=dependencies.tools.detect_stock_signals,
        ),
        MatchAgent(
            name="match_agent",
            description="Match Agent safe transfer ranking",
            dependencies=dependencies,
            tool=dependencies.tools.rank_safe_transfers,
        ),
        StewardAgent(
            name="steward_agent",
            description="Steward Agent governance review",
            dependencies=dependencies,
            tool=dependencies.tools.evaluate_governance,
        ),
        DispatchAgent(
            name="dispatch_agent",
            description="Dispatch Agent approval gate",
            dependencies=dependencies,
            tool=dependencies.tools.check_dispatch_gate,
        ),
        ReconciliationAgent(
            name="reconciliation_agent",
            description="Reconciliation Agent receipt gate",
            dependencies=dependencies,
            tool=dependencies.tools.check_reconciliation_gate,
        ),
    ]
    return TulinaFleetAgent(
        name="tulina_fleet",
        description="Coordinates Tulina's asynchronous district medicine workflow",
        sub_agents=agents,
    )


FLEET_REGISTRY = (
    {
        "name": "stock_intake_agent",
        "label": "Stock Intake Agent",
        "tool": "extract_stock_card / validate_inventory_snapshot",
        "authority": "Creates observations; never changes inventory",
    },
    {
        "name": "watch_agent",
        "label": "Watch Agent",
        "tool": "detect_stock_signals",
        "authority": "Finds needs and safe offers",
    },
    {
        "name": "match_agent",
        "label": "Match Agent",
        "tool": "rank_safe_transfers",
        "authority": "Ranks proposals; cannot approve",
    },
    {
        "name": "steward_agent",
        "label": "Steward Agent",
        "tool": "evaluate_governance",
        "authority": "Explains policy and requires human authority",
    },
    {
        "name": "dispatch_agent",
        "label": "Dispatch Agent",
        "tool": "check_dispatch_gate / issue_signed_tulina_note",
        "authority": "Issues a signed note only after human approval",
    },
    {
        "name": "reconciliation_agent",
        "label": "Reconciliation Agent",
        "tool": "check_reconciliation_gate / reconcile_signed_receipt",
        "authority": "Verifies receipts and applies an idempotent mutation",
    },
)
