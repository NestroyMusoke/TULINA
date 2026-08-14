from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tulina_request_id", default=None)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tulina_trace_id", default=None)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$")


def current_request_id() -> str | None:
    return _request_id.get()


def current_trace_id() -> str | None:
    return _trace_id.get()


def audit_context() -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "request_id": current_request_id(),
            "request_trace_id": current_trace_id(),
        }.items()
        if value
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "service": "tulina-api",
            "event": getattr(record, "event", record.getMessage()),
            "request_id": current_request_id(),
            "trace_id": current_trace_id(),
        }
        for field in ("method", "path", "status_code", "duration_ms", "error_code", "actor_id", "role"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("tulina")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(getattr(handler, "_tulina_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._tulina_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


LOGGER = configure_logging()


def log_event(level: int, event: str, **fields: object) -> None:
    LOGGER.log(level, event, extra={"event": event, **fields})


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else f"REQ-{uuid4().hex[:16].upper()}"
        trace_id = f"TRACE-HTTP-{uuid4().hex[:16].upper()}"
        request_token = _request_id.set(request_id)
        trace_token = _trace_id.set(trace_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            log_event(
                logging.INFO if response.status_code < 500 else logging.ERROR,
                "HTTP_REQUEST_COMPLETED",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                role=request.headers.get("X-Tulina-Role"),
                actor_id=request.headers.get("X-Tulina-Actor"),
            )
            return response
        except Exception:
            log_event(
                logging.ERROR,
                "HTTP_REQUEST_FAILED",
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_code="UNHANDLED_EXCEPTION",
            )
            raise
        finally:
            _request_id.reset(request_token)
            _trace_id.reset(trace_token)


def install_problem_handlers(app) -> None:
    @app.exception_handler(HTTPException)
    async def http_problem(_: Request, exc: HTTPException) -> JSONResponse:
        detail = str(exc.detail) if isinstance(exc.detail, str) else "The request could not be completed"
        return _problem(exc.status_code, detail, f"HTTP_{exc.status_code}", exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_problem(_: Request, __: RequestValidationError) -> JSONResponse:
        return _problem(422, "Check the submitted fields and try again", "REQUEST_VALIDATION_FAILED")

    @app.exception_handler(Exception)
    async def unexpected_problem(_: Request, __: Exception) -> JSONResponse:
        return _problem(500, "Tulina could not complete the request", "INTERNAL_ERROR")


def _problem(
    status_code: int,
    detail: str,
    error_code: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "type": f"https://tulina.example/problems/{error_code.casefold()}",
            "title": "Request blocked" if status_code < 500 else "Service error",
            "status": status_code,
            "detail": detail,
            "error_code": error_code,
            "request_id": current_request_id(),
        },
    )
