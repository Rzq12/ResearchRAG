import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from app.config import get_settings
import hashlib

_client = None
_collections: dict[str, chromadb.Collection] = {}
_embedder = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        cfg = get_settings()
        print(f"[Embedder] Loading {cfg.embedding_model}...")
        _embedder = SentenceTransformer(cfg.embedding_model)
    return _embedder


def _normalize_user_id(user_id: str | None) -> str:
    if not user_id:
        return "default"
    return user_id.strip().lower() or "default"


def _collection_name(user_id: str | None) -> str:
    cfg = get_settings()
    normalized = _normalize_user_id(user_id)
    if normalized == "default":
        return cfg.chroma_collection
    suffix = hashlib.md5(normalized.encode()).hexdigest()[:12]
    return f"{cfg.chroma_collection}_{suffix}"


def init_chroma(user_id: str | None = None):
    global _client, _collections
    cfg = get_settings()
    if _client is None:
        _client = chromadb.PersistentClient(
            path=cfg.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    collection_name = _collection_name(user_id)
    collection = _client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    _collections[_normalize_user_id(user_id)] = collection

    # Warm up embedder
    get_embedder()
    print(f"[ChromaDB] Ready — {collection.name} — {collection.count()} chunks stored")


def get_collection(user_id: str | None = None):
    normalized = _normalize_user_id(user_id)
    if normalized not in _collections:
        init_chroma(user_id=normalized)
    return _collections[normalized]


def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embedder().encode(texts, show_progress_bar=False).tolist()


def make_doc_id(source: str, chunk_index: int) -> str:
    """Stable unique ID for a chunk."""
    raw = f"{source}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()
