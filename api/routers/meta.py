"""
Meta endpoints: health check + config/model catalog.

Exposes the same model list the Streamlit sidebar builds from
``app.llm_client.MODEL_CATALOG`` / ``PROVIDER_HINTS``, including the optional
self-hosted ``hf:`` model when it is configured in the environment.
"""

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.llm_client import MODEL_CATALOG, PROVIDER_HINTS, get_provider
from app.topic_classifier import RESEARCH_TOPICS

from api.schemas import ConfigResponse, ModelInfo

router = APIRouter(tags=["meta"])


@router.get("/api/health")
def health() -> dict[str, str]:
    """Liveness — process is up. Cheap enough for a container HEALTHCHECK."""
    return {"status": "ok"}


@router.get("/api/ready")
def ready() -> dict[str, object]:
    """
    Readiness — dependencies actually answer.

    Distinct from liveness: the process can be alive while ChromaDB or the
    embedding model is not yet usable, and an orchestrator should not send
    traffic during that window.
    """
    checks: dict[str, bool] = {}
    try:
        from app.database import get_collection

        get_collection(None).count()
        checks["vector_store"] = True
    except Exception:
        checks["vector_store"] = False

    try:
        from app.auth import _conn

        with _conn() as db:
            db.execute("SELECT 1").fetchone()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    ok = all(checks.values())
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Not ready: {checks}",
        )
    return {"status": "ready", "checks": checks}


@router.get("/api/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    """Return model catalog + a few settings the frontend needs to render."""
    cfg = get_settings()

    models: list[ModelInfo] = []
    for model_id, (label, provider) in MODEL_CATALOG.items():
        icon, text = PROVIDER_HINTS.get(model_id, ("", ""))
        models.append(
            ModelInfo(
                id=model_id,
                label=label,
                provider=provider,  # type: ignore[arg-type]
                hint_icon=icon,
                hint_text=text,
            )
        )

    # Self-hosted fine-tuned model — only surfaced when configured (mirrors the
    # Streamlit sidebar behaviour).
    if cfg.hf_endpoint_url and cfg.hf_model_name:
        hf_id = f"hf:{cfg.hf_model_name}"
        models.append(
            ModelInfo(
                id=hf_id,
                label=f"🏠 {cfg.hf_model_name} (self-hosted)",
                provider="hf",
                hint_icon="🏠",
                hint_text="Self-hosted endpoint",
            )
        )

    default_model = cfg.default_model
    if get_provider(default_model) not in ("groq", "gemini", "hf"):
        default_model = next(iter(MODEL_CATALOG))

    return ConfigResponse(
        models=models,
        default_model=default_model,
        require_user_id=cfg.require_user_id,
        max_upload_mb=cfg.max_upload_mb,
        research_topics=list(RESEARCH_TOPICS),
    )
