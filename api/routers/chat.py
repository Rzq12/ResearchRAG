"""
Streaming chat endpoint.

Wraps ``app.rag.ask_stream`` and re-emits its output as Server-Sent Events so
the React client can render tokens as they arrive — the same token-by-token UX
as ``st.write_stream`` in the Streamlit app.

Event protocol (``text/event-stream``):
    event: token   data: {"text": "..."}       # zero or more, in order
    event: meta    data: {references, openalex_used, uploaded_used,
                          reasoning, source}     # once, after the last token
    event: error   data: {"category": "...", "message": "..."}  # on failure
    event: done    data: {}                      # always last
"""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.llm_client import friendly_llm_error
from app.rag import ask_stream

from api.rate_limit import limiter
from api.schemas import ChatRequest
from api.security import current_user
from api.serialize import reference_to_dict

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_stream(body: ChatRequest, user_id: str) -> Iterator[str]:
    history = [{"role": m.role, "content": m.content} for m in body.chat_history]

    try:
        gen, refs, oa_count, up_count, think_holder, source = ask_stream(
            body.query,
            chat_history=history,
            api_key=body.api_key,
            model=body.model,
            user_id=user_id,
            where=body.where,
            kb_only=body.kb_only,
        )
    except Exception as exc:  # setup/retrieval failure (e.g. missing key)
        category, message = friendly_llm_error(exc)
        yield _sse("error", {"category": category, "message": message})
        yield _sse("done", {})
        return

    try:
        for chunk in gen:
            if chunk:
                yield _sse("token", {"text": chunk})
    except Exception as exc:  # LLM error mid-stream
        category, message = friendly_llm_error(exc)
        yield _sse("error", {"category": category, "message": message})
        yield _sse("done", {})
        return
    finally:
        # A client that navigates away abandons this generator. Starlette drives
        # it through iterate_in_threadpool, so cancellation cannot interrupt the
        # in-flight next() — without an explicit close() the upstream LLM
        # connection was only released whenever GC got round to it, and enough
        # abandoned streams drained the threadpool.
        close = getattr(gen, "close", None)
        if close is not None:
            close()

    # think_holder is only populated once the generator is fully consumed.
    reasoning = think_holder.get("think", "") if think_holder else ""

    yield _sse(
        "meta",
        {
            "references": [reference_to_dict(r) for r in refs],
            "openalex_used": oa_count,
            "uploaded_used": up_count,
            "reasoning": reasoning,
            "source": source,
        },
    )
    yield _sse("done", {})


@router.post("/stream", response_class=StreamingResponse)
@limiter.limit("20/minute")
def chat_stream(
    request: Request,
    body: ChatRequest,
    user_id: str = Depends(current_user),
):
    # No return annotation: this module uses postponed annotations and slowapi
    # wraps the handler, so FastAPI cannot resolve `StreamingResponse` from the
    # wrapper's globals. `response_class` conveys the same thing to OpenAPI.
    return StreamingResponse(
        _event_stream(body, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering so tokens flush immediately (nginx/HF).
            "X-Accel-Buffering": "no",
        },
    )
