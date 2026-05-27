"""
ChromaDB client + embedding singleton for ResearchRAG.

Collections per user:
  {name}_{hash}         → child chunks (small, embedded, searched)
  {name}_{hash}_parent  → parent chunks (large, LLM context, looked up by ID)
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from app.config import get_settings
import hashlib

_client      = None
_collections: dict[str, chromadb.Collection] = {}
_embedder    = None


# ─── Embedder ─────────────────────────────────────────────────────────────────

def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        cfg = get_settings()
        print(f"[Embedder] Loading {cfg.embedding_model}...")
        _embedder = SentenceTransformer(cfg.embedding_model)
    return _embedder


# ─── Collection naming ────────────────────────────────────────────────────────

def _normalize_user_id(user_id: str | None) -> str:
    if not user_id:
        return "default"
    return user_id.strip().lower() or "default"


def _collection_name(user_id: str | None, role: str = "child") -> str:
    cfg        = get_settings()
    normalized = _normalize_user_id(user_id)
    if normalized == "default":
        base = cfg.chroma_collection
    else:
        suffix = hashlib.md5(normalized.encode()).hexdigest()[:12]
        base   = f"{cfg.chroma_collection}_{suffix}"
    if role == "parent":
        return f"{base}_parent"
    return base


# ─── Client init ──────────────────────────────────────────────────────────────

def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        cfg     = get_settings()
        _client = chromadb.PersistentClient(
            path     = cfg.chroma_path,
            settings = ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def _get_or_create(name: str) -> chromadb.Collection:
    client = _get_client()
    col = client.get_or_create_collection(
        name     = name,
        metadata = {"hnsw:space": "cosine"},
    )
    return col


# ─── Public collection accessors ─────────────────────────────────────────────

def init_chroma(user_id: str | None = None):
    global _collections
    normalized = _normalize_user_id(user_id)

    child_name  = _collection_name(user_id, "child")
    parent_name = _collection_name(user_id, "parent")

    _collections[normalized]              = _get_or_create(child_name)
    _collections[f"{normalized}_parent"]  = _get_or_create(parent_name)

    get_embedder()
    print(
        f"[ChromaDB] Ready — {child_name} ({_collections[normalized].count()} child chunks) "
        f"| {parent_name} ({_collections[f'{normalized}_parent'].count()} parent chunks)"
    )


def get_collection(user_id: str | None = None) -> chromadb.Collection:
    """Returns the CHILD collection (for embedding + search)."""
    normalized = _normalize_user_id(user_id)
    if normalized not in _collections:
        init_chroma(user_id)
    return _collections[normalized]


def get_parent_collection(user_id: str | None = None) -> chromadb.Collection:
    """Returns the PARENT collection (for LLM context lookup)."""
    normalized = _normalize_user_id(user_id)
    key = f"{normalized}_parent"
    if key not in _collections:
        init_chroma(user_id)
    return _collections[key]


def get_parents_by_ids(
    parent_ids: list[str],
    user_id: str | None = None,
) -> list[dict]:
    """
    Fetch parent chunks by their IDs from the parent collection.
    Returns list of {id, text, metadata} dicts.
    """
    if not parent_ids:
        return []
    col     = get_parent_collection(user_id)
    unique  = list(dict.fromkeys(parent_ids))   # deduplicate, preserve order
    try:
        results = col.get(ids=unique, include=["documents", "metadatas"])
    except Exception:
        return []
    out = []
    for pid, doc, meta in zip(
        results.get("ids", []),
        results.get("documents", []),
        results.get("metadatas", []),
    ):
        out.append({"id": pid, "text": doc, "metadata": meta})
    return out


# ─── Utilities ────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embedder().encode(texts, show_progress_bar=False).tolist()


def make_doc_id(source: str, chunk_index: int) -> str:
    """Stable unique ID for a chunk."""
    raw = f"{source}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()
