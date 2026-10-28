import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useAuth } from "./AuthContext";
import { useSettings } from "./SettingsContext";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import { getKbSuggestions } from "@/lib/api";
import type { SuggestionLanguage } from "@/lib/types";

/**
 * Cross-panel workspace state that the sidebar and the chat both touch: the
 * suggested questions, generated from the knowledge base and shown as chips in
 * the chat.
 *
 * Every fetch is started imperatively — after an ingest, or by the regenerate
 * button — never by an effect watching state. A `pendingQuery` field used to
 * live here so a chip click could park the query for an effect in ChatPanel to
 * send; that state round-trip is precisely the shape that makes duplicate
 * requests easy to reintroduce, so the chip calls `send` directly.
 */

export type SuggestionStatus = "idle" | "loading" | "error";

export interface RefreshOptions {
  /**
   * Focus on these documents, e.g. the ones just ingested. Omitted → the
   * latest documents, avoiding the questions already on screen.
   */
  titles?: string[];
  /** Override the saved language (used right after switching it). */
  language?: SuggestionLanguage;
}

interface WorkspaceContextValue {
  suggestions: string[];
  suggestionStatus: SuggestionStatus;
  suggestionError: string | null;
  refreshSuggestions: (options?: RefreshOptions) => Promise<void>;
  /** Drop a suggestion once it has been asked, and never suggest it again. */
  markSuggestionUsed: (question: string) => void;
  clearSuggestions: () => void;
}

/** Server-side cap on `exclude` (KbSuggestionsRequest). */
const MAX_EXCLUDE = 30;

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const { llm, llmReady, llmMissing, suggestionLanguage } = useSettings();

  // Keyed per user so a shared browser never shows one account's questions to
  // another, and persisted so a reload does not throw away a paid-for call.
  const [suggestions, setSuggestions] = useLocalStorage<string[]>(
    `rr_suggestions:${session?.userId ?? "anonymous"}`,
    [],
  );
  const [suggestionStatus, setStatus] = useState<SuggestionStatus>("idle");
  const [suggestionError, setError] = useState<string | null>(null);

  /** Questions already asked this session. */
  const askedRef = useRef<string[]>([]);
  /**
   * Latest-wins counter: a slow response must not overwrite a newer one, e.g.
   * regenerate pressed while an ingest-triggered refresh is still running.
   */
  const requestSeq = useRef(0);

  const refreshSuggestions = useCallback(
    async (options: RefreshOptions = {}) => {
      const seq = ++requestSeq.current;
      if (!llmReady) {
        setStatus("error");
        setError(llmMissing);
        return;
      }

      const regenerating = !options.titles?.length;
      const exclude = regenerating
        ? [...suggestions, ...askedRef.current]
        : askedRef.current;

      setStatus("loading");
      setError(null);
      try {
        const res = await getKbSuggestions(llm, {
          titles: options.titles,
          language: options.language ?? suggestionLanguage,
          exclude: exclude.slice(-MAX_EXCLUDE),
        });
        if (seq !== requestSeq.current) return;
        const next = res.suggestions ?? [];
        // A regenerate that only produced repeats keeps the current chips
        // rather than blanking the panel.
        if (next.length || !regenerating) setSuggestions(next);
        setStatus("idle");
      } catch (err) {
        if (seq !== requestSeq.current) return;
        setStatus("error");
        setError((err as Error).message || "Could not generate suggestions.");
      }
    },
    [llm, llmReady, llmMissing, suggestionLanguage, suggestions, setSuggestions],
  );

  const markSuggestionUsed = useCallback(
    (question: string) => {
      askedRef.current = [...askedRef.current, question];
      setSuggestions((prev) => prev.filter((q) => q !== question));
    },
    [setSuggestions],
  );

  const clearSuggestions = useCallback(() => {
    requestSeq.current += 1; // orphan any in-flight request
    setSuggestions([]);
    setStatus("idle");
    setError(null);
  }, [setSuggestions]);

  const value = useMemo(
    () => ({
      suggestions,
      suggestionStatus,
      suggestionError,
      refreshSuggestions,
      markSuggestionUsed,
      clearSuggestions,
    }),
    [
      suggestions,
      suggestionStatus,
      suggestionError,
      refreshSuggestions,
      markSuggestionUsed,
      clearSuggestions,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within <WorkspaceProvider>");
  return ctx;
}
