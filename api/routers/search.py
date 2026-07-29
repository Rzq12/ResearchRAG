"""
Semantic search endpoint — direct vector search over the knowledge base with
no LLM involved. Thin wrapper over ``app.semantic_search.semantic_search``.

Scoped to the authenticated user's collection.
"""

from fastapi import APIRouter, Depends, Request

from app.semantic_search import semantic_search

from api.rate_limit import limiter
from api.schemas import (
    SemanticHit,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from api.security import current_user

router = APIRouter(prefix="/api/semantic-search", tags=["search"])


@router.post("", response_model=SemanticSearchResponse)
@limiter.limit("30/minute")
def search(
    request: Request,
    body: SemanticSearchRequest,
    user_id: str = Depends(current_user),
) -> SemanticSearchResponse:
    hits = semantic_search(
        query=body.query,
        user_id=user_id,
        top_k=body.top_k,
        content_type_filter=body.content_type_filter,
        min_score=body.min_score,
    )
    return SemanticSearchResponse(results=[SemanticHit(**h) for h in hits])
