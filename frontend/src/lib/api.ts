// Typed fetch client for the ResearchRAG FastAPI backend.
// Every function targets an endpoint defined in api/routers/*.py.
//
// Identity is carried by the bearer token only — no call passes a user_id, and
// the server would ignore it if one did. See api/security.py.

import {
  clearSession,
  getSession,
  isAccessTokenStale,
  refreshSession,
  sessionFromTokenResponse,
  setSession,
} from "./authStore";
import type {
  AppConfig,
  DocumentInfo,
  IngestMode,
  IngestResult,
  KbStats,
  OpenAlexWork,
  PdfIngestResult,
  SemanticHit,
  Session,
  WhereFilter,
} from "./types";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL;

if (!RAW_BASE && import.meta.env.PROD) {
  // Belt-and-braces: vite.config.ts already fails the build without this var,
  // so reaching here means someone bypassed the build guard.
  throw new Error("VITE_API_BASE_URL is not configured for this production build.");
}

/**
 * Normalise the configured base URL.
 *
 * A value like "my-space.hf.space" (no scheme) is treated by fetch() as a
 * RELATIVE path, so requests silently hit the frontend's own origin, the SPA
 * rewrite answers with index.html, and the app reports a JSON parse error that
 * looks nothing like the actual cause. The build now rejects that, but this
 * keeps an already-deployed bad build working instead of appearing broken.
 */
function normaliseBaseUrl(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;

  const fixed = `https://${trimmed.replace(/^\/+/, "")}`;
  console.warn(
    `[ResearchRAG] VITE_API_BASE_URL "${raw}" has no scheme; assuming "${fixed}". ` +
      "Set the full https:// URL in your environment to remove this warning.",
  );
  return fixed;
}

export const API_BASE_URL = normaliseBaseUrl(RAW_BASE || "http://localhost:8000");

export class ApiError extends Error {
  status: number;
  /** Correlation id from the server; quote it in bug reports. */
  requestId?: string;
  constructor(message: string, status: number, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

/** Pull the message out of the API's error envelope. */
async function toApiError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  let requestId: string | undefined = res.headers.get("X-Request-ID") ?? undefined;
  try {
    const body = await res.json();
    message = body?.message || body?.detail || message;
    requestId = body?.request_id ?? requestId;
    if (Array.isArray(body?.fields) && body.fields.length) {
      message += `: ${body.fields.map((f: { message: string }) => f.message).join(", ")}`;
    }
  } catch {
    /* non-JSON body */
  }
  return new ApiError(message, res.status, requestId);
}

interface RequestOptions extends RequestInit {
  /** Skip auth entirely (login/register/refresh/config). */
  anonymous?: boolean;
}

async function rawFetch(path: string, init: RequestOptions, token?: string): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

/**
 * Core request wrapper: attaches the bearer token, refreshes proactively when
 * the access token is about to expire, and retries exactly once after a 401.
 * A failed refresh clears the session, which flips the app back to the login
 * screen through the auth store subscription.
 */
async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  let token: string | undefined;

  if (!init.anonymous) {
    let session = getSession();
    if (session && isAccessTokenStale(session)) {
      session = await refreshSession(API_BASE_URL);
    }
    token = session?.accessToken;
  }

  let res: Response;
  try {
    res = await rawFetch(path, init, token);
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
    );
  }

  // Reactive refresh: the token expired between check and call, or was revoked.
  if (res.status === 401 && !init.anonymous && getSession()) {
    const refreshed = await refreshSession(API_BASE_URL);
    if (refreshed) {
      try {
        res = await rawFetch(path, init, refreshed.accessToken);
      } catch {
        throw new ApiError(`Cannot reach the API at ${API_BASE_URL}.`, 0);
      }
    } else {
      clearSession();
      throw new ApiError("Your session has expired. Please sign in again.", 401);
    }
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonBody(data: unknown): RequestOptions {
  return { method: "POST", body: JSON.stringify(data) };
}

// ─── Meta (public) ───────────────────────────────────────────────────────────
export const getConfig = () => request<AppConfig>("/api/config", { anonymous: true });
export const getHealth = () => request<{ status: string }>("/api/health", { anonymous: true });

// ─── Auth ────────────────────────────────────────────────────────────────────
interface TokenPayload {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user_id: string;
  display_name?: string;
}

export const register = (username: string, display_name: string, password: string) =>
  request<{ success: boolean; message: string }>("/api/auth/register", {
    ...jsonBody({ username, display_name, password }),
    anonymous: true,
  });

export async function login(username: string, password: string): Promise<Session> {
  const data = await request<TokenPayload>("/api/auth/login", {
    ...jsonBody({ username, password }),
    anonymous: true,
  });
  const session = sessionFromTokenResponse(data);
  setSession(session);
  return session;
}

export async function logout(): Promise<void> {
  const session = getSession();
  if (session?.refreshToken) {
    try {
      await request<void>("/api/auth/logout", {
        ...jsonBody({ refresh_token: session.refreshToken }),
        anonymous: true,
      });
    } catch {
      // Server-side revocation is best-effort; always clear locally.
    }
  }
  clearSession();
}

// ─── OpenAlex ────────────────────────────────────────────────────────────────
export const searchOpenAlex = (query: string, max_results: number, api_key?: string) =>
  request<{ works: OpenAlexWork[] }>(
    "/api/openalex/search",
    jsonBody({ query, max_results, api_key: api_key || null }),
  );

export const ingestOpenAlex = (works: OpenAlexWork[], mode: IngestMode) =>
  request<IngestResult>("/api/openalex/ingest", jsonBody({ works, mode }));

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
export const listDocuments = () => request<{ documents: DocumentInfo[] }>("/api/documents");

export const getKbStats = () => request<KbStats>("/api/documents/stats");

export async function uploadPdf(file: File): Promise<PdfIngestResult> {
  const form = new FormData();
  form.append("file", file);
  // Content-Type is intentionally unset so the browser adds the multipart boundary.
  return request<PdfIngestResult>("/api/documents/upload", { method: "POST", body: form });
}

export const summarizeDocument = (title: string, api_key: string, model?: string) =>
  request<{ summary: string }>(
    "/api/documents/summarize",
    jsonBody({ title, api_key, model: model || null }),
  );

export const deleteDocument = (title: string) =>
  request<{ deleted: number }>("/api/documents", {
    method: "DELETE",
    body: JSON.stringify({ title }),
  });

export const clearKnowledgeBase = () =>
  request<{ cleared: number }>("/api/documents/clear", jsonBody({}));

// ─── Semantic search ─────────────────────────────────────────────────────────
export const semanticSearch = (params: {
  query: string;
  top_k: number;
  content_type_filter?: string | null;
  min_score: number;
}) =>
  request<{ results: SemanticHit[] }>(
    "/api/semantic-search",
    jsonBody({
      query: params.query,
      top_k: params.top_k,
      content_type_filter: params.content_type_filter || null,
      min_score: params.min_score,
    }),
  );

export type { WhereFilter };
