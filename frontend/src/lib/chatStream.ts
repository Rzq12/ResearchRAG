// SSE client for the streaming chat endpoint.
//
// EventSource only supports GET, but /api/chat/stream is a POST carrying the
// api_key + chat history in its body, so we read the stream manually from
// fetch()'s ReadableStream and parse SSE frames ("event:"/"data:" blocks).

import { API_BASE_URL } from "./api";
import { clearSession, getSession, isAccessTokenStale, refreshSession } from "./authStore";
import type { ChatMessage, ChatSource, Reference, WhereFilter } from "./types";

export interface ChatStreamMeta {
  references: Reference[];
  openalex_used: number;
  uploaded_used: number;
  reasoning: string;
  source: ChatSource;
}

/**
 * Completion is signalled by the returned promise settling, not by a callback.
 * A separate `onDone` was a second completion channel that every early return
 * had to remember to fire — and the one path that could not fire it (abort)
 * was exactly the path that left the caller's "streaming" flag stuck on.
 */
export interface ChatStreamHandlers {
  onToken: (text: string) => void;
  onMeta: (meta: ChatStreamMeta) => void;
  onError: (message: string) => void;
}

export interface ChatStreamParams {
  query: string;
  chatHistory: Pick<ChatMessage, "role" | "content">[];
  apiKey: string;
  model: string;
  where: WhereFilter;
  kbOnly: boolean;
  signal?: AbortSignal;
}

export async function streamChat(
  params: ChatStreamParams,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const payload = JSON.stringify({
    query: params.query,
    chat_history: params.chatHistory,
    api_key: params.apiKey,
    model: params.model,
    where: params.where,
    kb_only: params.kbOnly,
  });

  // Refresh proactively — a stream that 401s mid-flight cannot be replayed
  // cleanly, so it is much better to renew before opening it.
  let session = getSession();
  if (session && isAccessTokenStale(session)) {
    session = await refreshSession(API_BASE_URL);
  }

  const open = (token?: string) =>
    fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: params.signal,
      body: payload,
    });

  let res: Response;
  try {
    res = await open(session?.accessToken);
    if (res.status === 401 && getSession()) {
      const refreshed = await refreshSession(API_BASE_URL);
      if (refreshed) {
        res = await open(refreshed.accessToken);
      } else {
        clearSession();
        handlers.onError("Your session has expired. Please sign in again.");
        return;
      }
    }
  } catch {
    handlers.onError(`Cannot reach the API at ${API_BASE_URL}. Is the backend running?`);    return;
  }

  if (res.status === 429) {
    handlers.onError("You're sending messages too quickly. Please wait a moment and retry.");    return;
  }

  // The backend sleeps when idle; while it reloads its models the proxy returns
  // 502/503/504. That is a wait, not a failure — say so rather than showing a
  // raw gateway error.
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    handlers.onError(
      "The server is waking up and loading its models. Give it a minute, then send your question again.",
    );    return;
  }

  if (!res.ok || !res.body) {
    let detail = `Chat request failed (${res.status}).`;
    try {
      detail = (await res.json())?.message || detail;
    } catch {
      /* non-JSON body */
    }
    handlers.onError(detail);    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (frame: string) => {
    // A frame is a block separated by a blank line, e.g.
    //   event: token\ndata: {"text":"..."}
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return;
    let payload: unknown;
    try {
      payload = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }

    switch (event) {
      case "token":
        handlers.onToken((payload as { text: string }).text ?? "");
        break;
      case "meta":
        handlers.onMeta(payload as ChatStreamMeta);
        break;
      case "error":
        handlers.onError((payload as { message: string }).message ?? "Unknown error.");
        break;
      // "done" needs no case: the frame simply ends the stream, and the caller
      // learns that from the promise settling.
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      // SSE frames are separated by a blank line ("\n\n").
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (frame.trim()) dispatch(frame);
      }
    }
    if (buffer.trim()) dispatch(buffer);
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError("Connection interrupted while streaming the answer.");
    }
  }
}
