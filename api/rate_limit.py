"""
Rate limiting for the ResearchRAG API.

Every endpoint here is expensive: a chat turn runs HyDE (2 LLM calls), BM25, a
CPU cross-encoder rerank and a streamed completion; an upload runs the full PDF
pipeline. Without limits a single client can exhaust CPU and burn the user's
LLM quota.

Limits are keyed by authenticated user when a bearer token is present, falling
back to client IP for anonymous routes such as login. That way one user hitting
their limit never throttles everyone behind the same NAT.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _identify(request: Request) -> str:
    """Prefer the token subject; fall back to the peer address."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            try:
                from api.security import decode_access_token

                return f"user:{decode_access_token(token)}"
            except Exception:
                # Invalid/expired token — fall through to IP so the limiter
                # never rejects a request for the wrong reason.
                pass
    return f"ip:{get_remote_address(request)}"


# headers_enabled=False: slowapi's X-RateLimit-* injection requires every
# decorated endpoint to accept a `response: Response` parameter, which would
# leak a transport concern into each handler's signature. Enforcement (and the
# 429 response) is unaffected — only the advisory headers are omitted.
# default_limits is what makes the module docstring true. Without it slowapi
# evaluates an EMPTY limit list for every undecorated route, so /api/ready,
# /auth/logout, /auth/me and the whole documents read surface were unlimited —
# each one touching Chroma or SQLite from a finite threadpool.
limiter = Limiter(
    key_func=_identify,
    default_limits=["120/minute"],
    headers_enabled=False,
)
