import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { useLocalStorage } from "@/hooks/useLocalStorage";
import type { Provider, WhereFilter } from "@/lib/types";

/** Mirror of app.llm_client.get_provider — route provider from model id. */
export function providerFromModel(model: string): Provider {
  if (model.startsWith("hf:")) return "hf";
  if (model.startsWith("gemini")) return "gemini";
  return "groq";
}

type KeyStore = Record<Provider, string> & { openalex: string };

interface SettingsContextValue {
  selectedModel: string;
  setSelectedModel: (model: string) => void;
  provider: Provider;
  keys: KeyStore;
  setKey: (which: keyof KeyStore, value: string) => void;
  /** Resolved LLM key for the currently-selected model's provider. */
  activeApiKey: string;
  whereFilter: WhereFilter;
  setWhereFilter: (where: WhereFilter) => void;
  /** When true, answers come strictly from the KB (no live web/OpenAlex fallback). */
  kbOnly: boolean;
  setKbOnly: (value: boolean) => void;
}

const DEFAULT_KEYS: KeyStore = { groq: "", gemini: "", hf: "", openalex: "" };

const SettingsContext = createContext<SettingsContextValue | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [selectedModel, setSelectedModel] = useLocalStorage<string>(
    "rr_model",
    "gemini-3.5-flash",
  );
  const [keys, setKeys] = useLocalStorage<KeyStore>("rr_keys", DEFAULT_KEYS);
  const [whereFilter, setWhereFilter] = useLocalStorage<WhereFilter>("rr_where", null);
  // Default ON — this app is about answering from the user's own papers.
  const [kbOnly, setKbOnly] = useLocalStorage<boolean>("rr_kb_only", true);

  const setKey = useCallback(
    (which: keyof KeyStore, value: string) =>
      setKeys((prev) => ({ ...prev, [which]: value })),
    [setKeys],
  );

  const provider = providerFromModel(selectedModel);
  const activeApiKey = keys[provider] || "";

  const value = useMemo<SettingsContextValue>(
    () => ({
      selectedModel,
      setSelectedModel,
      provider,
      keys,
      setKey,
      activeApiKey,
      whereFilter,
      setWhereFilter,
      kbOnly,
      setKbOnly,
    }),
    [
      selectedModel,
      setSelectedModel,
      provider,
      keys,
      setKey,
      activeApiKey,
      whereFilter,
      setWhereFilter,
      kbOnly,
      setKbOnly,
    ],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within <SettingsProvider>");
  return ctx;
}
