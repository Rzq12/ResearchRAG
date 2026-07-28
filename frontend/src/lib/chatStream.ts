// SSE client for the streaming chat endpoint.
//
// EventSource only supports GET, but /api/chat/stream is a POST carrying the
// api_key + chat history in its body, so we read the stream manually from
// fetch()'s ReadableStream and parse SSE frames ("event:"/"data:" blocks).

import { API_BASE_URL } from "./api";
import type { ChatMessage, ChatSource, Reference, WhereFilter } from "./types";

export interface ChatStreamMeta {
  references: Reference[];
  openalex_used: number;
  uploaded_used: number;
  reasoning: string;
  source: ChatSource;
}

export interface ChatStreamHandlers {
  onToken: (text: string) => void;
  onMeta: (meta: ChatStreamMeta) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

export interface ChatStreamParams {
  query: string;
  chatHistory: Pick<ChatMessage, "role" | "content">[];
  apiKey: string;
  model: string;
  userId: string | null;
  where: WhereFilter;
  kbOnly: boolean;
  signal?: AbortSignal;
}

export async function streamChat(
  params: ChatStreamParams,
  handlers: ChatStreamHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: params.signal,
      body: JSON.stringify({
        query: params.query,
        chat_history: params.chatHistory,
        api_key: params.apiKey,
        model: params.model,
        user_id: params.userId,
        where: params.where,
        kb_only: params.kbOnly,
      }),
    });
  } catch {
    handlers.onError(`Cannot reach the API at ${API_BASE_URL}. Is the backend running?`);
    handlers.onDone();
    return;
  }

  if (!res.ok || !res.body) {
    handlers.onError(`Chat request failed (${res.status}).`);
    handlers.onDone();
    return;
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
      case "done":
        handlers.onDone();
        break;
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
      handlers.onDone();
    }
  }
}
