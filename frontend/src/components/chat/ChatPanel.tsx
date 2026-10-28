import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { DownloadSimple, Eraser, Flask } from "@phosphor-icons/react";

import { ChatInput } from "./ChatInput";
import { MessageBubble } from "./MessageBubble";
import { FollowUps, Suggestions } from "./Suggestions";
import { useSettings } from "@/context/SettingsContext";
import { useToast } from "@/context/ToastContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useKbStats } from "@/hooks/useServerData";
import { getFollowups } from "@/lib/api";
import { streamChat } from "@/lib/chatStream";
import type { ChatMessage, ChatSource } from "@/lib/types";

export function ChatPanel() {
  const {
    llm,
    llmReady,
    llmMissing,
    whereFilter,
    kbOnly,
    followupsEnabled,
    suggestionLanguage,
    setSuggestionLanguage,
  } = useSettings();
  const toast = useToast();
  const {
    suggestions,
    suggestionStatus,
    suggestionError,
    refreshSuggestions,
    markSuggestionUsed,
  } = useWorkspace();
  const { data: stats } = useKbStats();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  /**
   * Synchronous re-entry latch.
   *
   * `streaming` cannot guard this on its own: setState is not visible to another
   * handler in the same event batch, so a double-click or a mashed Enter fired
   * two streams for one question — and each question costs three upstream LLM
   * calls (HyDE ×2 + the completion), so the duplicate burned six. This ref
   * flips before anything async, closing that window.
   */
  const inFlightRef = useRef(false);

  /**
   * Mirror of `messages` for reading history at send time. Keeping the history
   * read off state means `send` no longer changes identity on every token that
   * streams in.
   */
  const messagesRef = useRef<ChatMessage[]>(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

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

  /**
   * Single place that ends a turn; safe to call more than once.
   *
   * Takes the controller that owns the turn so a superseded stream cannot clear
   * a newer one's state: stopping a turn and immediately asking again means the
   * abandoned stream's settle handler still runs, and without this check it
   * would unlatch the turn that had just started.
   */
  const finish = useCallback((controller: AbortController) => {
    if (abortRef.current !== controller) return;
    inFlightRef.current = false;
    abortRef.current = null;
    setStreaming(false);
  }, []);

  /** Source of the turn ids that follow-up results are matched against. */
  const turnSeqRef = useRef(0);

  /**
   * Fetch follow-ups for a finished turn and attach them to that turn's
   * message. Matched by id, not position: the user may have cleared the thread
   * or asked again before the follow-ups came back.
   */
  const loadFollowups = useCallback(
    (turnId: string, question: string, answer: string) => {
      getFollowups(llm, { question, answer })
        .then((res) => {
          const followups = res.suggestions ?? [];
          if (!followups.length) return;
          setMessages((prev) =>
            prev.map((m) => (m.turnId === turnId ? { ...m, followups } : m)),
          );
        })
        // Follow-ups are an extra; a failure leaves the answer as it is.
        .catch(() => undefined);
    },
    [llm],
  );

  /** Returns true when the question was actually sent. */
  const send = useCallback(
    (text: string): boolean => {
      // Latch first — before any branch that can yield to the event loop.
      if (inFlightRef.current) return false;

      if (!llmReady) {
        toast.error(llmMissing ?? "Configure a model in the sources panel first.");
        return false;
      }
      if (!stats || stats.total_chunks === 0) {
        toast.warning("Knowledge base is empty — search OpenAlex or upload a PDF first.");
        return false;
      }

      inFlightRef.current = true;
      const turnId = `turn-${++turnSeqRef.current}`;

      // Drop failed turns AND the question that produced them: replaying a
      // user message whose answer errored just re-asks it as phantom context.
      const history: Pick<ChatMessage, "role" | "content">[] = [];
      for (const m of messagesRef.current) {
        if (m.error) {
          if (history[history.length - 1]?.role === "user") history.pop();
          continue;
        }
        history.push({ role: m.role, content: m.content });
      }

      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "", turnId },
      ]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      // Tracked locally: state has not necessarily flushed when the stream settles.
      let answer = "";
      let source: ChatSource | undefined;
      let failed = false;

      streamChat(
        {
          query: text,
          chatHistory: history,
          llm,
          where: whereFilter,
          kbOnly,
          signal: controller.signal,
        },
        {
          onToken: (t) => {
            answer += t;
            appendToLast(t);
          },
          onMeta: (meta) => {
            source = meta.source;
            patchLast({
              references: meta.references,
              reasoning: meta.reasoning,
              source: meta.source,
            });
          },
          onError: (message) => {
            failed = true;
            patchLast({ content: message, error: true });
          },
        },
      )
        .catch(() => {
          failed = true;
          patchLast({ content: "The answer stream failed.", error: true });
        })
        // The promise settling is the one signal that always arrives — on
        // success, on error and on abort. Releasing the latch anywhere else
        // risks wedging the composer shut for the rest of the session.
        .finally(() => {
          finish(controller);
          // Only a complete, sourced answer is worth an extra LLM call.
          const answered = source !== undefined && source !== "none";
          if (followupsEnabled && answered && !failed && !controller.signal.aborted) {
            loadFollowups(turnId, text, answer);
          }
        });
      return true;
    },
    [
      llm,
      llmReady,
      llmMissing,
      stats,
      whereFilter,
      kbOnly,
      followupsEnabled,
      appendToLast,
      patchLast,
      toast,
      finish,
      loadFollowups,
    ],
  );

  const pickSuggestion = useCallback(
    (question: string) => {
      if (send(question)) markSuggestionUsed(question);
    },
    [send, markSuggestionUsed],
  );

  const changeSuggestionLanguage = useCallback(
    (language: typeof suggestionLanguage) => {
      setSuggestionLanguage(language);
      void refreshSuggestions({ language });
    },
    [setSuggestionLanguage, refreshSuggestions],
  );

  const stop = () => {
    const controller = abortRef.current;
    if (!controller) return;
    controller.abort();
    finish(controller);
    if (messagesRef.current[messagesRef.current.length - 1]?.content === "") {
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
        {/* Chips call send directly. They used to write the query into context
            state so an effect could observe it and call send — a round trip
            through state purely to invoke a function defined right here, whose
            dependency list had to omit `send` to avoid re-firing. */}
        {messages.length === 0 ? (
          // Starter questions belong to an empty thread; once it is under way,
          // follow-ups under the latest answer take over.
          <div className="flex min-h-full flex-col justify-center gap-8 py-8">
            <EmptyState />
            {((stats?.documents ?? 0) > 0 || suggestions.length > 0) && (
              <Suggestions
                suggestions={suggestions}
                status={suggestionStatus}
                error={suggestionError}
                language={suggestionLanguage}
                onLanguageChange={changeSuggestionLanguage}
                onPick={pickSuggestion}
                onRegenerate={() => void refreshSuggestions()}
                disabled={streaming}
              />
            )}
          </div>
        ) : (
          messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            return (
              <Fragment key={i}>
                <MessageBubble
                  message={m}
                  streaming={streaming && isLast && m.role === "assistant"}
                />
                {isLast && !streaming && m.followups && (
                  <FollowUps questions={m.followups} onPick={send} />
                )}
              </Fragment>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 px-2">
        <ChatInput onSend={send} onStop={stop} streaming={streaming} />
        <div className="flex items-center gap-3 px-3 pb-2 text-[11.5px] text-subtle">
          <span className="truncate">{llm.model}</span>
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
    <div className="flex flex-col items-center justify-center gap-5 text-center">
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
