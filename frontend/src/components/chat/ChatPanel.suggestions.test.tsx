/**
 * Suggested questions, follow-ups and the custom OpenAI-compatible provider,
 * exercised through the real chat panel with a stubbed fetch.
 *
 * Like ChatPanel.requests.test.tsx, assertions count requests: every one of
 * these features is an extra LLM call, so "fires once, only when useful" is
 * the property worth pinning down.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";
import { AuthProvider } from "@/context/AuthContext";
import { SettingsProvider } from "@/context/SettingsContext";
import { ToastProvider } from "@/context/ToastContext";
import { WorkspaceProvider } from "@/context/WorkspaceContext";
import { clearSession, setSession } from "@/lib/authStore";

interface Call {
  url: string;
  body: Record<string, unknown> | null;
}

let calls: Call[] = [];
/** What the chat stream answers with; swapped per test. */
let streamBody: () => string;
let suggestionsReply: string[] = [];
let followupsReply: string[] = [];

const callsTo = (path: string) => calls.filter((c) => c.url.endsWith(path));

function sse(events: [string, unknown][]): string {
  return events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
}

function answeredStream(source = "kb"): string {
  return sse([
    ["token", { text: "LoRA freezes the base weights [1]." }],
    ["meta", { references: [], openalex_used: 0, uploaded_used: 1, reasoning: "", source }],
    ["done", {}],
  ]);
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  calls = [];
  streamBody = () => answeredStream();
  suggestionsReply = ["What rank does LoRA use for GPT-3?"];
  followupsReply = ["How does LoRA compare to adapters?"];

  setSession({
    accessToken: "access-token",
    refreshToken: "refresh-token",
    userId: "u1",
    displayName: "Tester",
    expiresAt: Date.now() + 60 * 60 * 1000,
  });
  localStorage.setItem(
    "rr_keys",
    JSON.stringify({ groq: "", gemini: "test-key", hf: "", openalex: "" }),
  );
  localStorage.setItem("rr_model", JSON.stringify("gemini-3.5-flash"));

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      calls.push({ url, body });
      if (url.includes("/api/documents/stats")) {
        return jsonResponse({ total_chunks: 128, documents: 4 });
      }
      if (url.includes("/api/chat/stream")) {
        return new Response(streamBody(), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      if (url.endsWith("/api/suggestions/followups")) {
        return jsonResponse({ suggestions: followupsReply });
      }
      if (url.endsWith("/api/suggestions")) {
        return jsonResponse({ suggestions: suggestionsReply });
      }
      return jsonResponse({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearSession();
  localStorage.clear();
});

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <SettingsProvider>
            <WorkspaceProvider>
              <ChatPanel />
            </WorkspaceProvider>
          </SettingsProvider>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

async function waitForStats() {
  await waitFor(() => expect(screen.getByText(/128 chunks/)).toBeInTheDocument());
}

async function click(name: string | RegExp) {
  await act(async () => {
    screen.getByRole("button", { name }).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

async function ask(text: string) {
  const ta = screen.getByPlaceholderText("Ask about your papers…") as HTMLTextAreaElement;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(ta, text);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await click(/ask/i);
}

describe("starter suggestions", () => {
  it("restores saved suggestions for the signed-in user without a request", async () => {
    localStorage.setItem("rr_suggestions:u1", JSON.stringify(["Saved question about LoRA?"]));
    renderPanel();
    await waitForStats();

    expect(screen.getByRole("button", { name: "Saved question about LoRA?" })).toBeInTheDocument();
    expect(callsTo("/api/suggestions")).toHaveLength(0);
  });

  it("asks a picked suggestion once and removes its chip", async () => {
    localStorage.setItem("rr_suggestions:u1", JSON.stringify(["Saved question about LoRA?"]));
    renderPanel();
    await waitForStats();

    await click("Saved question about LoRA?");

    await waitFor(() => expect(callsTo("/api/chat/stream")).toHaveLength(1));
    expect(callsTo("/api/chat/stream")[0].body?.query).toBe("Saved question about LoRA?");
    expect(screen.queryByRole("button", { name: "Saved question about LoRA?" })).toBeNull();
  });

  it("regenerate excludes the questions already on screen", async () => {
    localStorage.setItem("rr_suggestions:u1", JSON.stringify(["Saved question about LoRA?"]));
    renderPanel();
    await waitForStats();

    await click(/regenerate suggestions/i);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "What rank does LoRA use for GPT-3?" }),
      ).toBeInTheDocument(),
    );
    const [req] = callsTo("/api/suggestions");
    expect(req.body?.exclude).toEqual(["Saved question about LoRA?"]);
    expect(req.body?.language).toBe("id");
    expect(req.body?.model).toBe("gemini-3.5-flash");
  });

  it("switching language regenerates once in that language", async () => {
    renderPanel();
    await waitForStats();

    await click("EN");

    await waitFor(() => expect(callsTo("/api/suggestions")).toHaveLength(1));
    expect(callsTo("/api/suggestions")[0].body?.language).toBe("en");
  });

  it("shows the server's error message instead of an empty panel", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push({ url, body: null });
      if (url.includes("/api/documents/stats")) {
        return jsonResponse({ total_chunks: 128, documents: 4 });
      }
      return new Response(
        JSON.stringify({ message: "Kuota API tercapai (rate limit).", status_code: 502 }),
        { status: 502, headers: { "Content-Type": "application/json" } },
      );
    });
    renderPanel();
    await waitForStats();

    await click(/suggest questions from my library/i);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/rate limit/i));
  });
});

