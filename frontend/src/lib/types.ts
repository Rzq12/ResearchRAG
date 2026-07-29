// Wire types mirroring api/schemas.py. Keep in sync with the backend.

export type Provider = "groq" | "gemini" | "hf";

export interface ModelInfo {
  id: string;
  label: string;
  provider: Provider;
  hint_icon: string;
  hint_text: string;
}

export interface AppConfig {
  models: ModelInfo[];
  default_model: string;
  require_user_id: boolean;
  max_upload_mb: number;
  research_topics: string[];
}

export interface AuthResult {
  success: boolean;
  message: string;
}

/** Re-exported so components can type a session without reaching into authStore. */
export type { Session } from "./authStore";

export interface OpenAlexWork {
  openalex_id: string;
  title: string;
  authors: string[];
  abstract: string;
  published: string;
  url: string;
  referenced_works: string[];
  concepts: string[];
  citation_count: number;
}

export type IngestMode = "abstracts" | "fulltext" | "both";

export interface FulltextDetail {
  title: string;
  status: string;
  source?: string | null;
  chunks?: number | null;
  pdf_url?: string | null;
}

export interface FulltextSummary {
  fetched: number;
  skipped: number;
  failed: number;
  details: FulltextDetail[];
}

export interface IngestResult {
  abstracts_ingested: number;
  fulltext: FulltextSummary | null;
}

export interface Coverage {
  coverage_pct: number | null;
  covered_pages: number | null;
  total_pages: number | null;
  fallback_used: number | null;
  missing_pages: unknown | null;
}

export interface PdfIngestResult {
  filename: string;
  chunks_added: number;
  chunks_skipped: number;
  parents_added: number;
  total_children: number;
  coverage: Coverage | null;
  message?: string | null;
  /** True when this upload superseded an earlier revision of the same document. */
  replaced_revision: boolean;
}

export interface DocumentInfo {
  title: string;
  source: string;
  authors: string;
  published: string;
  url: string;
}

export interface KbStats {
  total_chunks: number;
  documents: number;
}

export interface Reference {
  title: string;
  authors: string;
  published: string;
  url: string;
  source: string; // "openalex" | "upload"
  relevance_score: number;
}

export type ChatSource = "kb" | "openalex-live" | "web" | "none";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  reasoning?: string;
  references?: Reference[];
  source?: ChatSource;
  error?: boolean;
}

export interface SemanticHit {
  text: string;
  score: number;
  page_num: string | number;
  content_type: string;
  section_title: string;
  section_path: string;
  source: string;
  title: string;
  chunk_index: string | number;
  parent_id: string;
  chunk_role: string;
}

// Optional Chroma metadata filter built from the retrieval-filters UI.
export type WhereFilter = Record<string, unknown> | null;
