"""
API-layer configuration.

Only concerns the HTTP wrapper itself (auth, CORS, docs, limits). All
RAG/model/embedding configuration continues to live in ``app.config.Settings``
and is read from there — this module never duplicates it.

Fails closed: in a non-development environment the app refuses to start without
an explicit JWT secret and CORS allowlist, rather than silently using insecure
defaults.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings

Environment = Literal["development", "staging", "production"]


class ConfigurationError(RuntimeError):
    """Raised at startup when required production settings are missing."""


class ApiSettings(BaseSettings):
    """Settings specific to the FastAPI wrapper (read from the same .env)."""

    # Which environment we are running in. Anything other than "development"
    # enforces the production guardrails below.
    environment: Environment = "development"

    # ── Auth ─────────────────────────────────────────────────────────────────
    # MUST be set outside development. Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str = ""
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated browser origins. Wildcard is never permitted: this API is
    # state-changing (it can delete a user's whole library).
    #   CORS_ORIGINS=https://research-rag.vercel.app,https://researchrag.vercel.app
    cors_origins: str = ""

    # ── Docs ─────────────────────────────────────────────────────────────────
    # /docs advertises the full attack surface; off by default in production.
    expose_docs: bool = False

    api_title: str = "ResearchRAG API"
    api_version: str = "1.0.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    # ── Derived ──────────────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.environment != "development"

    @property
    def cors_origins_list(self) -> list[str]:
        """Explicit origin allowlist. Never returns ``*``."""
        origins = [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]
        origins = [o for o in origins if o != "*"]
        if origins:
            return origins
        if self.is_production:
            raise ConfigurationError(
                "CORS_ORIGINS must list explicit https origins in "
                f"{self.environment} (wildcards are rejected)."
            )
        # Development convenience only — the local Vite dev server.
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def docs_url(self) -> str | None:
        return "/docs" if (self.expose_docs or not self.is_production) else None

    @property
    def openapi_url(self) -> str | None:
        return "/openapi.json" if (self.expose_docs or not self.is_production) else None

    def validate_runtime(self) -> None:
        """
        Fail fast on missing production configuration.

        Called once at startup. In development a random secret is generated so
        local work needs no setup — but that secret dies with the process, which
        is exactly why it must never be relied on in production.
        """
        if self.is_production:
            if not self.jwt_secret or len(self.jwt_secret) < 32:
                raise ConfigurationError(
                    "JWT_SECRET must be set to at least 32 characters in "
                    f"{self.environment}. Generate one with: "
                    'python -c "import secrets; print(secrets.token_urlsafe(48))"'
                )
            self.cors_origins_list  # raises when unset
        elif not self.jwt_secret:
            object.__setattr__(self, "jwt_secret", secrets.token_urlsafe(48))


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
