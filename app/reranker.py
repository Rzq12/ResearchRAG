"""
Cross-encoder reranker for ResearchRAG.

Uses sentence-transformers CrossEncoder to rerank retrieved child chunks
before the parent chunks are fetched and sent to the LLM.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - Size: ~80 MB (downloaded once, cached by sentence-transformers)
  - Latency: ~50ms for 30 candidates on CPU
  - No GPU required

Enable via config: ENABLE_RERANKER=true
"""

from __future__ import annotations

_cross_encoder = None


def _get_cross_encoder(model_name: str):
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        print(f"[Reranker] Loading {model_name}...")
        _cross_encoder = CrossEncoder(model_name)
    return _cross_encoder


def rerank(
    query: str,
    chunks: list[dict],
    model_name: str,
    top_k: int,
) -> list[dict]:
    """
    Rerank a list of chunk dicts using a cross-encoder.

    Parameters
    ----------
    query      : the user's question
    chunks     : list of dicts, each must have a "text" key
    model_name : cross-encoder model identifier
    top_k      : how many top results to return

    Returns
    -------
    Reranked and truncated list of chunk dicts, highest score first.
    Each dict gets a new "_rerank_score" key.
    """
    if not chunks:
        return []

    encoder = _get_cross_encoder(model_name)

    pairs  = [(query, c["text"]) for c in chunks]
    scores = encoder.predict(pairs).tolist()

    for chunk, score in zip(chunks, scores):
        chunk["_rerank_score"] = round(float(score), 4)

    ranked = sorted(chunks, key=lambda c: c["_rerank_score"], reverse=True)
    return ranked[:top_k]
