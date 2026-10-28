import { describe, expect, it } from "vitest";

import { MISSING_KEY_MESSAGE, isHttpUrl, providerFromModel, resolveLlm } from "./llm";

const NO_CUSTOM = { baseUrl: "", model: "" };

describe("providerFromModel", () => {
  it("routes by prefix, mirroring app.llm_client.get_provider", () => {
    expect(providerFromModel("openai:gpt-4o-mini")).toBe("openai");
    expect(providerFromModel("hf:me/model")).toBe("hf");
    expect(providerFromModel("gemini-3.5-flash")).toBe("gemini");
    // Groq-hosted OpenAI models use a slash, not the colon prefix.
    expect(providerFromModel("openai/gpt-oss-120b")).toBe("groq");
  });
});

describe("isHttpUrl", () => {
  it.each(["https://api.openai.com/v1", "http://localhost:11434/v1"])("accepts %s", (url) => {
    expect(isHttpUrl(url)).toBe(true);
  });

  it.each(["localhost:11434", "ftp://x.org", "https://", ""])("rejects %s", (url) => {
    expect(isHttpUrl(url)).toBe(false);
  });
});

describe("resolveLlm", () => {
  it("uses the key of the selected model's provider", () => {
    const r = resolveLlm("gemini-3.5-flash", { gemini: "g-key", groq: "q-key" }, NO_CUSTOM);
    expect(r).toEqual({
      params: { api_key: "g-key", model: "gemini-3.5-flash" },
      ready: true,
      missing: null,
    });
  });

  it("is not ready without a key for a hosted provider", () => {
    const r = resolveLlm("llama-3.1-8b-instant", { gemini: "g-key" }, NO_CUSTOM);
    expect(r.ready).toBe(false);
    expect(r.missing).toBe(MISSING_KEY_MESSAGE);
  });

  it("builds the custom model id and base URL, key optional", () => {
    const r = resolveLlm("openai:", {}, { baseUrl: " http://localhost:11434/v1 ", model: "llama3.1" });
    expect(r).toEqual({
      params: { api_key: "", model: "openai:llama3.1", base_url: "http://localhost:11434/v1" },
      ready: true,
      missing: null,
    });
  });

  it("never borrows another provider's key for the custom endpoint", () => {
    const r = resolveLlm(
      "openai:",
      { groq: "q-key", gemini: "g-key" },
      { baseUrl: "https://example.com/v1", model: "m" },
    );
    expect(r.params.api_key).toBe("");
  });

  it("explains what is missing for an incomplete custom endpoint", () => {
    expect(resolveLlm("openai:", {}, { baseUrl: "", model: "m" }).missing).toMatch(/base url/i);
    expect(resolveLlm("openai:", {}, { baseUrl: "example.com", model: "m" }).missing).toMatch(
      /http/i,
    );
  });
});
