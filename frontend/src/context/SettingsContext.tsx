import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { useLocalStorage } from "@/hooks/useLocalStorage";
import { providerFromModel, resolveLlm, type CustomLlm, type LlmParams } from "@/lib/llm";
import type { Provider, SuggestionLanguage, WhereFilter } from "@/lib/types";

type KeyStore = Record<Provider, string> & { openalex: string };

interface SettingsContextValue {
  /** Dropdown value; "openai:" stands for the custom endpoint below. */
  selectedModel: string;
  setSelectedModel: (model: string) => void;
  provider: Provider;
  keys: KeyStore;
  setKey: (which: keyof KeyStore, value: string) => void;
  /** Resolved LLM key for the currently-selected model's provider. */
  activeApiKey: string;
  /** User-supplied OpenAI-compatible endpoint, used when provider is "openai". */
  customLlm: CustomLlm;
  setCustomLlm: (patch: Partial<CustomLlm>) => void;
  /** model / api_key / base_url to send with every LLM-backed request. */
  llm: LlmParams;
  /** False when that request would be rejected for missing configuration. */
  llmReady: boolean;
  /** Why `llmReady` is false, phrased for the user. */
  llmMissing: string | null;
  whereFilter: WhereFilter;
  setWhereFilter: (where: WhereFilter) => void;
  /** When true, answers come strictly from the KB (no live web/OpenAlex fallback). */
  kbOnly: boolean;
  setKbOnly: (value: boolean) => void;
  suggestionLanguage: SuggestionLanguage;
  setSuggestionLanguage: (value: SuggestionLanguage) => void;
  /** Suggest follow-up questions after each answer (one extra LLM call). */
  followupsEnabled: boolean;
  setFollowupsEnabled: (value: boolean) => void;
}

const DEFAULT_KEYS: KeyStore = { groq: "", gemini: "", hf: "", openai: "", openalex: "" };
const DEFAULT_CUSTOM_LLM: CustomLlm = { baseUrl: "", model: "" };

const SettingsContext = createContext<SettingsContextValue | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [selectedModel, setSelectedModel] = useLocalStorage<string>(
    "rr_model",
    "gemini-3.5-flash",
  );
  const [storedKeys, setKeys] = useLocalStorage<KeyStore>("rr_keys", DEFAULT_KEYS);
  const [storedCustom, setStoredCustom] = useLocalStorage<CustomLlm>(
    "rr_custom_llm",
    DEFAULT_CUSTOM_LLM,
  );
  const [whereFilter, setWhereFilter] = useLocalStorage<WhereFilter>("rr_where", null);
  // Default ON — this app is about answering from the user's own papers.
  const [kbOnly, setKbOnly] = useLocalStorage<boolean>("rr_kb_only", true);
  const [suggestionLanguage, setSuggestionLanguage] = useLocalStorage<SuggestionLanguage>(
    "rr_suggest_lang",
    "id",
  );
  const [followupsEnabled, setFollowupsEnabled] = useLocalStorage<boolean>(
    "rr_followups",
    true,
  );

  // Stores written before a field existed lack it; fill from the defaults so
  // inputs stay controlled.
  const keys = useMemo(() => ({ ...DEFAULT_KEYS, ...storedKeys }), [storedKeys]);
  const customLlm = useMemo(() => ({ ...DEFAULT_CUSTOM_LLM, ...storedCustom }), [storedCustom]);

  const setKey = useCallback(
    (which: keyof KeyStore, value: string) =>
      setKeys((prev) => ({ ...prev, [which]: value })),
    [setKeys],
  );
  const setCustomLlm = useCallback(
    (patch: Partial<CustomLlm>) => setStoredCustom((prev) => ({ ...prev, ...patch })),
    [setStoredCustom],
  );

  const provider = providerFromModel(selectedModel);
  const activeApiKey = keys[provider] || "";
  const resolved = useMemo(
    () => resolveLlm(selectedModel, keys, customLlm),
    [selectedModel, keys, customLlm],
  );

  const value = useMemo<SettingsContextValue>(
    () => ({
      selectedModel,
      setSelectedModel,
      provider,
      keys,
      setKey,
      activeApiKey,
      customLlm,
      setCustomLlm,
      llm: resolved.params,
      llmReady: resolved.ready,
      llmMissing: resolved.missing,
      whereFilter,
      setWhereFilter,
      kbOnly,
      setKbOnly,
      suggestionLanguage,
      setSuggestionLanguage,
      followupsEnabled,
      setFollowupsEnabled,
    }),
    [
      selectedModel,
      setSelectedModel,
      provider,
      keys,
      setKey,
      activeApiKey,
      customLlm,
      setCustomLlm,
      resolved,
      whereFilter,
      setWhereFilter,
      kbOnly,
      setKbOnly,
      suggestionLanguage,
      setSuggestionLanguage,
      followupsEnabled,
      setFollowupsEnabled,
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
