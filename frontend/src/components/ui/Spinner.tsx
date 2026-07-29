import { CircleNotch } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <CircleNotch className={cn("h-4 w-4 animate-spin text-accent", className)} />;
}

export function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-zinc-400">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}
