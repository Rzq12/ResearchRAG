"""
Relevance fallback for ResearchRAG.

When the reranker's top-1 score falls below cfg.relevance_threshold, the local
knowledge base is judged not relevant enough and the answer context comes from
live sources instead — same if-else pattern as the notebook, with one domain
adaptation: OpenAlex (250M papers, already integrated) is tried before
DuckDuckGo, which is only the last resort.

Every fallback context is labelled so the UI can tell the user the answer did
NOT come from their own knowledge base.
"""

from __future__ import annotations

from app.config import get_settings


def openalex_fallback(query: str, max_results: int) -> tuple[str, list[dict]]:
    """
    Live OpenAlex search → context blocks + reference dicts.
    Returns ("", []) when nothing is found or the API fails.
    """
    try:
        from app.openalex_service import search_openalex
        works = search_openalex(query, max_results=max_results)
    except Exception as exc:
        print(f"[fallback] OpenAlex failed: {exc}")
        return "", []

    blocks, refs = [], []
    for i, work in enumerate(works, start=1):
        blocks.append(f"[{i}] {work.title} ({work.published})\n{work.abstract}")
        refs.append({
            "title":     work.title,
            "authors":   ", ".join(work.authors),
            "published": work.published,
            "url":       work.url,
            "source":    "openalex-live",
        })
    return "\n\n".join(blocks), refs


def duckduckgo_fallback(query: str, max_results: int) -> tuple[str, list[dict]]:
    """
    DuckDuckGo web search → context blocks + reference dicts.
    Returns ("", []) when nothing is found or the search fails.
    """
    try:
        from ddgs import DDGS
        results = list(DDGS().text(query, max_results=max_results))
    except Exception as exc:
        print(f"[fallback] DuckDuckGo failed: {exc}")
        return "", []

    blocks, refs = [], []
    for i, r in enumerate(results, start=1):
        title = r.get("title", "")
        body  = r.get("body", "")
        if not body:
            continue
        blocks.append(f"[{i}] {title}\n{body}")
        refs.append({
            "title":     title,
            "authors":   "",
            "published": "",
            "url":       r.get("href", ""),
            "source":    "web",
        })
    return "\n\n".join(blocks), refs


def fallback_context(query: str) -> tuple[str, list[dict], str]:
    """
    Build answer context from live sources when the local KB is not relevant.

    Order: OpenAlex → DuckDuckGo → empty.
    Returns (context, refs, source_note). An empty context means both sources
    failed and the caller must answer honestly that nothing relevant was found.
    """
    cfg = get_settings()
    n   = getattr(cfg, "fallback_max_results", 3)

    context, refs = openalex_fallback(query, n)
    if context:
        return context, refs, "openalex-live"

    context, refs = duckduckgo_fallback(query, n)
    if context:
        return context, refs, "web"

    return "", [], "none"
