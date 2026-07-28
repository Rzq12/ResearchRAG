import { useState, type ReactNode } from "react";
import { CaretRight } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

interface CollapsibleProps {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}

/** Lightweight disclosure — the equivalent of Streamlit's st.expander. */
export function Collapsible({ title, children, defaultOpen = false, className }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={cn("overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.02]", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm font-medium text-zinc-300 transition-colors hover:text-white"
      >
        <CaretRight
          className={cn("h-4 w-4 text-zinc-500 transition-transform duration-200 ease-smooth", open && "rotate-90")}
        />
        <span className="flex-1">{title}</span>
      </button>
      {open && (
        <div className="border-t border-white/[0.06] px-3.5 py-3 animate-fade-up">{children}</div>
      )}
    </div>
  );
}
