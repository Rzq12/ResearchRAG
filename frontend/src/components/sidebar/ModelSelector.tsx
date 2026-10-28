import { ChatsCircle, CheckCircle, Key, WarningCircle } from "@phosphor-icons/react";

import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Toggle } from "@/components/ui/Toggle";
import { useSettings } from "@/context/SettingsContext";
import { useConfig } from "@/hooks/useServerData";
import { CUSTOM_MODEL_VALUE } from "@/lib/llm";
import type { Provider } from "@/lib/types";
import { stripLeadingSymbols } from "@/lib/utils";

const KEY_META: Record<Provider, { label: string; link: string; optional: boolean }> = {
  gemini: {
    label: "Google AI API Key",
    link: "https://aistudio.google.com/app/apikey",
    optional: false,
  },
  groq: {
    label: "Groq API Key",
    link: "https://console.groq.com",
    optional: false,
  },
  hf: {
    label: "Endpoint token (optional)",
    link: "",
    optional: true,
  },
  openai: {
    label: "API key (optional for local servers)",
    link: "",
    optional: true,
  },
};

/**
 * Model dropdown + provider hint + the single dynamic API-key field. The
 * "Custom" entry swaps the hint for base-URL and model-name fields, so any
 * OpenAI-compatible provider can be used without a server-side change.
 */
export function ModelSelector() {
  const { data: config } = useConfig();
  const {
    selectedModel,
    setSelectedModel,
    provider,
    keys,
    setKey,
    customLlm,
    setCustomLlm,
    llmReady,
    llmMissing,
    followupsEnabled,
    setFollowupsEnabled,
  } = useSettings();

  const models = config?.models ?? [];
  const current = models.find((m) => m.id === selectedModel);
  const isCustom = provider === "openai";
  const meta = KEY_META[provider];
  const keyValue = keys[provider];

  const options = [
    ...models.map((m) => ({ value: m.id, label: stripLeadingSymbols(m.label) })),
    { value: CUSTOM_MODEL_VALUE, label: "Custom (OpenAI-compatible)" },
  ];

  return (
    <div className="space-y-3">
      <Select
        id="llm-model"
        label="Model"
        options={options}
        value={isCustom ? CUSTOM_MODEL_VALUE : selectedModel}
        onChange={(e) => setSelectedModel(e.target.value)}
      />

      {isCustom ? (
        <div className="space-y-3">
          <Input
            id="custom-llm-base-url"
            label="Base URL"
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="https://api.openai.com/v1"
            value={customLlm.baseUrl}
            onChange={(e) => setCustomLlm({ baseUrl: e.target.value })}
          />
          <Input
            id="custom-llm-model"
            label="Model name"
            autoComplete="off"
            spellCheck={false}
            placeholder="gpt-4o-mini, llama3.1, …"
            value={customLlm.model}
            onChange={(e) => setCustomLlm({ model: e.target.value })}
          />
          <p className="text-[11px] leading-snug text-muted">
            Any server that speaks the OpenAI chat-completions API — OpenAI, OpenRouter,
            Together, Ollama, LM Studio, vLLM. Requests are sent from the ResearchRAG server, so a{" "}
            <code className="font-mono text-zinc-400">localhost</code> URL means the server's
            machine, not yours.
          </p>
        </div>
      ) : (
        current?.hint_text && (
          <p className="text-[11px] text-muted">{stripLeadingSymbols(current.hint_text)}</p>
        )
      )}

      <Input
        id="llm-api-key"
        label={meta.label}
        type="password"
        autoComplete="off"
        placeholder="Paste your API key here…"
        value={keyValue}
        onChange={(e) => setKey(provider, e.target.value)}
      />
      <p className="flex items-center gap-1.5 text-[11px]">
        <Key className="h-3.5 w-3.5 shrink-0 text-muted" />
        {!llmReady ? (
          <span className="flex items-start gap-1 text-amber-400">
            <WarningCircle className="mt-px h-3.5 w-3.5 shrink-0" />
            {isCustom ? llmMissing : "Key not set"}
          </span>
        ) : keyValue ? (
          <span className="flex items-center gap-1 text-accent">
            <CheckCircle className="h-3.5 w-3.5" weight="fill" /> Key active
          </span>
        ) : (
          <span className="flex items-center gap-1 text-accent">
            <CheckCircle className="h-3.5 w-3.5" weight="fill" />
            {meta.optional ? "Ready — no key needed" : "Key active"}
          </span>
        )}
        {meta.link && (
          <a
            href={meta.link}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 shrink-0 text-accent transition-colors hover:text-accent-soft"
          >
            Get key
          </a>
        )}
      </p>

      <Toggle
        checked={followupsEnabled}
        onChange={setFollowupsEnabled}
        icon={<ChatsCircle className="h-4 w-4" />}
        label="Follow-up questions"
        hint="Suggests next questions after each answer — one extra LLM call."
      />
    </div>
  );
}
