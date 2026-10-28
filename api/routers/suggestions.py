"""
Question suggestions: starter questions grounded in the user's knowledge base,
and follow-up questions after an answer.

Unlike the legacy ``/api/openalex/suggestions`` (which fails soft to an empty
list), these endpoints report LLM failures, so the client can show why nothing
came back instead of silently rendering no chips.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.llm_client import friendly_llm_error
from app.rag import generate_followup_questions, suggest_questions_from_kb

from api.rate_limit import limiter
from api.schemas import FollowupsRequest, KbSuggestionsRequest, SuggestionsResponse
from api.security import current_user

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


def _upstream_error(exc: Exception) -> HTTPException:
    """Map a provider failure to a 502 carrying the friendly message's headline."""
    _, message = friendly_llm_error(exc)
    headline = message.split("\n", 1)[0].replace("**", "").strip()
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=headline)


@router.post("", response_model=SuggestionsResponse)
@limiter.limit("20/minute")
def kb_suggestions(
    request: Request,
    body: KbSuggestionsRequest,
    user_id: str = Depends(current_user),
) -> SuggestionsResponse:
    """Suggest research questions from the text of the user's ingested documents."""
    try:
        questions = suggest_questions_from_kb(
            user_id,
            api_key=body.api_key or None,
            model=body.model,
            base_url=body.base_url,
            titles=body.titles,
            n=body.n,
            language=body.language,
            exclude=body.exclude,
        )
    except Exception as exc:
        raise _upstream_error(exc) from exc
    return SuggestionsResponse(suggestions=questions)


@router.post("/followups", response_model=SuggestionsResponse)
@limiter.limit("30/minute")
def followups(
    request: Request,
    body: FollowupsRequest,
    user_id: str = Depends(current_user),
) -> SuggestionsResponse:
    """Suggest follow-up questions for a finished answer."""
    try:
        questions = generate_followup_questions(
            body.question,
            body.answer,
            api_key=body.api_key or None,
            model=body.model,
            base_url=body.base_url,
            n=body.n,
            language=body.language,
        )
    except Exception as exc:
        raise _upstream_error(exc) from exc
    return SuggestionsResponse(suggestions=questions)
