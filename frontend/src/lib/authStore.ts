// Token storage and the single-flight refresh used by the API client.
//
// Deliberately framework-free (no React) so `lib/api.ts` can reach it without a
// circular import back into context. React subscribes via `subscribe()`.
//
// Storage choice: the API lives on a different site (Vercel → HF Space), so
// httpOnly cookies would be third-party and are blocked by default in Safari
// and Firefox. Tokens therefore live in localStorage and travel in the
// Authorization header. The compensating control is a strict CSP plus never
// rendering untrusted HTML — see vercel.json and components/ui/Markdown.tsx.

export interface Session {
  accessToken: string;
  refreshToken: string;
  userId: string;
  displayName: string;
  /** Epoch ms at which the access token expires. */
  expiresAt: number;
}

const STORAGE_KEY = "rr_session";

// Refresh this many ms before actual expiry, so a request never races the clock.
const REFRESH_SKEW_MS = 60_000;

let session: Session | null = load();
const listeners = new Set<(s: Session | null) => void>();

function load(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    return parsed?.accessToken && parsed?.refreshToken ? parsed : null;
  } catch {
    return null;
  }
}

function persist(next: Session | null): void {
  try {
    if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode / quota — the in-memory session still works for this tab */
  }
}

export function getSession(): Session | null {
  return session;
}

export function setSession(next: Session | null): void {
  session = next;
  persist(next);
  listeners.forEach((fn) => fn(next));
}

export function clearSession(): void {
  setSession(null);
}

export function subscribe(fn: (s: Session | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Build a Session from the API's TokenResponse payload. */
export function sessionFromTokenResponse(data: {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user_id: string;
  display_name?: string;
}): Session {
  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    userId: data.user_id,
    displayName: data.display_name || data.user_id,
    expiresAt: Date.now() + data.expires_in * 1000,
  };
}

export function isAccessTokenStale(s: Session | null = session): boolean {
  return !s || Date.now() >= s.expiresAt - REFRESH_SKEW_MS;
}

// ── Single-flight refresh ────────────────────────────────────────────────────
// Several requests can 401 at once (the dashboard fires 3 on mount). Without
// this guard each would spend the same rotating refresh token, and the reuse
// detector on the server would treat that as theft and revoke the family.
let inFlight: Promise<Session | null> | null = null;

export function refreshSession(apiBaseUrl: string): Promise<Session | null> {
  if (inFlight) return inFlight;

  const current = session;
  if (!current?.refreshToken) return Promise.resolve(null);

  inFlight = (async () => {
    try {
      const res = await fetch(`${apiBaseUrl}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: current.refreshToken }),
      });
      if (!res.ok) {
        clearSession();
        return null;
      }
      const next = sessionFromTokenResponse(await res.json());
      setSession(next);
      return next;
    } catch {
      // Network failure: keep the session so a transient outage doesn't log the
      // user out. The failing request surfaces its own error instead.
      return null;
    } finally {
      inFlight = null;
    }
  })();

  return inFlight;
}
