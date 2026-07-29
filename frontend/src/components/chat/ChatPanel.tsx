import { useCallback, useEffect, useRef, useState } from "react";
import { DownloadSimple, Eraser, Flask } from "@phosphor-icons/react";

import { ChatInput } from "./ChatInput";
import { MessageBubble } from "./MessageBubble";
import { Suggestions } from "./Suggestions";
import { useSettings } from "@/context/SettingsContext";
import { useToast } from "@/context/ToastContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useKbStats } from "@/hooks/useServerData";
import { streamChat } from "@/lib/chatStream";
import type { ChatMessage } from "@/lib/types";

export function ChatPanel() {
  const { selectedModel, activeApiKey, whereFilter, kbOnly } = useSettings();
  const toast = useToast();
  const { suggestions, pendingQuery, setPendingQuery } = useWorkspace();
  const { data: stats } = useKbStats();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const patchLast = useCallback((patch: Partial<ChatMessage>) => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const next = [...prev];
      next[next.length - 1] = { ...next[next.length - 1], ...patch };
      return next;
    });
  }, []);

  const appendToLast = useCallback((text: string) => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, content: last.content + text };
      return next;
    });
  }, []);

  const send = useCallback(
    (text: string) => {
      if (streaming) return;
      if (!activeApiKey) {
        toast.error("Set an API key in the sources panel for the selected model first.");
        return;
      }
      if (!stats || stats.total_chunks === 0) {
        toast.warning("Knowledge base is empty — search OpenAlex or upload a PDF first.");
        return;
      }

      const history = messages
        .filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: m.content }));

      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "" },
      ]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      streamChat(
        {
          query: text,
          chatHistory: history,
          apiKey: activeApiKey,
          model: selectedModel,
          where: whereFilter,
          kbOnly,
          signal: controller.signal,
        },
        {
          onToken: (t) => appendToLast(t),
          onMeta: (meta) =>
            patchLast({
              references: meta.references,
              reasoning: meta.reasoning,
              source: meta.source,
            }),
          onError: (message) => patchLast({ content: message, error: true }),
          onDone: () => {
            setStreaming(false);
            abortRef.current = null;
          },
        },
      );
    },
    [streaming, activeApiKey, stats, messages, selectedModel, whereFilter, kbOnly, appendToLast, patchLast, toast],
  );

  useEffect(() => {
    if (pendingQuery && !streaming) {
      const q = pendingQuery;
      setPendingQuery(null);
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuery, streaming]);

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    if (messages[messages.length - 1]?.content === "") {
      patchLast({ content: "_(stopped)_" });
    }
  };

  const clearChat = () => setMessages([]);

  const exportChat = () => {
    if (!messages.length) return;
    const lines = ["# ResearchRAG — Chat Export\n"];
    for (const m of messages) {
      lines.push(`### ${m.role === "user" ? "User" : "Assistant"}\n`);
      lines.push(`${m.content}\n`);
      if (m.references?.length) {
        lines.push("**References:**\n");
        m.references.forEach((r, i) =>
          lines.push(`${i + 1}. ${r.url ? `[${r.title}](${r.url})` : r.title} (${r.published})\n`),
        );
      }
      lines.push("---\n");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "chat_export.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      {/* Section header — no full-width rule, just air. */}
      <div className="flex shrink-0 items-baseline justify-between gap-6 px-2 pb-6 pt-10">
        <div className="min-w-0">
          <h1 className="text-[26px] font-medium tracking-[-0.035em] text-white">
            Research assistant
          </h1>
          <p className="mt-1.5 truncate text-[13px] text-muted">
            {stats
              ? `${stats.total_chunks.toLocaleString()} chunks · answers cite their source passage`
              : "Answers cite their source passage"}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {/* The labels collapse below `sm`, so both carry an explicit
              accessible name — otherwise they surface as unnamed buttons. */}
          <button
            onClick={exportChat}
            disabled={!messages.length}
            title="Export thread"
            aria-label="Export thread"
            className="flex items-center gap-2 whitespace-nowrap rounded-full border border-white/[0.08] px-4 py-2 text-[12.5px] text-zinc-400 transition-all duration-[400ms] ease-smooth hover:bg-white/[0.05] hover:text-zinc-100 active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <DownloadSimple className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Export thread</span>
          </button>
          <button
            onClick={clearChat}
            disabled={!messages.length}
            title="Clear thread"
            aria-label="Clear thread"
            className="flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-[12.5px] text-muted transition-all duration-[400ms] ease-smooth hover:text-red-300 active:scale-[0.98] disabled:opacity-40 disabled:hover:text-muted"
          >
            <Eraser className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Clear</span>
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-8 overflow-y-auto scrollbar-thin px-2 pb-6">
        {suggestions.length > 0 && (
          <Suggestions suggestions={suggestions} onPick={setPendingQuery} disabled={streaming} />
        )}

        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          messages.map((m, i) => (
            <MessageBubble
              key={i}
              message={m}
              streaming={streaming && i === messages.length - 1 && m.role === "assistant"}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 px-2">
        <ChatInput onSend={send} onStop={stop} streaming={streaming} />
        <div className="flex items-center gap-3 px-3 pb-2 text-[11.5px] text-subtle">
          <span className="truncate">{selectedModel}</span>
          <span className="text-muted">·</span>
          <span className="whitespace-nowrap">
            {kbOnly ? "grounded in library only" : "web fallback enabled"}
          </span>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 py-16 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl border border-accent/25 bg-accent/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
        <Flask className="h-6 w-6 text-accent" />
      </div>
      <div>
        <p className="text-[17px] font-medium tracking-tight text-zinc-100">
          Ask your library a question
        </p>
        <p className="mx-auto mt-2 max-w-[42ch] text-[13.5px] leading-relaxed text-muted">
          Pull papers from OpenAlex or drop a PDF into the rail, then ask. Answers stream in with the
          passage they came from attached.
        </p>
      </div>
    </div>
  );
}
