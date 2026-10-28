import {
  ArrowBendDownRight,
  ArrowsClockwise,
  Lightbulb,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";

import type { SuggestionStatus } from "@/context/WorkspaceContext";
import type { SuggestionLanguage } from "@/lib/types";
import { cn } from "@/lib/utils";

const LANGUAGES: { value: SuggestionLanguage; label: string; title: string }[] = [
  { value: "id", label: "ID", title: "Questions in Bahasa Indonesia" },
  { value: "en", label: "EN", title: "Questions in English" },
];

interface SuggestionsProps {
  suggestions: string[];
  status: SuggestionStatus;
  error?: string | null;
  language: SuggestionLanguage;
  onLanguageChange: (language: SuggestionLanguage) => void;
  onPick: (q: string) => void;
  onRegenerate: () => void;
  /** True while an answer is streaming — picking would be ignored. */
  disabled?: boolean;
}

/** Starter questions generated from the knowledge base. */
export function Suggestions({
  suggestions,
  status,
  error,
  language,
  onLanguageChange,
  onPick,
  onRegenerate,
  disabled,
}: SuggestionsProps) {
  const loading = status === "loading";

  return (
    <section aria-label="Suggested questions" aria-busy={loading} className="space-y-2.5">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted">
          <Lightbulb className="h-3.5 w-3.5 text-accent" /> Suggested questions
        </p>
        <div className="flex items-center gap-1">
          <div
            role="group"
            aria-label="Question language"
            className="flex rounded-full border border-white/[0.08] p-0.5"
          >
            {LANGUAGES.map((l) => (
              <button
                key={l.value}
                type="button"
                title={l.title}
                aria-pressed={language === l.value}
                disabled={loading}
                onClick={() => language !== l.value && onLanguageChange(l.value)}
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10.5px] font-medium transition-colors duration-200 ease-smooth disabled:opacity-50",
                  language === l.value
                    ? "bg-white/[0.08] text-zinc-100"
                    : "text-muted hover:text-zinc-300",
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onRegenerate}
            disabled={loading}
            title="Suggest different questions"
            aria-label="Regenerate suggestions"
            className="grid h-7 w-7 place-items-center rounded-full text-muted transition-colors duration-200 ease-smooth hover:bg-white/[0.05] hover:text-zinc-200 disabled:opacity-50"
          >
            <ArrowsClockwise className={cn("h-3.5 w-3.5", loading && "motion-safe:animate-spin")} />
          </button>
        </div>
      </div>

      {status === "error" && error && (
        <p role="alert" className="flex items-start gap-1.5 text-[11.5px] leading-snug text-rose-300">
          <WarningCircle className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>
            {error}{" "}
            <button
              type="button"
              onClick={onRegenerate}
              className="underline underline-offset-2 hover:text-rose-200"
            >
              Try again
            </button>
          </span>
        </p>
      )}

      {suggestions.length > 0 ? (
        <ChipList
          questions={suggestions}
          onPick={onPick}
          disabled={disabled || loading}
          className={cn(loading && "opacity-50")}
        />
      ) : loading ? (
        <SkeletonChips />
      ) : (
        status !== "error" && (
          <button
            type="button"
            onClick={onRegenerate}
            className="flex items-center gap-1.5 rounded-full border border-dashed border-white/[0.12] px-3.5 py-1.5 text-xs text-zinc-400 transition-colors duration-200 ease-smooth hover:border-accent/40 hover:text-zinc-200"
          >
            <Sparkle className="h-3.5 w-3.5 text-accent" /> Suggest questions from my library
          </button>
        )
      )}
    </section>
  );
}

/** Follow-up questions shown under the latest answer. */
export function FollowUps({
  questions,
  onPick,
  disabled,
}: {
  questions: string[];
  onPick: (q: string) => void;
  disabled?: boolean;
}) {
  if (!questions.length) return null;
  return (
    // ml-11 lines the chips up with the answer text (avatar w-8 + gap-3).
    <section aria-label="Follow-up questions" className="ml-11 space-y-2 animate-fade-up">
      <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted">
        <ArrowBendDownRight className="h-3.5 w-3.5" /> Follow up
      </p>
      <ChipList questions={questions} onPick={onPick} disabled={disabled} />
    </section>
  );
}

function ChipList({
  questions,
  onPick,
  disabled,
  className,
}: {
  questions: string[];
  onPick: (q: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("stagger-in flex flex-wrap gap-2 transition-opacity", className)}>
      {questions.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onPick(q)}
          className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3.5 py-1.5 text-left text-xs text-zinc-300 transition-all duration-200 ease-smooth hover:border-accent/40 hover:bg-white/[0.04] active:scale-[0.98] disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}

const SKELETON_WIDTHS = ["w-56", "w-72", "w-48", "w-64"];

function SkeletonChips() {
  return (
    <div className="flex flex-wrap gap-2" aria-hidden="true">
      {SKELETON_WIDTHS.map((w) => (
        <span
          key={w}
          className={cn(
            "h-7 max-w-full rounded-full bg-white/[0.05] motion-safe:animate-pulse",
            w,
          )}
        />
      ))}
    </div>
  );
}