describe("follow-up questions", () => {
  it("requests follow-ups once after a completed answer and renders them", async () => {
    renderPanel();
    await waitForStats();

    await ask("What is LoRA?");

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "How does LoRA compare to adapters?" }),
      ).toBeInTheDocument(),
    );
    const followups = callsTo("/api/suggestions/followups");
    expect(followups).toHaveLength(1);
    expect(followups[0].body?.question).toBe("What is LoRA?");
    expect(followups[0].body?.answer).toBe("LoRA freezes the base weights [1].");
  });

  it("skips follow-ups when the stream reports an error", async () => {
    streamBody = () => sse([["error", { category: "auth", message: "Bad key" }], ["done", {}]]);
    renderPanel();
    await waitForStats();

    await ask("What is LoRA?");

    await waitFor(() => expect(screen.getByText("Bad key")).toBeInTheDocument());
    expect(callsTo("/api/suggestions/followups")).toHaveLength(0);
  });

  it("skips follow-ups when nothing relevant was found", async () => {
    streamBody = () => answeredStream("none");
    renderPanel();
    await waitForStats();

    await ask("Unrelated question?");

    await waitFor(() => expect(callsTo("/api/chat/stream")).toHaveLength(1));
    await act(async () => {});
    expect(callsTo("/api/suggestions/followups")).toHaveLength(0);
  });

  it("makes no follow-up request when the user turned them off", async () => {
    localStorage.setItem("rr_followups", JSON.stringify(false));
    renderPanel();
    await waitForStats();

    await ask("What is LoRA?");

    await waitFor(() =>
      expect(screen.getByText("LoRA freezes the base weights [1].")).toBeInTheDocument(),
    );
    await act(async () => {});
    expect(callsTo("/api/suggestions/followups")).toHaveLength(0);
  });
});

describe("custom OpenAI-compatible provider", () => {
  it("sends the custom model and base URL, with no key required", async () => {
    localStorage.setItem("rr_model", JSON.stringify("openai:"));
    localStorage.setItem(
      "rr_custom_llm",
      JSON.stringify({ baseUrl: "http://localhost:11434/v1", model: "llama3.1" }),
    );
    localStorage.setItem("rr_followups", JSON.stringify(false));
    renderPanel();
    await waitForStats();

    await ask("What is LoRA?");

    await waitFor(() => expect(callsTo("/api/chat/stream")).toHaveLength(1));
    const { body } = callsTo("/api/chat/stream")[0];
    expect(body?.model).toBe("openai:llama3.1");
    expect(body?.base_url).toBe("http://localhost:11434/v1");
    expect(body?.api_key).toBe("");
  });

  it("refuses to send while the custom endpoint is incomplete", async () => {
    localStorage.setItem("rr_model", JSON.stringify("openai:"));
    localStorage.setItem("rr_custom_llm", JSON.stringify({ baseUrl: "", model: "llama3.1" }));
    renderPanel();
    await waitForStats();

    await ask("What is LoRA?");

    await waitFor(() =>
      expect(screen.getByText(/set the base url and model name/i)).toBeInTheDocument(),
    );
    expect(callsTo("/api/chat/stream")).toHaveLength(0);
  });
});
