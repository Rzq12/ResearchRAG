import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
}

/** Accessible switch used for the "KB-only" control. */
export function Toggle({ checked, onChange, label, hint, icon }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="group flex w-full items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3 text-left transition-colors hover:bg-white/[0.03]"
    >
      {icon && <span className="mt-0.5 shrink-0 text-zinc-400">{icon}</span>}
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-medium text-zinc-200">{label}</span>
        {hint && <span className="mt-0.5 block text-[11px] leading-snug text-zinc-500">{hint}</span>}
      </span>
      <span
        className={cn(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors duration-200 ease-smooth",
          checked ? "bg-accent" : "bg-zinc-700",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ease-smooth",
            checked ? "translate-x-[18px]" : "translate-x-0.5",
          )}
        />
      </span>
    </button>
  );
}
