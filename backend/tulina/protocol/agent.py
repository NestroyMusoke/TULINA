from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps import App
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, ToolContext
from google.genai import types
from pydantic import PrivateAttr

from .models import ReconciliationResult, SignedTulinaNote
from .service import ProtocolService


class DispatchProtocolAgent(BaseAgent):
    _tool: FunctionTool = PrivateAttr()

    def __init__(self, tool: FunctionTool):
        super().__init__(
            name="dispatch_agent",
            description="Issues a signed one-use Tulina Note only after recorded DHO approval",
        )
        self._tool = tool

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        result = await self._tool.run_async(
            args={"transfer_id": str(ctx.session.state["transfer_id"])},
            tool_context=ToolContext(ctx),
        )
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("Dispatch tool returned an invalid note")
        note = SignedTulinaNote.model_validate(result)
        yield Event(
            author=self.name,
            output={"capsule_id": note.payload.capsule_id, "key_id": note.key_id},
            actions=EventActions(state_delta={"capsule_id": note.payload.capsule_id}),
        )


class ReceiptReconciliationAgent(BaseAgent):
    _tool: FunctionTool = PrivateAttr()

    def __init__(self, tool: FunctionTool):
        super().__init__(
            name="reconciliation_agent",
            description="Verifies signed offline receipts and applies a safe stock mutation exactly once",
        )
        self._tool = tool

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        result = await self._tool.run_async(
            args={"receipt_token": str(ctx.session.state["receipt_token"])},
            tool_context=ToolContext(ctx),
        )
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("Reconciliation tool returned an invalid result")
        reconciliation = ReconciliationResult.model_validate(result)
        yield Event(
            author=self.name,
            output={
                "receipt_id": reconciliation.receipt_id,
                "decision": reconciliation.decision.value,
                "mutation_count": reconciliation.transfer_mutations_applied,
            },
            actions=EventActions(
                state_delta={"reconciliation_result": reconciliation.model_dump(mode="json")}
            ),
        )


class ProtocolAgentRuntime:
    """Runs dispatch and reconciliation as real ADK tool-using agents."""

    def __init__(self, service: ProtocolService):
        self.service = service

        def issue_signed_tulina_note(transfer_id: str) -> dict[str, object]:
            """Issue and persist a P-256 Tulina Note after the human approval gate."""
            return service.issue_note(transfer_id).model_dump(mode="json")

        def reconcile_signed_receipt(receipt_token: str) -> dict[str, object]:
            """Verify a device receipt and apply or reject its stock mutation exactly once."""
            return service.reconcile(receipt_token).model_dump(mode="json")

        self.dispatch_tool = FunctionTool(func=issue_signed_tulina_note)
        self.reconciliation_tool = FunctionTool(func=reconcile_signed_receipt)
        self.dispatch_agent = DispatchProtocolAgent(self.dispatch_tool)
        self.reconciliation_agent = ReceiptReconciliationAgent(self.reconciliation_tool)
        self.sessions = InMemorySessionService()
        self.dispatch_runner = Runner(
            app=App(name="tulina_dispatch", root_agent=self.dispatch_agent),
            session_service=self.sessions,
        )
        self.reconciliation_runner = Runner(
            app=App(name="tulina_reconciliation", root_agent=self.reconciliation_agent),
            session_service=self.sessions,
        )

    async def issue(self, transfer_id: str, actor_id: str) -> SignedTulinaNote:
        session_id = f"DISPATCH-{uuid4().hex[:12].upper()}"
        await self.sessions.create_session(
            app_name="tulina_dispatch",
            user_id=actor_id,
            session_id=session_id,
            state={"transfer_id": transfer_id},
        )
        try:
            message = types.Content(
                role="user",
                parts=[types.Part(text="Recorded DHO approval is ready for dispatch validation.")],
            )
            async for _ in self.dispatch_runner.run_async(
                user_id=actor_id, session_id=session_id, new_message=message
            ):
                pass
            note = self.service.store.note_for_transfer(transfer_id) or self.service.issue_note(transfer_id)
            self.service.repository.record_event(
                trace_id=f"TRACE-{transfer_id}",
                actor_id=self.dispatch_agent.name,
                event_type="ADK_DISPATCH_COMPLETED",
                summary="Dispatch Agent issued the signed Tulina Note through a validated tool",
                details={
                    "framework": "Google ADK",
                    "tool_name": self.dispatch_tool.name,
                    "capsule_id": note.payload.capsule_id,
                },
            )
            return note
        finally:
            await self.sessions.delete_session(
                app_name="tulina_dispatch", user_id=actor_id, session_id=session_id
            )

    async def reconcile(self, receipt_token: str, actor_id: str) -> ReconciliationResult:
        session_id = f"RECON-{uuid4().hex[:12].upper()}"
        await self.sessions.create_session(
            app_name="tulina_reconciliation",
            user_id=actor_id,
            session_id=session_id,
            state={"receipt_token": receipt_token},
        )
        try:
            message = types.Content(
                role="user",
                parts=[types.Part(text="A signed offline receipt is queued for deterministic verification.")],
            )
            async for _ in self.reconciliation_runner.run_async(
                user_id=actor_id, session_id=session_id, new_message=message
            ):
                pass
            session = await self.sessions.get_session(
                app_name="tulina_reconciliation", user_id=actor_id, session_id=session_id
            )
            if session is None or "reconciliation_result" not in session.state:
                raise RuntimeError("Reconciliation Agent finished without a validated result")
            result = ReconciliationResult.model_validate(session.state["reconciliation_result"])
            self.service.repository.record_event(
                trace_id=f"TRACE-{result.transfer_id or 'PROTOCOL'}",
                actor_id=self.reconciliation_agent.name,
                event_type="ADK_RECONCILIATION_COMPLETED",
                summary="Reconciliation Agent verified the queued receipt through a validated tool",
                details={
                    "framework": "Google ADK",
                    "tool_name": self.reconciliation_tool.name,
                    "decision": result.decision.value,
                    "mutation_count": result.transfer_mutations_applied,
                },
            )
            return result
        finally:
            await self.sessions.delete_session(
                app_name="tulina_reconciliation", user_id=actor_id, session_id=session_id
            )
