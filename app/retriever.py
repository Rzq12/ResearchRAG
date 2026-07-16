"""
Hybrid retrieval for ResearchRAG: BM25 keyword search fused with vector search.

Mirrors the notebook's Ensemble Retriever (BM25 weight 0.4 + vector weight 0.6)
without pulling in LangChain — fusion is Reciprocal Rank Fusion (RRF), ~30 lines.

BM25 shines on exact-match tokens that pure semantic search misses in academic
text: author names, acronyms (BERT, LoRA, FAISS), dataset names, equations.

The BM25 index is cached in memory per user and rebuilt lazily whenever the
user's child-chunk count changes (self-healing — no wiring needed at every
ingest/delete call site, though explicit invalidation is also available).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings
from app.database import get_collection

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Works for both English and Indonesian."""
    return _TOKEN_RE.findall(text.lower())


@dataclass
class _Bm25Index:
    bm25: object                # rank_bm25.BM25Okapi
    ids: list[str]
    texts: list[str]
    metadatas: list[dict]
    corpus_count: int           # child collection count when built


_bm25_cache: dict[str, _Bm25Index] = {}


def invalidate_bm25(user_id: str | None = None) -> None:
    """Drop the cached BM25 index for a user (call after ingest/delete)."""
    _bm25_cache.pop(_cache_key(user_id), None)


def _cache_key(user_id: str | None) -> str:
    return (user_id or "default").strip().lower() or "default"


def _get_bm25_index(user_id: str | None) -> _Bm25Index | None:
    """
    Return a cached (or freshly built) BM25 index over the user's child chunks.
    Returns None when BM25 is disabled, the corpus is empty, or it exceeds
    bm25_max_corpus (building would be too slow/memory-hungry).
    """
    cfg = get_settings()
    if not getattr(cfg, "enable_bm25", False):
        return None

    collection = get_collection(user_id)
    count = collection.count()
    if count == 0:
        return None
    if count > getattr(cfg, "bm25_max_corpus", 20_000):
        print(f"[BM25] corpus too large ({count} chunks) — vector-only retrieval")
        return None

    key    = _cache_key(user_id)
    cached = _bm25_cache.get(key)
    if cached is not None and cached.corpus_count == count:
        return cached

    from rank_bm25 import BM25Okapi

    results = collection.get(include=["documents", "metadatas"])
    ids     = results.get("ids", [])
    texts   = results.get("documents", []) or []
    metas   = results.get("metadatas", []) or []
    if not texts:
        return None

    index = _Bm25Index(
        bm25         = BM25Okapi([_tokenize(t) for t in texts]),
        ids          = ids,
        texts        = texts,
        metadatas    = metas,
        corpus_count = count,
    )
    _bm25_cache[key] = index
    return index


def bm25_search(query: str, user_id: str | None = None, k: int = 10) -> list[dict]:
    """
    BM25 keyword search over the user's child chunks.
    Returns candidate dicts {id, text, metadata, _score} sorted by BM25 score.
    """
    index = _get_bm25_index(user_id)
    if index is None:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = index.bm25.get_scores(tokens)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    out = []
    for i in ranked[:k]:
        if scores[i] <= 0:
            break
        out.append({
            "id":       index.ids[i],
            "text":     index.texts[i],
            "metadata": index.metadatas[i],
            "_score":   round(float(scores[i]), 4),
        })
    return out


def rrf_fuse(
    vector_candidates: list[dict],
    bm25_candidates: list[dict],
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
    rrf_k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion of two ranked candidate lists.

    Each candidate dict must have an "id" key. Fused score:
        score(d) = Σ_list  weight_list * 1 / (rrf_k + rank_in_list)

    Candidates appearing in both lists get both contributions (that's the point:
    agreement between keyword and semantic search is strong evidence).
    Returns a single deduplicated list sorted by fused score (stored in "_rrf").
    """
    fused: dict[str, dict] = {}

    for weight, candidates in ((vector_weight, vector_candidates),
                               (bm25_weight, bm25_candidates)):
        for rank, cand in enumerate(candidates, start=1):
            cid   = cand["id"]
            score = weight / (rrf_k + rank)
            if cid in fused:
                fused[cid]["_rrf"] += score
            else:
                fused[cid] = {**cand, "_rrf": score}

    out = sorted(fused.values(), key=lambda c: c["_rrf"], reverse=True)
    for c in out:
        c["_rrf"] = round(c["_rrf"], 6)
    return out
