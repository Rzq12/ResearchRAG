import { Lightbulb } from "@phosphor-icons/react";

interface SuggestionsProps {
  suggestions: string[];
  onPick: (q: string) => void;
  disabled?: boolean;
}

export function Suggestions({ suggestions, onPick, disabled }: SuggestionsProps) {
  if (!suggestions.length) return null;
  return (
    <div className="space-y-2.5">
      <p className="flex items-center gap-1.5 text-xs font-medium text-zinc-500">
        <Lightbulb className="h-3.5 w-3.5 text-accent" /> Suggested questions
      </p>
      <div className="stagger-in flex flex-wrap gap-2">
        {suggestions.map((s, i) => (
          <button
            key={i}
            disabled={disabled}
            onClick={() => onPick(s)}
            className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3.5 py-1.5 text-left text-xs text-zinc-300 transition-all duration-200 ease-smooth hover:border-accent/40 hover:bg-white/[0.04] active:scale-[0.98] disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
