from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Groq
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    # ChromaDB
    chroma_path: str = "./data/chroma_db"
    chroma_collection: str = "arxiv_rag"

    # Embedding model (runs locally, gratis)
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

    # RAG
    top_k_retrieval: int = 15          # chunks to retrieve from ChromaDB per query
    similarity_threshold: float = 0.2  # minimum cosine similarity score
    max_tokens_response: int = 2000    # max tokens for LLM response
    chunk_size: int = 1200             # chars per chunk (≈240 words)
    chunk_overlap: int = 200           # overlap between chunks (≈40 words)
    summarize_max_chars: int = 20000   # max chars fed to the summarizer LLM

    # Full-text fetching (Semantic Scholar + Unpaywall)
    fulltext_mailto: str | None = None  # email for Unpaywall polite pool (falls back to openalex_mailto)
    fulltext_max_pdf_mb: int = 30       # max size to download for full-text PDFs

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
