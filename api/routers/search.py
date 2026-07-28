"""
Semantic search endpoint — direct vector search over the knowledge base with
no LLM involved. Thin wrapper over ``app.semantic_search.semantic_search``.
"""

from fastapi import APIRouter

from app.semantic_search import semantic_search

from api.schemas import (
    SemanticHit,
    SemanticSearchRequest,
    SemanticSearchResponse,
)

router = APIRouter(prefix="/api/semantic-search", tags=["search"])


@router.post("", response_model=SemanticSearchResponse)
def search(body: SemanticSearchRequest) -> SemanticSearchResponse:
    hits = semantic_search(
        query=body.query,
        user_id=body.user_id,
        top_k=body.top_k,
        content_type_filter=body.content_type_filter,
        min_score=body.min_score,
    )
    return SemanticSearchResponse(results=[SemanticHit(**h) for h in hits])
