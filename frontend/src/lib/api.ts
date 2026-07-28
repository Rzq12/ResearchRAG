// Typed fetch client for the ResearchRAG FastAPI backend.
// Every function targets an endpoint defined in api/routers/*.py.

import type {
  AppConfig,
  AuthResult,
  DocumentInfo,
  IngestMode,
  IngestResult,
  KbStats,
  OpenAlexWork,
  PdfIngestResult,
  SemanticHit,
  WhereFilter,
} from "./types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      ...init,
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
    );
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body?.detail || body?.message || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonBody(data: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(data) };
}

// ─── Meta ──────────────────────────────────────────────────────────────────
export const getConfig = () => request<AppConfig>("/api/config");
export const getHealth = () => request<{ status: string }>("/api/health");

// ─── Auth ──────────────────────────────────────────────────────────────────
export const register = (username: string, display_name: string, password: string) =>
  request<AuthResult>("/api/auth/register", jsonBody({ username, display_name, password }));

export const login = (username: string, password: string) =>
  request<AuthResult>("/api/auth/login", jsonBody({ username, password }));

// ─── OpenAlex ────────────────────────────────────────────────────────────────
export const searchOpenAlex = (query: string, max_results: number, api_key?: string) =>
  request<{ works: OpenAlexWork[] }>(
    "/api/openalex/search",
    jsonBody({ query, max_results, api_key: api_key || null }),
  );

export const ingestOpenAlex = (works: OpenAlexWork[], mode: IngestMode, user_id: string | null) =>
  request<IngestResult>("/api/openalex/ingest", jsonBody({ works, mode, user_id }));

export const fetchCitations = (openalex_id: string, api_key?: string) =>
  request<{ references: Record<string, string> }>(
    "/api/openalex/citations",
    jsonBody({ openalex_id, api_key: api_key || null }),
  );

export const classifyTopics = (works: OpenAlexWork[], groq_api_key: string, model?: string) =>
  request<{ labels: Record<string, string> }>(
    "/api/openalex/topics",
    jsonBody({ works, groq_api_key, model: model || null }),
  );

export const getSuggestions = (params: {
  works?: OpenAlexWork[];
  titles?: string[];
  api_key: string;
  model?: string;
  n?: number;
}) =>
  request<{ suggestions: string[] }>(
    "/api/openalex/suggestions",
    jsonBody({
      works: params.works || null,
      titles: params.titles || null,
      api_key: params.api_key,
      model: params.model || null,
      n: params.n ?? 5,
    }),
  );

// ─── Documents / KB ──────────────────────────────────────────────────────────
export const listDocuments = (user_id: string | null) =>
  request<{ documents: DocumentInfo[] }>(
    `/api/documents${user_id ? `?user_id=${encodeURIComponent(user_id)}` : ""}`,
  );

export const getKbStats = (user_id: string | null) =>
  request<KbStats>(
    `/api/documents/stats${user_id ? `?user_id=${encodeURIComponent(user_id)}` : ""}`,
  );

export async function uploadPdf(file: File, user_id: string | null): Promise<PdfIngestResult> {
  const form = new FormData();
  form.append("file", file);
  if (user_id) form.append("user_id", user_id);
  // Note: do NOT set Content-Type — the browser sets the multipart boundary.
  const res = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = `Upload failed (${res.status})`;
    try {
      detail = (await res.json())?.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as PdfIngestResult;
}

export const summarizeDocument = (
  title: string,
  user_id: string | null,
  api_key: string,
  model?: string,
) =>
  request<{ summary: string }>(
    "/api/documents/summarize",
    jsonBody({ title, user_id, api_key, model: model || null }),
  );

export const deleteDocument = (title: string, user_id: string | null) =>
  request<{ deleted: number }>("/api/documents", {
    method: "DELETE",
    body: JSON.stringify({ title, user_id }),
  });

export const clearKnowledgeBase = (user_id: string | null) =>
  request<{ cleared: number }>("/api/documents/clear", jsonBody({ user_id }));

// ─── Semantic search ──────────────────────────────────────────────────────────
export const semanticSearch = (params: {
  query: string;
  user_id: string | null;
  top_k: number;
  content_type_filter?: string | null;
  min_score: number;
}) =>
  request<{ results: SemanticHit[] }>(
    "/api/semantic-search",
    jsonBody({
      query: params.query,
      user_id: params.user_id,
      top_k: params.top_k,
      content_type_filter: params.content_type_filter || null,
      min_score: params.min_score,
    }),
  );

export type { WhereFilter };
