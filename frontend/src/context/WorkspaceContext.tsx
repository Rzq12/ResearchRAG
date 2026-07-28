import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * Cross-panel workspace state that the sidebar and the chat both touch:
 *  - query suggestions produced after ingest (shown as chips in the chat)
 *  - a "pending query" set when the user clicks a suggestion chip
 */
interface WorkspaceContextValue {
  suggestions: string[];
  setSuggestions: (s: string[]) => void;
  pendingQuery: string | null;
  setPendingQuery: (q: string | null) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  const value = useMemo(
    () => ({ suggestions, setSuggestions, pendingQuery, setPendingQuery }),
    [suggestions, pendingQuery],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within <WorkspaceProvider>");
  return ctx;
}
