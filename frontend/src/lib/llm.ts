// Which model/key/endpoint an LLM request carries, resolved from the settings.
// Kept free of React so the rules can be unit-tested directly.

import type { Provider } from "./types";

/** Dropdown value for the user-configured OpenAI-compatible endpoint. */
export const CUSTOM_MODEL_VALUE = "openai:";

/** User-supplied OpenAI-compatible endpoint (OpenAI, OpenRouter, Ollama, …). */
export interface CustomLlm {
  baseUrl: string;
  model: string;
}

/** Fields every LLM-backed request sends — mirrors api/schemas.py. */
export interface LlmParams {
  api_key: string;
  model: string;
  base_url?: string;
}

export interface ResolvedLlm {
  params: LlmParams;
  /** False when a request would be rejected for missing configuration. */
  ready: boolean;
  /** What to tell the user when `ready` is false. */
  missing: string | null;
}

export const MISSING_KEY_MESSAGE =
  "Set an API key in the sources panel for the selected model first.";

/** Mirror of app.llm_client.get_provider — route provider from model id. */
export function providerFromModel(model: string): Provider {
  if (model.startsWith("openai:")) return "openai";
  if (model.startsWith("hf:")) return "hf";
  if (model.startsWith("gemini")) return "gemini";
  return "groq";
}

/** Same shape check as the backend's base_url validator. */
export function isHttpUrl(value: string): boolean {
  return /^https?:\/\/[^\s/?#]+\S*$/i.test(value.trim());
}

export function resolveLlm(
  selectedModel: string,
  keys: Partial<Record<Provider, string>>,
  custom: CustomLlm,
): ResolvedLlm {
  const provider = providerFromModel(selectedModel);
  const api_key = (keys[provider] ?? "").trim();

  if (provider === "openai") {
    const baseUrl = custom.baseUrl.trim();
    const model = custom.model.trim();
    const params: LlmParams = { api_key, model: `openai:${model}`, base_url: baseUrl };
    if (!baseUrl || !model) {
      return {
        params,
        ready: false,
        missing: "Set the base URL and model name for your OpenAI-compatible provider.",
      };
    }
    if (!isHttpUrl(baseUrl)) {
      return { params, ready: false, missing: "The base URL must start with http:// or https://." };
    }
    // The key stays optional: local servers such as Ollama run without one.
    return { params, ready: true, missing: null };
  }

  const params: LlmParams = { api_key, model: selectedModel };
  // Self-hosted endpoints fall back to the server's own token.
  if (provider === "hf" || api_key) return { params, ready: true, missing: null };
  return { params, ready: false, missing: MISSING_KEY_MESSAGE };
}
