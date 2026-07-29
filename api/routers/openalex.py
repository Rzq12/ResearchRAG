"""
OpenAlex endpoints: search, ingest (abstracts / full-text / both), citation
network, topic classification, and query suggestions.

All heavy work (HTTP to OpenAlex, embedding, PDF download) runs in Starlette's
threadpool because these handlers are declared ``def`` (not ``async def``).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.openalex_service import (
    OpenAlexWork,
    fetch_citation_network,
    ingest_openalex_abstracts,
    search_openalex,
)
from app.fulltext_service import fetch_fulltext_batch
from app.rag import generate_query_suggestions
from app.topic_classifier import classify_topics_batch

from api.schemas import (
    CitationsRequest,
    CitationsResponse,
    FulltextSummary,
    IngestOpenAlexRequest,
    IngestOpenAlexResponse,
    OpenAlexWorkModel,
    SearchRequest,
    SearchResponse,
    SuggestionsRequest,
    SuggestionsResponse,
    TopicsRequest,
    TopicsResponse,
)
from api.rate_limit import limiter
from api.security import current_user
from api.serialize import work_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/openalex", tags=["openalex"])


def _to_work(model: OpenAlexWorkModel) -> OpenAlexWork:
    """Rebuild a backend dataclass from the wire model (for ingest calls)."""
    return OpenAlexWork(
        openalex_id=model.openalex_id,
        title=model.title,
        authors=list(model.authors),
        abstract=model.abstract,
        published=model.published,
        url=model.url,
        referenced_works=list(model.referenced_works),
        concepts=list(model.concepts),
        citation_count=model.citation_count,
    )


@router.post("/search", response_model=SearchResponse)
@limiter.limit("30/minute")
def search(
    request: Request,
    body: SearchRequest,
    user_id: str = Depends(current_user),
) -> SearchResponse:
    """Search OpenAlex and return enriched work metadata (no ingestion)."""
    try:
        works = search_openalex(
            body.query,
            max_results=body.max_results,
            api_key=body.api_key,
        )
    except Exception as exc:
        # NEVER interpolate the upstream exception. httpx renders the full
        # request URL in its message, and app.openalex_service sends the API key
        # as a query parameter — which defaults to the SERVER's key when the
        # caller omits one. `detail=f"...{exc}"` handed that credential to any
        # authenticated user who could provoke a 4xx (e.g. an oversized
        # max_results, now bounded in api/schemas.py).
        logger.warning("openalex_search_failed", exc_info=exc)
        raise HTTPException(status_code=502, detail="OpenAlex request failed.") from exc
    return SearchResponse(works=[OpenAlexWorkModel(**work_to_dict(w)) for w in works])


@router.post("/ingest", response_model=IngestOpenAlexResponse)
@limiter.limit("10/minute")
def ingest(
    request: Request,
    body: IngestOpenAlexRequest,
    user_id: str = Depends(current_user),
) -> IngestOpenAlexResponse:
    """Ingest previously-searched works into the user's knowledge base."""
    works = [_to_work(w) for w in body.works]
    if not works:
        return IngestOpenAlexResponse(abstracts_ingested=0, fulltext=None)

    abstracts_ingested = 0
    fulltext: FulltextSummary | None = None

    if body.mode in ("abstracts", "both"):
        ingest_openalex_abstracts(works, user_id=user_id)
        abstracts_ingested = len(works)

    if body.mode in ("fulltext", "both"):
        result = fetch_fulltext_batch(works, user_id=user_id)
        fulltext = FulltextSummary(**result)

    return IngestOpenAlexResponse(
        abstracts_ingested=abstracts_ingested,
        fulltext=fulltext,
    )


@router.post("/citations", response_model=CitationsResponse)
@limiter.limit("30/minute")
def citations(
    request: Request,
    body: CitationsRequest,
    user_id: str = Depends(current_user),
) -> CitationsResponse:
    """Fetch the reference network ({openalex_id: title}) for one work."""
    refs = fetch_citation_network(body.openalex_id, api_key=body.api_key)
    return CitationsResponse(references=refs or {})


@router.post("/topics", response_model=TopicsResponse)
@limiter.limit("20/minute")
def topics(
    request: Request,
    body: TopicsRequest,
    user_id: str = Depends(current_user),
) -> TopicsResponse:
    """Classify works into research topics via the Groq LLM."""
    works = [_to_work(w) for w in body.works]
    model = body.model or "llama-3.3-70b-versatile"
    labels = classify_topics_batch(works, groq_api_key=body.groq_api_key, groq_model=model)
    return TopicsResponse(labels=labels)


@router.post("/suggestions", response_model=SuggestionsResponse)
@limiter.limit("20/minute")
def suggestions(
    request: Request,
    body: SuggestionsRequest,
    user_id: str = Depends(current_user),
) -> SuggestionsResponse:
    """Generate follow-up research questions from ingested works or titles."""
    if body.works:
        works_or_titles: list = [_to_work(w) for w in body.works]
    else:
        works_or_titles = list(body.titles or [])

    if not works_or_titles:
        return SuggestionsResponse(suggestions=[])

    result = generate_query_suggestions(
        works_or_titles,
        api_key=body.api_key,
        model=body.model,
        n=body.n,
    )
    return SuggestionsResponse(suggestions=result)
