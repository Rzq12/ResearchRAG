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

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.llm_client import friendly_llm_error
from app.rag import ask_stream

from api.schemas import ChatRequest
from api.serialize import reference_to_dict

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_stream(body: ChatRequest) -> Iterator[str]:
    history = [{"role": m.role, "content": m.content} for m in body.chat_history]

    try:
        gen, refs, oa_count, up_count, think_holder, source = ask_stream(
            body.query,
            chat_history=history,
            api_key=body.api_key,
            model=body.model,
            user_id=body.user_id,
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

    # think_holder is only populated once the generator is fully consumed.
    reasoning = ""
    try:
        reasoning = think_holder.get("think", "") if think_holder else ""
    except Exception:
        reasoning = ""

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


@router.post("/stream")
def chat_stream(body: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering so tokens flush immediately (nginx/HF).
            "X-Accel-Buffering": "no",
        },
    )
