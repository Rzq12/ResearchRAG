"""
Cross-encoder reranker for ResearchRAG.

Re-scores retrieval candidates against the ORIGINAL query before parent
chunks are fetched and sent to the LLM.

Model: BAAI/bge-reranker-base (multilingual, XLM-R based) — handles the
Indonesian/English/code-switching queries this app serves. Raw logits are
sigmoid-normalized to [0,1] so the top-1 score can be compared against
cfg.relevance_threshold (the notebook pattern: threshold → web fallback).

Enable via config: ENABLE_RERANKER=true (default on).
"""

from __future__ import annotations

from app.logger import logger
import math
import threading

_cross_encoders: dict[str, object] = {}
# Under Streamlit this init was effectively serialised. FastAPI runs every sync
# handler in a 40-slot threadpool, so N concurrent first-requests each saw an
# empty dict and each loaded its own ~500 MB CrossEncoder — OOM in a 2 GB
# container. Double-checked locking makes exactly one load win.
_cross_encoder_lock = threading.Lock()


def _get_cross_encoder(model_name: str):
    model = _cross_encoders.get(model_name)
    if model is None:
        with _cross_encoder_lock:
            model = _cross_encoders.get(model_name)
            if model is None:
                from sentence_transformers import CrossEncoder
                logger.info("reranker_loading model=%s", model_name)
                model = CrossEncoder(model_name, max_length=512)
                _cross_encoders[model_name] = model
    return model


def warm_reranker(model_name: str) -> None:
    """Load the cross-encoder at startup so no request pays for it mid-flight."""
    _get_cross_encoder(model_name)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


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
    Each dict gets a new "_rerank_score" key, sigmoid-normalized to [0,1].
    """
    if not chunks:
        return []

    encoder = _get_cross_encoder(model_name)

    pairs  = [(query, c["text"]) for c in chunks]
    logits = encoder.predict(pairs).tolist()

    for chunk, logit in zip(chunks, logits):
        chunk["_rerank_score"] = round(_sigmoid(float(logit)), 4)

    ranked = sorted(chunks, key=lambda c: c["_rerank_score"], reverse=True)
    return ranked[:top_k]
