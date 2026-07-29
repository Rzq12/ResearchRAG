"""
ResearchRAG FastAPI application.

A thin HTTP wrapper around the existing ``app/`` backend so a React frontend
can use every feature the Streamlit app has. Run with:

    uvicorn api.main:app --host 0.0.0.0 --port 8000

The Streamlit app (``streamlit_app.py``) is unaffected and can keep running
independently against the same data.

Security posture:
  - every data route requires a bearer token (``api.security.current_user``)
  - the user id is derived from that token only, never from the request body
  - CORS is an explicit allowlist and fails closed outside development
  - all endpoints are rate limited; errors use one envelope and leak nothing
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.auth import init_auth_db
from app.config import get_settings
from app.database import init_chroma
from app.reranker import warm_reranker
from app.sessions import init_sessions_db, purge_expired

from api.errors import register_exception_handlers
from api.middleware import RequestContextMiddleware, configure_logging
from api.rate_limit import limiter
from api.routers import auth, chat, documents, meta, openalex, search
from api.settings import get_api_settings

logger = logging.getLogger("researchrag.api")

api_settings = get_api_settings()

# Fail fast on missing production configuration (JWT secret, CORS allowlist)
# rather than booting with insecure defaults.
api_settings.validate_runtime()

configure_logging(json_output=api_settings.is_production)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same startup work the Streamlit app performs in its cached startup(),
    # plus the refresh-token table used only by the API.
    init_chroma()
    init_auth_db()
    init_sessions_db()
    # Warm the cross-encoder here too. init_chroma()/get_embedder() covered the
    # embedder but not the reranker, so its ~500 MB load landed on whichever
    # request arrived first — and on a cold container several concurrent first
    # requests each started their own copy.
    _cfg = get_settings()
    if getattr(_cfg, "enable_reranker", False):
        warm_reranker(_cfg.reranker_model)
    removed = purge_expired()
    logger.info(
        "api_ready",
        extra={"request_id": "-", "path": f"env={api_settings.environment} purged={removed}"},
    )
    yield


app = FastAPI(
    title=api_settings.api_title,
    version=api_settings.api_version,
    description=(
        "HTTP API wrapping the ResearchRAG backend (OpenAlex search, PDF "
        "ingestion, hybrid RAG with streaming, semantic search, auth). "
        "All data endpoints require a bearer token."
    ),
    lifespan=lifespan,
    docs_url=api_settings.docs_url,
    redoc_url=None,
    openapi_url=api_settings.openapi_url,
)

# ── Middleware (executed bottom-up) ──────────────────────────────────────────
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.cors_origins_list,  # explicit allowlist, never "*"
    allow_credentials=False,  # bearer tokens, not cookies
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

register_exception_handlers(app)

# ── Routers — one per resource group ─────────────────────────────────────────
app.include_router(meta.router)
app.include_router(auth.router)
app.include_router(openalex.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(search.router)


@app.get("/")
def root() -> dict[str, str | None]:
    return {
        "name": api_settings.api_title,
        "version": api_settings.api_version,
        "docs": api_settings.docs_url,
        "health": "/api/health",
    }
