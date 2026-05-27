"""
PDF ingestion service for ResearchRAG.
Uses the advanced chunker pipeline (hierarchical + layout-aware + parent-child).
"""

from app.chunker import extract_pdf_chunks_advanced, CoverageReport
from app.database import (
    get_collection, get_parent_collection,
    embed_texts, make_doc_id,
)


def ingest_pdf(
    pdf_bytes: bytes,
    filename: str,
    user_id: str | None = None,
) -> dict:
    """
    Ingest a user-uploaded PDF into ChromaDB (child + parent collections).
    Returns a summary dict including the CoverageReport.
    """
    child_col  = get_collection(user_id)
    parent_col = get_parent_collection(user_id)

    children, parents, report = extract_pdf_chunks_advanced(pdf_bytes, filename)

    if not children:
        return {
            "filename":      filename,
            "chunks_added":  0,
            "message":       "No text extracted",
            "coverage":      None,
        }

    title = filename.replace(".pdf", "")

    # ── Ingest child chunks ────────────────────────────────────────────────
    child_texts, child_ids, child_metas = [], [], []

    for chunk in children:
        doc_id   = chunk.chunk_id
        existing = child_col.get(ids=[doc_id])
        if existing["ids"]:
            continue

        meta = chunk.to_metadata()
        meta["title"]  = title
        meta["source"] = "upload"

        child_texts.append(chunk.text)
        child_ids.append(doc_id)
        child_metas.append(meta)

    if child_texts:
        embeddings = embed_texts(child_texts)
        child_col.add(
            documents  = child_texts,
            embeddings = embeddings,
            ids        = child_ids,
            metadatas  = child_metas,
        )

    # ── Ingest parent chunks (no embedding needed — looked up by ID) ───────
    parent_texts, parent_ids, parent_metas = [], [], []

    for chunk in parents:
        doc_id   = chunk.chunk_id
        existing = parent_col.get(ids=[doc_id])
        if existing["ids"]:
            continue

        meta = chunk.to_metadata()
        meta["title"]  = title
        meta["source"] = "upload"

        parent_texts.append(chunk.text)
        parent_ids.append(doc_id)
        parent_metas.append(meta)

    if parent_texts:
        # Parents MUST be stored with embeddings — ChromaDB collection has no
        # default embedding function configured, so explicit embeddings are required.
        # Parent chunks are looked up by ID (not by similarity), but storage still
        # requires embeddings to avoid ChromaDB ValueError.
        parent_embeddings = embed_texts(parent_texts)
        parent_col.add(
            documents  = parent_texts,
            embeddings = parent_embeddings,
            ids        = parent_ids,
            metadatas  = parent_metas,
        )

    return {
        "filename":      filename,
        "total_children": len(children),
        "chunks_added":  len(child_texts),
        "chunks_skipped": len(children) - len(child_texts),
        "parents_added": len(parent_texts),
        "coverage":      report,
    }


def list_uploaded_docs(user_id: str | None = None) -> list[dict]:
    """List all documents in ChromaDB (child collection) with their metadata."""
    collection = get_collection(user_id)
    results    = collection.get(include=["metadatas"])

    seen = set()
    docs = []
    for meta in results["metadatas"]:
        key = meta.get("openalex_id") or meta.get("filename") or meta.get("title", "unknown")
        if key not in seen:
            seen.add(key)
            docs.append({
                "title":    meta.get("title", key),
                "source":   meta.get("source", "unknown"),
                "authors":  meta.get("authors", ""),
                "published": meta.get("published", ""),
                "url":      meta.get("url", ""),
            })
    return docs


def delete_document(title: str, user_id: str | None = None) -> int:
    """Delete all child + parent chunks for a given document title."""
    child_col  = get_collection(user_id)
    parent_col = get_parent_collection(user_id)
    total = 0

    for col in (child_col, parent_col):
        results = col.get(include=["metadatas"])
        ids_to_delete = [
            results["ids"][i]
            for i, meta in enumerate(results["metadatas"])
            if meta.get("title") == title or meta.get("filename") == title
        ]
        if ids_to_delete:
            col.delete(ids=ids_to_delete)
            total += len(ids_to_delete)

    return total
