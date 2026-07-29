import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Newspaper, NotePencil, Stack, Trash } from "@phosphor-icons/react";

import { Button } from "@/components/ui/Button";
import { Section } from "@/components/ui/Card";
import { Collapsible } from "@/components/ui/Collapsible";
import { Markdown } from "@/components/ui/Markdown";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/context/AuthContext";
import { useSettings } from "@/context/SettingsContext";
import { useToast } from "@/context/ToastContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useDocuments, useKbStats } from "@/hooks/useServerData";
import { clearKnowledgeBase, deleteDocument, summarizeDocument } from "@/lib/api";
import { truncate } from "@/lib/utils";

export function KnowledgeBase() {
  const { session } = useAuth();
  const { selectedModel, activeApiKey } = useSettings();
  const toast = useToast();
  const qc = useQueryClient();
  const { setSuggestions } = useWorkspace();
  const scope = session?.userId ?? "anonymous";

  const { data: stats } = useKbStats();
  const { data: docs } = useDocuments();

  const [summaries, setSummaries] = useState<Record<string, string>>({});
  const [busyTitle, setBusyTitle] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["documents", scope] });
    qc.invalidateQueries({ queryKey: ["kb-stats", scope] });
  };

  const summarize = async (title: string) => {
    if (!activeApiKey) {
      toast.warning("An API key is required to summarize. Set one above.");
      return;
    }
    setBusyTitle(title);
    try {
      const res = await summarizeDocument(title, activeApiKey, selectedModel);
      setSummaries((prev) => ({ ...prev, [title]: res.summary }));
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusyTitle(null);
    }
  };

  const remove = async (title: string) => {
    try {
      const res = await deleteDocument(title);
      setSummaries((prev) => {
        const next = { ...prev };
        delete next[title];
        return next;
      });
      toast.success(`Deleted ${res.deleted} chunks.`);
      invalidate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const clearAll = async () => {
    try {
      const res = await clearKnowledgeBase();
      setSummaries({});
      setSuggestions([]);
      toast.success(`Cleared ${res.cleared} chunks.`);
      invalidate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const documents = docs?.documents ?? [];

  return (
    <Section title="Knowledge Base" icon={<Stack className="h-4 w-4" />}>
      <div className="grid grid-cols-2 gap-2">
        <Metric label="Total chunks" value={stats?.total_chunks ?? 0} />
        <Metric label="Documents" value={stats?.documents ?? 0} />
      </div>

      {documents.length > 0 && (
        <Collapsible title={`Manage documents (${documents.length})`}>
          <div className="space-y-1">
            {documents.slice(0, 30).map((d) => (
              <div key={d.title} className="flex items-center gap-2 text-xs">
                {d.source === "upload" ? (
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted" />
                ) : (
                  <Newspaper className="h-3.5 w-3.5 shrink-0 text-muted" />
                )}
                <span className="flex-1 truncate text-zinc-300" title={d.title}>
                  {truncate(d.title, 30)}
                </span>
                <button
                  onClick={() => summarize(d.title)}
                  disabled={busyTitle === d.title}
                  title="Summarize"
                  className="text-muted transition-colors hover:text-accent disabled:opacity-50"
                >
                  {busyTitle === d.title ? (
                    <Spinner className="h-3.5 w-3.5" />
                  ) : (
                    <NotePencil className="h-3.5 w-3.5" />
                  )}
                </button>
                <button
                  onClick={() => remove(d.title)}
                  title="Delete"
                  className="text-muted transition-colors hover:text-rose-400"
                >
                  <Trash className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </Collapsible>
      )}

      {Object.entries(summaries).map(([title, text]) => (
        <Collapsible key={title} title={`Summary — ${truncate(title, 36)}`} defaultOpen>
          <Markdown>{text}</Markdown>
        </Collapsible>
      ))}

      <Button variant="outline" fullWidth onClick={clearAll}>
        <Trash className="h-4 w-4" /> Clear all documents
      </Button>
    </Section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className="font-mono text-xl font-semibold tracking-tight text-white">{value}</div>
      <div className="mt-0.5 text-[11px] text-muted">{label}</div>
    </div>
  );
}
