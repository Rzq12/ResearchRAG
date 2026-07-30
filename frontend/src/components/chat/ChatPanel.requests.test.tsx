/**
 * Request-budget regression tests for the chat panel.
 *
 * The defect these guard against: the React client burned far more upstream LLM
 * quota than the Streamlit client against the identical backend, endpoint, key
 * and model. Streamlit cannot reproduce it because `st.chat_input` serialises
 * turns through a server-side rerun — a second submit is impossible while the
 * first is still streaming. The React composer had no such interlock.
 *
 * Every test here asserts a COUNT of requests, not just that a request happened.
 * That is the only assertion shape that can catch quota amplification.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "./ChatPanel";
import { SettingsProvider } from "@/context/SettingsContext";
import { ToastProvider } from "@/context/ToastContext";
import { WorkspaceProvider } from "@/context/WorkspaceContext";
import { AuthProvider } from "@/context/AuthContext";
import { clearSession, setSession } from "@/lib/authStore";

/** Requests recorded by the fetch stub, in order. */
let calls: string[] = [];
/** Resolvers that keep each chat stream open until the test closes it. */
let openStreams: Array<() => void> = [];

function chatCallCount(): number {
  return calls.filter((u) => u.includes("/api/chat/stream")).length;
}

/**
 * An SSE body that stays open until the test releases it, so a test can act
 * while a stream is genuinely in flight — which is exactly the window the
 * duplicate-submit bug lived in.
 */
function pendingSseResponse(): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(encoder.encode('event: token\ndata: {"text":"hi"}\n\n'));
      openStreams.push(() => {
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      });
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  calls = [];
  openStreams = [];

  // Via setSession, not localStorage: authStore caches the session in a module
  // variable read at import time, so writing the key directly would be ignored.
  setSession({
    accessToken: "access-token",
    refreshToken: "refresh-token",
    userId: "u1",
    displayName: "Tester",
    expiresAt: Date.now() + 60 * 60 * 1000,
  });
  // A key must be present for the selected model's provider or send() bails
  // before it ever reaches the network.
  localStorage.setItem(
    "rr_keys",
    JSON.stringify({ groq: "", gemini: "test-key", hf: "", openalex: "" }),
  );
  localStorage.setItem("rr_model", JSON.stringify("gemini-3.5-flash"));

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.includes("/api/documents/stats")) {
        return jsonResponse({ total_chunks: 128, documents: 4 });
      }
      if (url.includes("/api/chat/stream")) {
        return pendingSseResponse();
      }
      return jsonResponse({});
    }),
  );
});

afterEach(() => {
  // vitest.config.ts sets no `globals`, so testing-library's auto-cleanup hook
  // is never registered — without this, each test renders into a document that
  // still holds the previous test's tree and every query matches twice.
  cleanup();
  vi.unstubAllGlobals();
  clearSession();
  localStorage.clear();
});

function renderPanel(strict = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const tree = (
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
    </QueryClientProvider>
  );
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
}

/** Wait until the KB-stats query has landed, so send() passes its guard. */
async function waitForStats() {
  await waitFor(() => expect(screen.getByText(/128 chunks/)).toBeInTheDocument());
}

function composer() {
  return screen.getByPlaceholderText("Ask about your papers…") as HTMLTextAreaElement;
}

/** Type into the textarea the way a user would. */
async function type(text: string) {
  const ta = composer();
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )!.set!;
    setter.call(ta, text);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("ChatPanel request budget", () => {
  it("sends exactly one chat request per submitted question", async () => {
    renderPanel();
    await waitForStats();
    await type("why is adjusted IR better?");

    await act(async () => {
      screen.getByRole("button", { name: /ask/i }).dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });

    await waitFor(() => expect(chatCallCount()).toBe(1));
    expect(chatCallCount()).toBe(1);
  });

  it("collapses a rapid double-click into a single chat request", async () => {
    renderPanel();
    await waitForStats();
    await type("why is adjusted IR better?");

    // Two clicks dispatched inside ONE act() — React batches them, so both
    // handlers observe the pre-update `streaming === false`. This is a real
    // double-click / Enter-mash, and it used to open two streams, doubling the
    // upstream LLM spend for a single question.
    await act(async () => {
      const btn = screen.getByRole("button", { name: /ask/i });
      btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await waitFor(() => expect(chatCallCount()).toBeGreaterThan(0));
    expect(chatCallCount()).toBe(1);
  });

  it("does not open a second stream while one is still in flight", async () => {
    renderPanel();
    await waitForStats();
    await type("first question");

    await act(async () => {
      screen.getByRole("button", { name: /ask/i }).dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });
    await waitFor(() => expect(chatCallCount()).toBe(1));

    // The first stream is deliberately still open here.
    await type("second question");
    await act(async () => {
      const btn = screen.queryByRole("button", { name: /ask/i });
      btn?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(chatCallCount()).toBe(1);
  });

  it("allows a new question after Stop, and the abandoned stream cannot unlatch it", async () => {
    renderPanel();
    await waitForStats();
    await type("first question");

    await act(async () => {
      screen.getByRole("button", { name: /ask/i }).dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });
    await waitFor(() => expect(chatCallCount()).toBe(1));

    await act(async () => {
      screen.getByRole("button", { name: /stop/i }).dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });

    // Stop must release the latch so the composer is usable again.
    await type("second question");
    await act(async () => {
      screen.getByRole("button", { name: /ask/i }).dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });
    await waitFor(() => expect(chatCallCount()).toBe(2));

    // The second turn is still in flight, so a third submit is still refused —
    // proving the abandoned first stream did not clear the new turn's latch.
    await type("third question");
    await act(async () => {
      screen.queryByRole("button", { name: /ask/i })?.dispatchEvent(
        new MouseEvent("click", { bubbles: true }),
      );
    });
    expect(chatCallCount()).toBe(2);
  });

  it("issues no chat request from mounting under StrictMode", async () => {
    renderPanel(true);
    await waitForStats();
    expect(chatCallCount()).toBe(0);
  });

  it("fetches KB stats once on mount, even under StrictMode", async () => {
    renderPanel(true);
    await waitForStats();
    const statsCalls = calls.filter((u) => u.includes("/api/documents/stats"));
    expect(statsCalls).toHaveLength(1);
  });
});
