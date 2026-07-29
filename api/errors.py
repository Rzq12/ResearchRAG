"""
Uniform error responses and correlation IDs.

Two goals:

1. **One error shape everywhere.** The project's own CLAUDE.md mandates
   ``{request_id, error, message, status_code}``; FastAPI's default is a bare
   ``{"detail": ...}``. Clients get one contract, and every response carries a
   request id that also appears in the logs.

2. **Never leak internals.** Unhandled exceptions are logged in full server-side
   but the client only ever sees a generic message — no stack traces, no
   provider payloads, no file paths.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("researchrag.api")

# Correlation id for the request currently being served, so log records made
# deep in the call stack can be tied back to the client's request.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"

# Maps HTTP status → stable, machine-readable error code for clients.
_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    status.HTTP_502_BAD_GATEWAY: "UPSTREAM_ERROR",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def new_request_id() -> str:
    return uuid.uuid4().hex


def _envelope(
    status_code: int,
    message: str,
    error: str | None = None,
    extra: dict | None = None,
) -> JSONResponse:
    rid = request_id_ctx.get()
    payload = {
        "request_id": rid,
        "error": error or _ERROR_CODES.get(status_code, "ERROR"),
        "message": message,
        "status_code": status_code,
    }
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload, headers={REQUEST_ID_HEADER: rid})


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers. Order matters: most specific first."""

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded):
        logger.warning(
            "rate_limit_exceeded",
            extra={"request_id": request_id_ctx.get(), "path": request.url.path},
        )
        return _envelope(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests. Please slow down and try again shortly.",
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException):
        response = _envelope(exc.status_code, str(exc.detail))
        # Preserve auth challenge headers (WWW-Authenticate) from 401s.
        for key, value in (getattr(exc, "headers", None) or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        # Field-level detail is safe and genuinely useful to the client.
        fields = [
            {"field": ".".join(str(p) for p in err.get("loc", [])), "message": err.get("msg", "")}
            for err in exc.errors()
        ]
        return _envelope(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Request validation failed.",
            extra={"fields": fields},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Full detail to the logs, nothing sensitive to the client.
        logger.exception(
            "unhandled_exception",
            extra={"request_id": request_id_ctx.get(), "path": request.url.path},
        )
        return _envelope(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An internal error occurred. Quote the request_id when reporting this.",
        )
