import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * Cross-panel workspace state that the sidebar and the chat both touch: the
 * query suggestions produced after ingest, shown as chips in the chat.
 *
 * A `pendingQuery` field used to live here so a suggestion click could park the
 * query in context for an effect in ChatPanel to notice and send. Nothing reads
 * it any more — the chip calls `send` directly — and a state round-trip that
 * triggers a network call from an effect is precisely the shape that makes
 * duplicate requests easy to reintroduce.
 */
interface WorkspaceContextValue {
  suggestions: string[];
  setSuggestions: (s: string[]) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const value = useMemo(() => ({ suggestions, setSuggestions }), [suggestions]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within <WorkspaceProvider>");
  return ctx;
}
