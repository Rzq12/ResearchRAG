"""
API-layer configuration.

Only concerns the HTTP wrapper itself (CORS, docs). All RAG/model/embedding
configuration continues to live in ``app.config.Settings`` and is read from
there — this module never duplicates it.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    """Settings specific to the FastAPI wrapper (read from the same .env)."""

    # Comma-separated list of allowed browser origins for CORS.
    # In production set this to your Vercel URL, e.g.
    #   CORS_ORIGINS=https://research-rag.vercel.app,https://researchrag.vercel.app
    # Default "*" is convenient for local development.
    cors_origins: str = "*"

    # Human-friendly title shown in the auto-generated OpenAPI docs.
    api_title: str = "ResearchRAG API"
    api_version: str = "1.0.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
