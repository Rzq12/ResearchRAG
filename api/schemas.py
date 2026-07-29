"""
Pydantic v2 request/response schemas for the ResearchRAG API.

These describe the wire format only. The underlying data models
(``OpenAlexWork``, ``Reference`` …) stay as dataclasses in ``app/`` and are
converted via ``api.serialize``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    display_name: str = ""
    password: str


class RegisterResponse(BaseModel):
    success: bool
    message: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    """Access + refresh pair returned by /login and /refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires
    user_id: str
    display_name: str = ""


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: str
    display_name: str = ""


# ─── Models / config ──────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    label: str
    provider: Literal["groq", "gemini", "hf"]
    hint_icon: str = ""
    hint_text: str = ""


class ConfigResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str
    require_user_id: bool
    max_upload_mb: int
    research_topics: list[str]


# ─── OpenAlex ─────────────────────────────────────────────────────────────────

class OpenAlexWorkModel(BaseModel):
    openalex_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    published: str = ""
    url: str = ""
    referenced_works: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    citation_count: int = 0


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    api_key: str | None = None  # optional OpenAlex key


class SearchResponse(BaseModel):
    works: list[OpenAlexWorkModel]


IngestMode = Literal["abstracts", "fulltext", "both"]


class IngestOpenAlexRequest(BaseModel):
    works: list[OpenAlexWorkModel]
    mode: IngestMode = "abstracts"


class FulltextDetail(BaseModel):
    title: str
    status: str
    source: str | None = None
    chunks: int | None = None
    pdf_url: str | None = None


class FulltextSummary(BaseModel):
    fetched: int = 0
    skipped: int = 0
    failed: int = 0
    details: list[FulltextDetail] = Field(default_factory=list)


class IngestOpenAlexResponse(BaseModel):
    abstracts_ingested: int = 0
    fulltext: FulltextSummary | None = None


class CitationsRequest(BaseModel):
    openalex_id: str
    api_key: str | None = None


class CitationsResponse(BaseModel):
    references: dict[str, str]


class TopicsRequest(BaseModel):
    works: list[OpenAlexWorkModel]
    groq_api_key: str
    model: str | None = None


class TopicsResponse(BaseModel):
    labels: dict[str, str]


class SuggestionsRequest(BaseModel):
    # Either OpenAlex works or plain title strings.
    works: list[OpenAlexWorkModel] | None = None
    titles: list[str] | None = None
    api_key: str
    model: str | None = None
    n: int = 5


class SuggestionsResponse(BaseModel):
    suggestions: list[str]


# ─── Documents / knowledge base ───────────────────────────────────────────────

class DocumentModel(BaseModel):
    title: str
    source: str = ""
    authors: str = ""
    published: str = ""
    url: str = ""


class DocumentsResponse(BaseModel):
    documents: list[DocumentModel]


class CoverageModel(BaseModel):
    coverage_pct: float | None = None
    covered_pages: int | None = None
    total_pages: int | None = None
    fallback_used: int | None = None
    missing_pages: Any | None = None


class PdfIngestResponse(BaseModel):
    filename: str
    chunks_added: int = 0
    chunks_skipped: int = 0
    parents_added: int = 0
    total_children: int = 0
    coverage: CoverageModel | None = None
    message: str | None = None
    # True when this upload replaced an earlier revision of the same document,
    # so the UI can say "updated" instead of "already indexed".
    replaced_revision: bool = False


class DeleteDocumentRequest(BaseModel):
    title: str


class DeleteDocumentResponse(BaseModel):
    deleted: int


class SummarizeRequest(BaseModel):
    title: str
    api_key: str
    model: str | None = None


class SummarizeResponse(BaseModel):
    summary: str


class ClearResponse(BaseModel):
    cleared: int


class KbStatsResponse(BaseModel):
    total_chunks: int
    documents: int


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str
    chat_history: list[ChatMessage] = Field(default_factory=list)
    api_key: str
    model: str | None = None
    where: dict[str, Any] | None = None  # optional Chroma metadata filter
    # When True, answer strictly from the user's knowledge base and never fall
    # back to live OpenAlex/web. Defaults False to match the backend default.
    kb_only: bool = False


# ─── Semantic search ──────────────────────────────────────────────────────────

class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 15
    content_type_filter: str | None = None
    min_score: float = 0.0


class SemanticHit(BaseModel):
    text: str
    score: float
    page_num: Any = "?"
    content_type: str = "text"
    section_title: str = ""
    section_path: str = ""
    source: str = ""
    title: str = ""
    chunk_index: Any = 0
    parent_id: str = ""
    chunk_role: str = "child"


class SemanticSearchResponse(BaseModel):
    results: list[SemanticHit]
