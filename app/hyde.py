"""
HyDE — Hypothetical Document Embeddings — for ResearchRAG.

Mirrors the notebook pattern: the LLM writes n (default 2) short hypothetical
abstract paragraphs that would answer the research question; those paragraphs
are then embedded and used as additional retrieval queries alongside the
original question.

Domain adaptation vs the notebook (which generated fake legal clauses):
the hypothetical here is an academic-abstract paragraph, and it MUST be in the
same language as the question — a hypothetical in the wrong language shifts
the embedding away from the right documents and makes retrieval worse.

Costs n extra LLM calls per query. Gate behind cfg.enable_hyde, and never use
in semantic_search (which is LLM-free by design).
"""

from __future__ import annotations

from app.config import get_settings
from app.llm_client import call_llm

_HYDE_SYSTEM = (
    "You write hypothetical academic abstract passages for search purposes. "
    "Given a research question, write ONE paragraph (2-3 sentences) that would "
    "plausibly appear in a paper answering it. "
    "Write in the SAME LANGUAGE as the question. "
    "Academic register. No preamble, no citations, no lists — just the paragraph."
)


def generate_hypotheticals(
    question: str,
    api_key: str,
    model: str,
    n: int | None = None,
) -> list[str]:
    """
    Generate n hypothetical abstract paragraphs for the question.

    Fails soft: any LLM error just yields fewer (possibly zero) hypotheticals,
    so retrieval degrades to plain vector search instead of crashing.
    """
    cfg = get_settings()
    n   = n or getattr(cfg, "hyde_num_hypotheticals", 2)

    hypotheticals: list[str] = []
    for _ in range(n):
        try:
            text = call_llm(
                model       = model,
                messages    = [
                    {"role": "system", "content": _HYDE_SYSTEM},
                    {"role": "user",   "content": question},
                ],
                api_key     = api_key,
                max_tokens  = getattr(cfg, "hyde_max_tokens", 150),
                temperature = getattr(cfg, "hyde_temperature", 0.9),
            )
        except Exception as exc:
            print(f"[HyDE] generation failed, skipping: {exc}")
            continue
        text = (text or "").strip()
        if text:
            hypotheticals.append(text)

    return hypotheticals
