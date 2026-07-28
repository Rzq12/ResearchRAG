"""
ResearchRAG FastAPI application.

A thin HTTP wrapper around the existing ``app/`` backend so a React frontend
can use every feature the Streamlit app has. Run with:

    uvicorn api.main:app --host 0.0.0.0 --port 8000

The Streamlit app (``streamlit_app.py``) is unaffected and can keep running
independently.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import init_auth_db
from app.database import init_chroma

from api.settings import get_api_settings
from api.routers import auth, chat, documents, meta, openalex, search

logger = logging.getLogger("researchrag.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Same startup work the Streamlit app performs in its cached startup().
    init_chroma()
    init_auth_db()
    logger.info("ResearchRAG API ready")
    yield


api_settings = get_api_settings()

app = FastAPI(
    title=api_settings.api_title,
    version=api_settings.api_version,
    description=(
        "HTTP API wrapping the ResearchRAG backend (OpenAlex search, PDF "
        "ingestion, hybrid RAG with streaming, semantic search, auth). "
        "The Streamlit app remains the reference implementation."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.cors_origins_list,
    allow_credentials=False,  # we pass user_id explicitly, no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — one per resource group.
app.include_router(meta.router)
app.include_router(auth.router)
app.include_router(openalex.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(search.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": api_settings.api_title,
        "version": api_settings.api_version,
        "docs": "/docs",
        "health": "/api/health",
    }
