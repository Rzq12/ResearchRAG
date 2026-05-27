import httpx
from dataclasses import dataclass
from app.config import get_settings
from app.chunker import chunk_text
from app.database import get_collection, embed_texts, make_doc_id


@dataclass
class OpenAlexWork:
    openalex_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    url: str


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


def search_openalex(query: str, max_results: int = None, api_key: str | None = None) -> list[OpenAlexWork]:
    """Search OpenAlex and return work metadata."""
    cfg = get_settings()
    n = max_results or cfg.top_k_openalex

    params = {
        "search": query,
        "per_page": n,
    }

    key = api_key or cfg.openalex_api_key
    if key:
        params["api_key"] = key

    if cfg.openalex_mailto:
        params["mailto"] = cfg.openalex_mailto

    with httpx.Client(timeout=30) as client:
        resp = client.get(cfg.openalex_base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    works = []
    for item in data.get("results", []):
        abstract = _decode_abstract(item.get("abstract_inverted_index"))
        if not abstract:
            continue

        authors = []
        for a in item.get("authorships", []):
            author = a.get("author", {})
            name = author.get("display_name")
            if name:
                authors.append(name)

        work_id = item.get("id", "")
        title = item.get("display_name", "").replace("\n", " ")
        published = item.get("publication_date") or str(item.get("publication_year") or "")

        url = ""
        primary = item.get("primary_location") or {}
        if isinstance(primary, dict):
            url = primary.get("landing_page_url") or ""
        if not url:
            url = item.get("doi") or work_id

        works.append(OpenAlexWork(
            openalex_id=work_id,
            title=title,
            authors=authors[:5],
            abstract=abstract,
            published=published or "",
            url=url,
        ))

    return works


def ingest_openalex_abstracts(works: list[OpenAlexWork]):
    """Store OpenAlex abstracts into ChromaDB for retrieval."""
    collection = get_collection()

    texts, ids, metadatas = [], [], []

    for work in works:
        chunks = chunk_text(work.abstract, source=f"openalex:{work.openalex_id}")
        for chunk in chunks:
            doc_id = make_doc_id(chunk["source"], chunk["chunk_index"])

            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                continue

            texts.append(chunk["text"])
            ids.append(doc_id)
            metadatas.append({
                "source": "openalex",
                "openalex_id": work.openalex_id,
                "title": work.title,
                "authors": ", ".join(work.authors),
                "published": work.published,
                "url": work.url,
                "chunk_index": chunk["chunk_index"],
            })

    if texts:
        embeddings = embed_texts(texts)
        collection.add(documents=texts, embeddings=embeddings,
                       ids=ids, metadatas=metadatas)
        print(f"[OpenAlex] Stored {len(texts)} new chunks from {len(works)} works")
