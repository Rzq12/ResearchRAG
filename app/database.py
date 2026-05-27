import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from app.config import get_settings
import hashlib

_client = None
_collection = None
_embedder = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        cfg = get_settings()
        print(f"[Embedder] Loading {cfg.embedding_model}...")
        _embedder = SentenceTransformer(cfg.embedding_model)
    return _embedder


def init_chroma():
    global _client, _collection
    cfg = get_settings()
    _client = chromadb.PersistentClient(
        path=cfg.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    _collection = _client.get_or_create_collection(
        name=cfg.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )
    # Warm up embedder
    get_embedder()
    print(f"[ChromaDB] Ready — {_collection.count()} chunks stored")


def get_collection():
    if _collection is None:
        init_chroma()
    return _collection


def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embedder().encode(texts, show_progress_bar=False).tolist()


def make_doc_id(source: str, chunk_index: int) -> str:
    """Stable unique ID for a chunk."""
    raw = f"{source}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()
