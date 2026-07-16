from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Groq
    groq_api_key: str | None = None
    # Default LLM for generation. Provider is auto-routed from the name:
    # "gemini-*" → Gemini, "hf:*" → self-hosted endpoint, else → Groq.
    # (Renamed from the misleading `groq_model`; the old GROQ_MODEL env var
    # still works via the alias below.)
    default_model: str = Field(
        default="gemini-3.5-flash",
        validation_alias=AliasChoices("default_model", "groq_model"),
    )

    @property
    def groq_model(self) -> str:
        """Backward-compat alias for default_model."""
        return self.default_model

    # Google Gemini
    gemini_api_key: str | None = None  # GEMINI_API_KEY env var

    # ChromaDB
    chroma_path: str = "./data/chroma_db"
    # _v2 suffix: multilingual-e5 embeddings are 768-dim; the old MiniLM
    # collections are 384-dim and cannot be reused. Migrate existing data with:
    #   python -m scripts.reindex --apply
    chroma_collection: str = "researchrag_v2"

    # ── Embedding (local, open-source, multilingual) ──────────────────────────
    # e5 models REQUIRE the query:/passage: prefixes — without them quality
    # drops below MiniLM. If RAM is tight (free-tier container), switch to
    # intfloat/multilingual-e5-small (~470 MB loaded vs ~1.1 GB for base).
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_query_prefix: str = "query: "
    embedding_passage_prefix: str = "passage: "

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

    # ── Reranker (cross-encoder, multilingual) ────────────────────────────────
    # mmarco-mMiniLMv2: multilingual (mMARCO, incl. Indonesian), small enough
    # for CPU, and sharply calibrated — relevant pairs ≈ 0.99, irrelevant
    # ≈ 0.002 after sigmoid, which is what relevance_threshold needs.
    # Measured on CPU: ~3x faster than BAAI/bge-reranker-base with better
    # separation. GPU-quality upgrade: BAAI/bge-reranker-v2-m3 (~2.2 GB).
    enable_reranker: bool = True
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    reranker_top_k: int = 5            # top-k candidates after reranking
    rerank_max_candidates: int = 20    # cap pairs sent to the cross-encoder (CPU cost)

    # ── Full-text fetching (Semantic Scholar + Unpaywall) ─────────────────────
    fulltext_mailto: str | None = None  # email for Unpaywall polite pool
    fulltext_max_pdf_mb: int = 30

    # ── Hybrid retrieval: BM25 + vector, RRF fusion ───────────────────────────
    # Academic text is full of exact-match tokens (author names, acronyms like
    # BERT/LoRA, dataset names) that pure semantic search misses.
    enable_bm25: bool = True
    bm25_weight: float = 0.4           # notebook ensemble weights
    vector_weight: float = 0.6
    bm25_max_corpus: int = 20_000      # above this, skip BM25 (index too big)

    # ── HyDE (Hypothetical Document Embeddings) ───────────────────────────────
    # Costs hyde_num_hypotheticals extra LLM calls per query.
    enable_hyde: bool = True
    hyde_num_hypotheticals: int = 2
    hyde_temperature: float = 0.9
    hyde_max_tokens: int = 150

    # ── Relevance threshold + live fallback ───────────────────────────────────
    # Applied to the reranker's top-1 sigmoid score. Below it, the local KB is
    # judged irrelevant and context comes from OpenAlex live → DuckDuckGo.
    relevance_threshold: float = 0.5
    enable_web_fallback: bool = True
    fallback_max_results: int = 3

    # ── Reasoning (<think> block before the final answer) ─────────────────────
    enable_reasoning: bool = True

    # ── Self-hosted provider (model prefix "hf:") ─────────────────────────────
    # OpenAI-compatible endpoint (vLLM / TGI / HF Inference) for serving your
    # own fine-tuned model. Leave unset to use only Groq/Gemini.
    # When both URL and model name are set, the model appears in the UI as
    # "hf:<hf_model_name>".
    hf_endpoint_url: str | None = None
    hf_api_token: str | None = None
    hf_model_name: str | None = None   # e.g. "username/my-finetuned-model"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
