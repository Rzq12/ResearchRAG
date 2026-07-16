"""
Semantic search panel — search the knowledge base without calling the LLM.
Useful for debugging retrieval quality and exploring document chunks.
"""

from __future__ import annotations

from app.database import get_collection, embed_query


def semantic_search(
    query: str,
    user_id: str | None = None,
    top_k: int = 20,
    content_type_filter: str | None = None,
    min_score: float = 0.0,
) -> list[dict]:
    """
    Perform vector similarity search against the knowledge base.
    Returns raw chunks with scores — no LLM involved.

    Parameters
    ----------
    query               : search string
    user_id             : scopes to user's collection
    top_k               : max results to return
    content_type_filter : e.g. "table", "formula", "heading" — filters by metadata
    min_score           : minimum cosine similarity (0.0 = no filter)

    Returns
    -------
    list of dicts:
        text, score, page_num, content_type, section_title,
        source, title, chunk_index, parent_id
    """
    collection = get_collection(user_id)
    count      = collection.count()
    if count == 0:
        return []

    k = min(top_k, count)

    # Build where filter
    where = None
    if content_type_filter:
        where = {"content_type": content_type_filter}

    query_emb = embed_query(query)

    try:
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=k,
            include=["documents", "metadatas", "distances"],
            where=where,
        )
    except Exception:
        # Fallback without filter if filter fails (e.g. old chunks have no content_type)
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, distances):
        score = round(1 - dist, 4)
        if score < min_score:
            continue
        hits.append({
            "text":          doc,
            "score":         score,
            "page_num":      meta.get("page_num", "?"),
            "content_type":  meta.get("content_type", "text"),
            "section_title": meta.get("section_title", ""),
            "section_path":  meta.get("section_path", ""),
            "source":        meta.get("source", ""),
            "title":         meta.get("title", ""),
            "chunk_index":   meta.get("chunk_index", 0),
            "parent_id":     meta.get("parent_id", ""),
            "chunk_role":    meta.get("chunk_role", "child"),
        })

    return sorted(hits, key=lambda h: h["score"], reverse=True)
