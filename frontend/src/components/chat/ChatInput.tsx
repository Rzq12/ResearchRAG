import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowRight, Stop } from "@phosphor-icons/react";

interface ChatInputProps {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
}

/**
 * Composer as a double-bezel tray: outer shell, inner core, and a nested
 * "button-in-button" send control.
 */
export function ChatInput({ onSend, onStop, streaming, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const text = value.trim();
    if (!text || streaming) return;
    onSend(text);
    setValue("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={submit} className="pb-3 pt-1">
      <div className="bezel shadow-[0_30px_70px_-34px_rgba(0,0,0,0.95)]">
        <div className="bezel-core flex items-end gap-3 p-2 pl-5">
          <textarea
            ref={taRef}
            rows={1}
            value={value}
            disabled={disabled}
            onChange={(e) => {
              setValue(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 148)}px`;
            }}
            onKeyDown={onKeyDown}
            placeholder="Ask about your papers…"
            className="scrollbar-none max-h-[148px] min-w-0 flex-1 resize-none bg-transparent py-3 text-[15px] leading-[22px] text-zinc-100 placeholder:text-subtle focus:outline-none disabled:opacity-50"
          />

          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              className="flex shrink-0 items-center gap-2.5 rounded-full border border-white/[0.09] bg-white/[0.04] py-2.5 pl-4 pr-2 text-sm text-zinc-300 transition-all duration-[500ms] ease-smooth hover:bg-white/[0.08] hover:text-white active:scale-[0.97]"
            >
              Stop
              <span className="grid h-6 w-6 place-items-center rounded-full bg-white/[0.08]">
                <Stop className="h-3 w-3" weight="fill" />
              </span>
            </button>
          ) : (
            <button
              type="submit"
              disabled={disabled || !value.trim()}
              className="group flex shrink-0 items-center gap-2.5 rounded-full bg-accent py-2.5 pl-[18px] pr-2 text-sm font-medium text-zinc-950 transition-all duration-[500ms] ease-smooth hover:bg-accent-soft hover:shadow-[0_14px_36px_-18px_rgba(16,185,129,0.75)] active:scale-[0.97] disabled:opacity-40 disabled:shadow-none"
            >
              Ask
              <span className="grid h-6 w-6 place-items-center rounded-full bg-zinc-950/[0.14] transition-transform duration-[500ms] ease-smooth group-hover:translate-x-0.5">
                <ArrowRight className="h-3.5 w-3.5" />
              </span>
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
