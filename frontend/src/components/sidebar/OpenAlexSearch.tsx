import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Broadcast, DownloadSimple, MagnifyingGlass } from "@phosphor-icons/react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Collapsible } from "@/components/ui/Collapsible";
import { Section } from "@/components/ui/Card";
import { useAuth } from "@/context/AuthContext";
import { useSettings } from "@/context/SettingsContext";
import { useToast } from "@/context/ToastContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useSingleFlight } from "@/hooks/useSingleFlight";
import {
  classifyTopics,
  getSuggestions,
  ingestOpenAlex,
  searchOpenAlex,
} from "@/lib/api";
import type { IngestMode, OpenAlexWork } from "@/lib/types";
import { topicColour, truncate } from "@/lib/utils";

const MODES: { value: IngestMode; label: string }[] = [
  { value: "abstracts", label: "Abstracts" },
  { value: "fulltext", label: "Full-text" },
  { value: "both", label: "Both" },
];

export function OpenAlexSearch() {
  const { session } = useAuth();
  const { selectedModel, activeApiKey, keys } = useSettings();
  const toast = useToast();
  const qc = useQueryClient();
  const { setSuggestions } = useWorkspace();

  const scope = session?.userId ?? "anonymous";

  const [query, setQuery] = useState("");
  const [count, setCount] = useState(5);
  const [mode, setMode] = useState<IngestMode>("abstracts");
  const [openAlexKey, setOpenAlexKey] = useState(keys.openalex);
  const [results, setResults] = useState<OpenAlexWork[]>([]);
  const [topics, setTopics] = useState<Record<string, string>>({});

  // Single-flight: one run fires searchOpenAlex + ingest + getSuggestions +
  // classifyTopics, the last two of which are LLM calls. Re-entry — trivially
  // reachable by holding Enter in the query box — multiplied that whole burst.
  const { run, pending: loading } = useSingleFlight(async () => {
    if (!query.trim()) {
      toast.warning("Please enter a search query.");
      return;
    }
    try {
      const { works } = await searchOpenAlex(query, count, openAlexKey || undefined);
      if (!works.length) {
        toast.error("No works found.");
        return;
      }
      setResults(works);

      const ingest = await ingestOpenAlex(works, mode);
      qc.invalidateQueries({ queryKey: ["documents", scope] });
      qc.invalidateQueries({ queryKey: ["kb-stats", scope] });

      if (ingest.abstracts_ingested) {
        toast.success(`${ingest.abstracts_ingested} abstracts ingested.`);
      }
      if (ingest.fulltext) {
        const { fetched, skipped, failed } = ingest.fulltext;
        if (fetched) toast.success(`Full-text ingested: ${fetched} paper(s).`);
        if (skipped) toast.info(`Already indexed: ${skipped} paper(s).`);
        if (failed) toast.warning(`No open-access PDF: ${failed} paper(s).`);
      }

      if (activeApiKey) {
        getSuggestions({ works, api_key: activeApiKey, model: selectedModel })
          .then((r) => setSuggestions(r.suggestions))
          .catch(() => undefined);
      }
      const groqKey = keys.groq || activeApiKey;
      if (groqKey) {
        classifyTopics(works, groqKey)
          .then((r) => setTopics((prev) => ({ ...prev, ...r.labels })))
          .catch(() => undefined);
      }
    } catch (err) {
      toast.error((err as Error).message);
    }
  });

  const downloadAbstracts = (format: "txt" | "json") => {
    let content: string;
    let mime: string;
    if (format === "json") {
      content = JSON.stringify(
        results.map((w) => ({
          title: w.title,
          authors: w.authors,
          published: w.published,
          url: w.url,
          abstract: w.abstract,
        })),
        null,
        2,
      );
      mime = "application/json";
    } else {
      content = results
        .map(
          (w, i) =>
            `[${i + 1}] ${w.title}\nAuthors : ${w.authors.join(", ")}\nPublished: ${w.published}\nURL      : ${w.url}\nAbstract :\n${w.abstract}\n${"-".repeat(60)}`,
        )
        .join("\n");
      mime = "text/plain";
    }
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `abstracts.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Section title="Search OpenAlex" icon={<Broadcast className="h-4 w-4" />}>
      <div className="space-y-3">
        <Input
          placeholder="e.g. attention mechanism transformer"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="Papers"
            type="number"
            min={1}
            max={20}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
          />
          <Input
            label="OpenAlex key (opt.)"
            type="password"
            value={openAlexKey}
            onChange={(e) => setOpenAlexKey(e.target.value)}
          />
        </div>

        <div className="flex gap-1.5">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={
                "flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition-all duration-200 ease-smooth active:scale-[0.97] " +
                (mode === m.value
                  ? "bg-accent text-zinc-950"
                  : "bg-white/[0.04] text-zinc-400 hover:bg-white/[0.07] hover:text-zinc-200")
              }
            >
              {m.label}
            </button>
          ))}
        </div>

        <Button variant="primary" fullWidth onClick={run} loading={loading}>
          <MagnifyingGlass className="h-4 w-4" /> Search &amp; Ingest
        </Button>

        {results.length > 0 && (
          <Collapsible title={`Results (${results.length})`} defaultOpen>
            <div className="stagger-in space-y-3">
              {results.map((w) => (
                <div key={w.openalex_id} className="text-xs">
                  <a
                    href={w.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-zinc-200 transition-colors hover:text-accent"
                  >
                    {truncate(w.title, 90)}
                  </a>
                  {topics[w.openalex_id] && (
                    <Badge
                      className="ml-1.5 text-white"
                      style={{ backgroundColor: topicColour(topics[w.openalex_id]) }}
                    >
                      {topics[w.openalex_id]}
                    </Badge>
                  )}
                  <p className="mt-0.5 text-muted">
                    {w.authors.slice(0, 2).join(", ")} · {w.published}
                    {w.citation_count ? ` · ${w.citation_count} citations` : ""}
                  </p>
                </div>
              ))}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => downloadAbstracts("txt")}>
                  <DownloadSimple className="h-3.5 w-3.5" /> .txt
                </Button>
                <Button size="sm" variant="outline" onClick={() => downloadAbstracts("json")}>
                  <DownloadSimple className="h-3.5 w-3.5" /> .json
                </Button>
              </div>
            </div>
          </Collapsible>
        )}
      </div>
    </Section>
  );
}
