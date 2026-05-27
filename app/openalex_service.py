"""
OpenAlex search, ingestion, and citation network for ResearchRAG.
"""

import httpx
import time
from dataclasses import dataclass, field
from app.config import get_settings
from app.chunker import chunk_text
from app.database import get_collection, embed_texts, make_doc_id


# ─── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class OpenAlexWork:
    openalex_id:      str
    title:            str
    authors:          list[str]
    abstract:         str
    published:        str
    url:              str
    referenced_works: list[str] = field(default_factory=list)  # OpenAlex IDs
    concepts:         list[str] = field(default_factory=list)  # concept labels
    citation_count:   int = 0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decode_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""

    max_pos = -1
    for positions in inverted_index.values():
        if positions:
            max_pos = max(max_pos, max(positions))

    if max_pos < 0:
        return ""

    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            if 0 <= pos < len(words):
                words[pos] = word

    return " ".join(w for w in words if w)


def _http_get(url: str, params: dict, cfg) -> dict | None:
    """Retry-aware GET with exponential backoff."""
    for attempt in range(cfg.openalex_num_retries + 1):
        try:
            with httpx.Client(timeout=cfg.openalex_timeout_seconds) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < cfg.openalex_num_retries:
                time.sleep(cfg.openalex_backoff_seconds * (attempt + 1))
                continue
            raise
    return None


# ─── Search ───────────────────────────────────────────────────────────────────

def search_openalex(
    query: str,
    max_results: int = None,
    api_key: str | None = None,
) -> list[OpenAlexWork]:
    """Search OpenAlex and return enriched work metadata."""
    cfg = get_settings()
    n   = max_results or cfg.top_k_openalex

    params: dict = {"search": query, "per_page": n}
    key = api_key or cfg.openalex_api_key
    if key:
        params["api_key"] = key
    if cfg.openalex_mailto:
        params["mailto"] = cfg.openalex_mailto

    data = _http_get(cfg.openalex_base_url, params, cfg)
    if not data:
        return []

    works = []
    for item in data.get("results", []):
        abstract = _decode_abstract(item.get("abstract_inverted_index"))
        if not abstract:
            continue

        authors = [
            a["author"]["display_name"]
            for a in item.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]

        work_id   = item.get("id", "")
        title     = item.get("display_name", "").replace("\n", " ")
        published = item.get("publication_date") or str(item.get("publication_year") or "")

        # URL
        url = ""
        primary = item.get("primary_location") or {}
        if isinstance(primary, dict):
            url = primary.get("landing_page_url") or ""
        if not url:
            url = item.get("doi") or work_id

        # Referenced works (list of OpenAlex IDs)
        referenced = item.get("referenced_works", []) or []

        # Concepts
        concepts = [
            c["display_name"]
            for c in item.get("concepts", [])
            if c.get("score", 0) >= 0.3
        ][:5]

        # Citation count
        citation_count = item.get("cited_by_count", 0) or 0

        works.append(OpenAlexWork(
            openalex_id      = work_id,
            title            = title,
            authors          = authors[:5],
            abstract         = abstract,
            published        = published or "",
            url              = url,
            referenced_works = referenced[:30],   # cap at 30 to keep metadata size small
            concepts         = concepts,
            citation_count   = citation_count,
        ))

    return works


# ─── Ingestion ────────────────────────────────────────────────────────────────

def ingest_openalex_abstracts(
    works: list[OpenAlexWork],
    user_id: str | None = None,
) -> None:
    """Store OpenAlex abstracts (chunked) into the child ChromaDB collection."""
    collection = get_collection(user_id)
    texts, ids, metadatas = [], [], []

    for work in works:
        chunks = chunk_text(work.abstract, source=f"openalex:{work.openalex_id}")
        for chunk in chunks:
            doc_id   = make_doc_id(chunk["source"], chunk["chunk_index"])
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                continue

            texts.append(chunk["text"])
            ids.append(doc_id)
            metadatas.append({
                "chunk_role":    "child",
                "source":        "openalex",
                "openalex_id":   work.openalex_id,
                "title":         work.title,
                "authors":       ", ".join(work.authors),
                "published":     work.published,
                "url":           work.url,
                "chunk_index":   chunk["chunk_index"],
                "page_num":      1,
                "content_type":  "text",
                "section_path":  "",
                "section_title": "Abstract",
                "word_count":    len(chunk["text"].split()),
                "parent_id":     "",
                "concepts":      ", ".join(work.concepts),
                "citation_count": work.citation_count,
            })

    if texts:
        embeddings = embed_texts(texts)
        collection.add(
            documents  = texts,
            embeddings = embeddings,
            ids        = ids,
            metadatas  = metadatas,
        )
        print(f"[OpenAlex] Stored {len(texts)} new chunks from {len(works)} works")


# ─── Citation Network ─────────────────────────────────────────────────────────

def fetch_citation_network(
    work_id: str,
    api_key: str | None = None,
) -> dict[str, str]:
    """
    Fetch the referenced works for a single OpenAlex work.
    Returns {openalex_id: title} for each referenced paper.

    Parameters
    ----------
    work_id : full OpenAlex ID URL, e.g. "https://openalex.org/W2741809807"
    """
    cfg = get_settings()
    params: dict = {}
    key = api_key or cfg.openalex_api_key
    if key:
        params["api_key"] = key
    if cfg.openalex_mailto:
        params["mailto"] = cfg.openalex_mailto

    # Strip base URL if needed to get just the ID
    short_id = work_id.split("/")[-1]   # e.g. "W2741809807"
    url      = f"https://api.openalex.org/works/{short_id}"

    try:
        data = _http_get(url, params, cfg)
    except Exception:
        return {}

    if not data:
        return {}

    refs = data.get("referenced_works", []) or []
    if not refs:
        return {}

    # Batch-fetch titles for references (up to 25 at a time)
    result: dict[str, str] = {}
    batch_size = 25
    for i in range(0, min(len(refs), 50), batch_size):
        batch = refs[i : i + batch_size]
        ids_filter = "|".join(r.split("/")[-1] for r in batch)
        try:
            batch_data = _http_get(
                "https://api.openalex.org/works",
                {"filter": f"ids.openalex:{ids_filter}", "per_page": batch_size},
                cfg,
            )
            if batch_data:
                for item in batch_data.get("results", []):
                    result[item.get("id", "")] = item.get("display_name", "Unknown")
        except Exception:
            pass
        time.sleep(0.1)  # polite delay

    return result
