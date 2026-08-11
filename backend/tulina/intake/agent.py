from __future__ import annotations

import base64
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

from .models import StockCardIntake
from .service import StockCardIntakeService

INTAKE_APP_NAME = "stock_intake"


class MultimodalStockIntakeAgent(BaseAgent):
    """ADK agent that invokes the validated multimodal extraction tool."""

    _tool: FunctionTool = PrivateAttr()

    def __init__(self, tool: FunctionTool):
        super().__init__(
            name="stock_intake_agent",
            description="Extracts a stock card and routes uncertain fields to a human",
        )
        self._tool = tool

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        result = await self._tool.run_async(
            args=dict(ctx.session.state["intake_request"]),
            tool_context=ToolContext(ctx),
        )
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("Stock-card extraction tool returned an invalid result")
        intake = StockCardIntake.model_validate(result)
        yield Event(
            author=self.name,
            output={
                "intake_id": intake.intake_id,
                "status": intake.status.value,
                "provider": intake.provider,
            },
            actions=EventActions(state_delta={"intake_id": intake.intake_id}),
        )


class StockIntakeAgentRuntime:
    def __init__(self, service: StockCardIntakeService):
        self.service = service

        async def extract_stock_card(
            image_base64: str,
            filename: str,
            mime_type: str,
            actor_id: str,
        ) -> dict[str, object]:
            """Extract and persist a validated stock-card observation."""
            image_bytes = base64.b64decode(image_base64, validate=True)
            intake = await service.extract(
                image_bytes=image_bytes,
                filename=filename,
                claimed_mime=mime_type,
                actor_id=actor_id,
            )
            return intake.model_dump(mode="json")

        self.tool = FunctionTool(func=extract_stock_card)
        self.agent = MultimodalStockIntakeAgent(self.tool)
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app=App(name=INTAKE_APP_NAME, root_agent=self.agent),
            session_service=self.session_service,
        )

    async def extract(
        self,
        *,
        image_bytes: bytes,
        filename: str,
        claimed_mime: str | None,
        actor_id: str,
    ) -> StockCardIntake:
        session_id = f"INTAKE-{uuid4().hex[:12].upper()}"
        await self.session_service.create_session(
            app_name=INTAKE_APP_NAME,
            user_id=actor_id,
            session_id=session_id,
            state={
                "intake_request": {
                    "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                    "filename": filename,
                    "mime_type": claimed_mime or "",
                    "actor_id": actor_id,
                }
            },
        )
        try:
            message = types.Content(
                role="user",
                parts=[types.Part(text="New stock-card image ready for validated extraction.")],
            )
            async for _ in self.runner.run_async(
                user_id=actor_id,
                session_id=session_id,
                new_message=message,
            ):
                pass
            session = await self.session_service.get_session(
                app_name=INTAKE_APP_NAME,
                user_id=actor_id,
                session_id=session_id,
            )
            if session is None or "intake_id" not in session.state:
                raise RuntimeError("Stock Intake Agent finished without a durable observation")
            return self.service.store.get(str(session.state["intake_id"]))
        finally:
            await self.session_service.delete_session(
                app_name=INTAKE_APP_NAME,
                user_id=actor_id,
                session_id=session_id,
            )
