import type { CSSProperties, ReactNode } from "react";

import { cn, sourceMeta } from "@/lib/utils";

interface BadgeProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function Badge({ children, className, style }: BadgeProps) {
  return (
    <span
      style={style}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SourceBadge({ source }: { source: string }) {
  const meta = sourceMeta(source);
  return <Badge className={meta.className}>{meta.label}</Badge>;
}
