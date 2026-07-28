import { Broadcast, Brain, Globe, Robot, User } from "@phosphor-icons/react";

import { Collapsible } from "@/components/ui/Collapsible";
import { Markdown } from "@/components/ui/Markdown";
import { References } from "./References";
import type { ChatMessage, ChatSource } from "@/lib/types";
import { cn } from "@/lib/utils";

const SOURCE_NOTICE: Partial<
  Record<ChatSource, { icon: typeof Broadcast; text: string; cls: string }>
> = {
  "openalex-live": {
    icon: Broadcast,
    text: "Knowledge base wasn't relevant — answered from a live OpenAlex search.",
    cls: "border-sky-500/30 text-sky-300",
  },
  web: {
    icon: Globe,
    text: "KB & OpenAlex weren't relevant — answered from a web search (DuckDuckGo).",
    cls: "border-amber-500/30 text-amber-300",
  },
};

export function MessageBubble({ message, streaming }: { message: ChatMessage; streaming?: boolean }) {
  const isUser = message.role === "user";
  const notice = message.source ? SOURCE_NOTICE[message.source] : undefined;

  return (
    <div className={cn("flex gap-3 animate-fade-up", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
          isUser
            ? "border-white/[0.08] bg-white/[0.04] text-zinc-300"
            : "border-accent/25 bg-accent/10 text-accent",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Robot className="h-4 w-4" />}
      </div>

      <div className={cn("min-w-0 max-w-[85%] space-y-2", isUser && "flex flex-col items-end")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5",
            isUser
              ? "bg-white/[0.05] text-zinc-100"
              : message.error
                ? "border border-rose-500/30 bg-rose-950/20"
                : "border border-white/[0.06] bg-white/[0.02]",
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
          ) : (
            <>
              <Markdown>{message.content || ""}</Markdown>
              {streaming && (
                <span className="ml-0.5 inline-block h-4 w-[3px] translate-y-0.5 animate-blink rounded-full bg-accent" />
              )}
            </>
          )}
        </div>

        {!isUser && notice && (
          <div
            className={cn(
              "flex items-start gap-2 rounded-lg border bg-white/[0.02] px-3 py-2 text-xs",
              notice.cls,
            )}
          >
            <notice.icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{notice.text}</span>
          </div>
        )}

        {!isUser && message.reasoning && (
          <Collapsible
            title={
              <span className="flex items-center gap-2">
                <Brain className="h-4 w-4 text-zinc-500" /> Reasoning
              </span>
            }
            className="w-full"
          >
            <Markdown className="text-sm text-zinc-300">{message.reasoning}</Markdown>
          </Collapsible>
        )}

        {!isUser && message.references && message.references.length > 0 && (
          <div className="w-full">
            <References references={message.references} />
          </div>
        )}
      </div>
    </div>
  );
}
