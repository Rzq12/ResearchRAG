import { CheckCircle, Key, WarningCircle } from "@phosphor-icons/react";

import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { useSettings } from "@/context/SettingsContext";
import { useConfig } from "@/hooks/useServerData";
import type { Provider } from "@/lib/types";
import { stripLeadingSymbols } from "@/lib/utils";

const KEY_META: Record<
  Provider,
  { label: string; store: "groq" | "gemini" | "hf"; link: string }
> = {
  gemini: {
    label: "Google AI API Key",
    store: "gemini",
    link: "https://aistudio.google.com/app/apikey",
  },
  groq: {
    label: "Groq API Key",
    store: "groq",
    link: "https://console.groq.com",
  },
  hf: {
    label: "Endpoint token (optional)",
    store: "hf",
    link: "",
  },
};

/** Model dropdown + provider hint + the single dynamic API-key field. */
export function ModelSelector() {
  const { data: config } = useConfig();
  const { selectedModel, setSelectedModel, provider, keys, setKey } = useSettings();

  const models = config?.models ?? [];
  const current = models.find((m) => m.id === selectedModel);
  const meta = KEY_META[provider];
  const keyValue = keys[meta.store];

  return (
    <div className="space-y-3">
      <Select
        label="Model"
        options={models.map((m) => ({ value: m.id, label: stripLeadingSymbols(m.label) }))}
        value={selectedModel}
        onChange={(e) => setSelectedModel(e.target.value)}
      />
      {current?.hint_text && (
        <p className="text-[11px] text-zinc-500">{stripLeadingSymbols(current.hint_text)}</p>
      )}

      <Input
        label={meta.label}
        type="password"
        placeholder="Paste your API key here…"
        value={keyValue}
        onChange={(e) => setKey(meta.store, e.target.value)}
      />
      <p className="flex items-center gap-1.5 text-[11px]">
        <Key className="h-3.5 w-3.5 text-zinc-500" />
        {keyValue ? (
          <span className="flex items-center gap-1 text-accent">
            <CheckCircle className="h-3.5 w-3.5" weight="fill" /> Key active
          </span>
        ) : (
          <span className="flex items-center gap-1 text-amber-400">
            <WarningCircle className="h-3.5 w-3.5" /> Key not set
          </span>
        )}
        {meta.link && (
          <a
            href={meta.link}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 text-accent transition-colors hover:text-accent-soft"
          >
            Get key
          </a>
        )}
      </p>
    </div>
  );
}
