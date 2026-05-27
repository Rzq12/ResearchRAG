from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Groq
    groq_api_key: str | None = None
    # Default: Llama 4 Scout — 512k context, higher TPM on free tier.
    # Switch to llama-3.1-8b-instant for fastest responses.
    # Avoid llama-3.3-70b-versatile on free tier (12k TPM → 413 with large contexts).
    groq_model: str = "gemini-3.5-flash"

    # Google Gemini
    gemini_api_key: str | None = None  # GEMINI_API_KEY env var

    # ChromaDB
    chroma_path: str = "./data/chroma_db"
    chroma_collection: str = "researchrag"

    # Embedding model (runs locally, free)
    embedding_model: str = "all-MiniLM-L6-v2"

    # OpenAlex search
    openalex_base_url: str = "https://api.openalex.org/works"
    openalex_api_key: str | None = None
    openalex_mailto: str | None = None
    top_k_openalex: int = 5
    openalex_timeout_seconds: int = 30
    openalex_num_retries: int = 2
    openalex_backoff_seconds: int = 3

    # Upload limits
    max_upload_mb: int = 20

    # User scoping
    require_user_id: bool = True

    # ── RAG — retrieval ───────────────────────────────────────────────────────
    top_k_retrieval: int = 15          # child chunks to retrieve per query
    # NOTE: With parent-child retrieval this is a SOFT threshold.
    # The system rejects a query only if best_child_score < threshold / 2.
    # Recommended range: 0.05–0.15. Lower = more permissive retrieval.
    similarity_threshold: float = 0.1  # was 0.2; lowered for parent-child strategy
    max_tokens_response: int = 2000    # max tokens for LLM response
    summarize_max_chars: int = 20000   # max chars fed to summarizer LLM

    # ── Chunking — child (small, for embedding precision) ─────────────────────
    child_chunk_words: int = 180       # target words per child chunk
    child_chunk_overlap_words: int = 30

    # ── Chunking — parent (large, for LLM context) ────────────────────────────
    parent_chunk_words: int = 700      # target words per parent chunk
    children_per_parent: int = 4       # how many child chunks grouped into one parent

    # ── Legacy char-based settings (still used for abstract chunking) ─────────
    chunk_size: int = 1200             # chars per chunk (≈240 words)
    chunk_overlap: int = 200           # overlap between chunks (≈40 words)

    # ── Reranker (cross-encoder) ──────────────────────────────────────────────
    enable_reranker: bool = False      # set True to enable; downloads ~80MB model on first use
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 15          # top-k candidates after reranking

    # ── Full-text fetching (Semantic Scholar + Unpaywall) ─────────────────────
    fulltext_mailto: str | None = None  # email for Unpaywall polite pool
    fulltext_max_pdf_mb: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
