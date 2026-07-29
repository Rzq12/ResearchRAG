"""
Request middleware: correlation IDs and structured access logging.

Replaces ad-hoc ``print()`` on the request path. Every line is JSON so a log
aggregator can index it, and every line carries the same ``request_id`` the
client received in its response header — which makes a user-reported error
traceable to a single request.

Deliberately never logs: request bodies, Authorization headers, or LLM API keys.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from api.errors import REQUEST_ID_HEADER, new_request_id, request_id_ctx

logger = logging.getLogger("researchrag.api")

# Never emit these, whatever happens.
_REDACTED_HEADERS = {"authorization", "cookie", "x-api-key"}


class JsonLogFormatter(logging.Formatter):
    """Minimal JSON formatter — no dependency on structlog."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms", "client"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Install a single stdout handler. Safe to call once at startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonLogFormatter()
        if json_output
        else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn's own access log would duplicate ours.
    logging.getLogger("uvicorn.access").disabled = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, log the outcome, and echo the id to the client."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = request_id_ctx.set(rid)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # The exception handler builds the response; just record timing.
            logger.exception(
                "request_failed",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_ctx.reset(token)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers[REQUEST_ID_HEADER] = rid

        logger.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else None,
            },
        )
        request_id_ctx.reset(token)
        return response
