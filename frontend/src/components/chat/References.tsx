import { Books } from "@phosphor-icons/react";

import { Collapsible } from "@/components/ui/Collapsible";
import { SourceBadge } from "@/components/ui/Badge";
import type { Reference } from "@/lib/types";
import { sourceMeta } from "@/lib/utils";

export function References({ references }: { references: Reference[] }) {
  if (!references.length) return null;

  // Count by human-readable source label (Uploaded / OpenAlex / OpenAlex · live / Web).
  const counts = references.reduce<Record<string, number>>((acc, r) => {
    const { label } = sourceMeta(r.source);
    acc[label] = (acc[label] ?? 0) + 1;
    return acc;
  }, {});
  const label = Object.entries(counts)
    .map(([name, n]) => `${n} ${name}`)
    .join(" · ");

  return (
    <Collapsible
      title={
        <span className="flex items-center gap-2">
          <Books className="h-4 w-4 text-muted" />
          References ({references.length})
          {label && <span className="text-muted">— {label}</span>}
        </span>
      }
    >
      {/* Citations land in citation order, so [1] reads before [2]. */}
      <ol className="stagger-in space-y-2">
        {references.map((ref, i) => (
          <li
            key={`${ref.url}-${i}`}
            className="rounded-lg border-l-2 border-accent/60 bg-white/[0.02] px-3 py-2 text-xs"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-muted">[{i + 1}]</span>
              <SourceBadge source={ref.source} />
              {ref.url ? (
                <a
                  href={ref.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-zinc-200 transition-colors hover:text-accent"
                >
                  {ref.title}
                </a>
              ) : (
                <span className="font-medium text-zinc-200">{ref.title}</span>
              )}
            </div>
            <div className="mt-0.5 text-muted">
              {ref.authors} · {ref.published} · relevance: {ref.relevance_score.toFixed(2)}
            </div>
          </li>
        ))}
      </ol>
    </Collapsible>
  );
}
