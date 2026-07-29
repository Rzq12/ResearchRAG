import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { IconContext } from "@phosphor-icons/react";

import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
// KaTeX ships its own metric-critical fonts; without this stylesheet formulas
// render as unaligned plain text. Imported here rather than via an @import in
// index.css so Vite fingerprints the woff2 files as regular assets.
import "katex/dist/katex.min.css";

import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AuthProvider } from "./context/AuthContext";
import { SettingsProvider } from "./context/SettingsContext";
import { ToastProvider } from "./context/ToastContext";
import { ApiError } from "./lib/api";
import "./index.css";

/**
 * Retry policy tuned for a sleeping backend.
 *
 * Hugging Face Spaces suspend on inactivity. On wake, nginx answers in about a
 * second but uvicorn must first load ~1.6 GB of embedding and reranker weights,
 * so for a minute or two the proxy returns 502/503/504. Failing immediately
 * shows "Cannot reach the API" for what is really a normal cold start, so reads
 * back off and retry instead.
 *
 * Mutations are deliberately NOT retried — replaying a POST that may have
 * already been applied is worse than surfacing the error.
 *
 * The budget must cover the whole wake window App.tsx promises the user
 * ("under two minutes"); giving up sooner shows an error screen while that
 * message is still on screen. Status 0 is our own "cannot reach the API",
 * so a genuinely dead backend also takes the full budget to surface.
 */
const COLD_START_STATUSES = new Set([0, 502, 503, 504]);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        error instanceof ApiError &&
        COLD_START_STATUSES.has(error.status) &&
        failureCount < 16,
      // failureCount is 0-based and read before it increments, so this is
      // 1s, 2s, 4s, then 8s capped ×13 — ~111s, just under the two minutes.
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
    mutations: { retry: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Precise, hairline Phosphor icons everywhere (never thick-stroked). */}
    <IconContext.Provider value={{ weight: "regular", size: 18 }}>
      {/* Outermost so it also catches throws from the providers themselves. */}
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <AuthProvider>
              <SettingsProvider>
                <App />
              </SettingsProvider>
            </AuthProvider>
          </ToastProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </IconContext.Provider>
  </StrictMode>,
);
