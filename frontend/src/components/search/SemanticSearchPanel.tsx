import { useState, type CSSProperties } from "react";
import { ArrowRight, MagnifyingGlass, Sparkle } from "@phosphor-icons/react";

import { useToast } from "@/context/ToastContext";
import { useKbStats } from "@/hooks/useServerData";
import { useSingleFlight } from "@/hooks/useSingleFlight";
import { semanticSearch } from "@/lib/api";
import type { SemanticHit } from "@/lib/types";
import { cn, formatScore, scoreColour, truncate } from "@/lib/utils";

const TYPES = ["All", "text", "table", "formula", "heading", "list", "fallback_page"];

const EXAMPLES = [
  "emotion recognition from wearables",
  "self-attention scaling behaviour",
  "chunking strategy for long methods",
];

export function SemanticSearchPanel() {
  const toast = useToast();
  const { data: stats } = useKbStats();

  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(15);
  const [ctype, setCtype] = useState("All");
  const [minScore, setMinScore] = useState(0);
  const [results, setResults] = useState<SemanticHit[] | null>(null);
  const [ranQuery, setRanQuery] = useState("");

  // The button was already disabled while loading, but the Enter handler below
  // was not — so holding Enter fired one search per keyboard repeat.
  const { run, pending: loading } = useSingleFlight(async (q?: string) => {
    const text = (q ?? query).trim();
    if (!text) {
      toast.warning("Enter a search query first.");
      return;
    }
    try {
      const res = await semanticSearch({
        query: text,
        top_k: topK,
        content_type_filter: ctype === "All" ? null : ctype,
        min_score: minScore,
      });
      setResults(res.results);
      setRanQuery(text);
    } catch (err) {
      toast.error((err as Error).message);
    }
  });

  const empty = !stats || stats.total_chunks === 0;

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="flex shrink-0 items-baseline justify-between gap-6 px-2 pb-6 pt-10">
        <div className="min-w-0">
          <h1 className="text-[26px] font-medium tracking-[-0.035em] text-white">
            Semantic search
          </h1>
          <p className="mt-1.5 truncate text-[13px] text-muted">
            Raw chunks with similarity scores — no model in the loop.
          </p>
        </div>
        {stats && (
          <span className="num shrink-0 whitespace-nowrap text-[12.5px] text-subtle">
            {stats.total_chunks.toLocaleString()} chunks indexed
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin px-2 pb-8">
        {empty ? (
          <div className="bezel">
            <div className="bezel-core px-6 py-10 text-center">
              <p className="text-[15px] text-zinc-200">Nothing indexed yet</p>
              <p className="mx-auto mt-2 max-w-[40ch] text-[13.5px] leading-relaxed text-muted">
                Ingest papers from OpenAlex or drop a PDF into the rail, then search across every
                chunk.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Query tray — same bezel language as the chat composer. */}
            <section className="bezel shadow-[0_30px_70px_-40px_rgba(0,0,0,0.9)]">
              <div className="bezel-core p-2 pl-5">
                <div className="flex items-center gap-3">
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && run()}
                    placeholder="Search every chunk…"
                    className="min-w-0 flex-1 bg-transparent py-3 text-[15px] text-zinc-100 placeholder:text-subtle focus:outline-none"
                  />
                  <button
                    onClick={() => run()}
                    disabled={loading || !query.trim()}
                    className="group flex shrink-0 items-center gap-2.5 rounded-full bg-accent py-2.5 pl-[18px] pr-2 text-sm font-medium text-zinc-950 transition-all duration-[500ms] ease-smooth hover:bg-accent-soft hover:shadow-[0_14px_36px_-18px_rgba(16,185,129,0.75)] active:scale-[0.97] disabled:opacity-40 disabled:shadow-none"
                  >
                    {loading ? "Searching" : "Search"}
                    <span className="grid h-6 w-6 place-items-center rounded-full bg-zinc-950/[0.14] transition-transform duration-[500ms] ease-smooth group-hover:translate-x-0.5">
                      <ArrowRight className="h-3.5 w-3.5" />
                    </span>
                  </button>
                </div>

                <div className="mt-1 flex flex-wrap items-center gap-x-8 gap-y-4 border-t border-white/[0.05] px-3 pb-2 pt-4">
                  <Range
                    label="Results"
                    value={topK}
                    display={String(topK)}
                    min={5}
                    max={30}
                    step={1}
                    onChange={setTopK}
                  />
                  <Range
                    label="Min score"
                    value={minScore}
                    display={minScore.toFixed(2)}
                    min={0}
                    max={1}
                    step={0.05}
                    onChange={setMinScore}
                  />
                </div>

                {/* Type filter as pills instead of a dropdown. */}
                <div className="flex flex-wrap gap-1.5 px-3 pb-2">
                  {TYPES.map((t) => (
                    <button
                      key={t}
                      onClick={() => setCtype(t)}
                      className={cn(
                        "rounded-full border border-white/[0.07] px-3 py-1.5 text-[12px] text-muted transition-all duration-[400ms] ease-smooth hover:text-zinc-200 active:scale-[0.97]",
                        ctype === t && "border-accent/30 bg-accent/[0.12] text-accent-soft",
                        t !== "All" && "font-mono",
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            {loading && <ResultSkeletons />}

            {!loading && results && results.length > 0 && (
              <div className="mt-8">
                <div className="mb-4 flex items-baseline justify-between gap-4 px-1">
                  <p className="min-w-0 truncate text-[13px] text-muted">
                    matches for <span className="text-zinc-300">“{ranQuery}”</span>
                  </p>
                  <span className="num shrink-0 text-[13px] text-zinc-400">
                    {results.length} hits
                  </span>
                </div>
                {/* Cascade follows rank order — the top hit lands first. */}
                <div className="stagger-in space-y-2.5">
                  {results.map((hit, i) => (
                    <ResultCard key={i} hit={hit} index={i + 1} />
                  ))}
                </div>
              </div>
            )}

            {!loading && results && results.length === 0 && (
              <div className="mt-8 rounded-[18px] border border-white/[0.07] bg-white/[0.02] px-6 py-9 text-center">
                <p className="text-[14.5px] text-zinc-300">
                  No chunk cleared the {minScore.toFixed(2)} score threshold
                </p>
                <p className="mt-2 text-[13px] text-muted">
                  Lower the minimum score, widen the type filter, or rephrase the query.
                </p>
              </div>
            )}

            {!loading && !results && (
              <div className="mt-10 px-1">
                <div className="flex items-center gap-2 text-subtle">
                  <Sparkle className="h-3.5 w-3.5" />
                  <span className="eyebrow">Try</span>
                </div>
                <ul className="mt-4 divide-y divide-white/[0.05]">
                  {EXAMPLES.map((ex) => (
                    <li key={ex}>
                      <button
                        onClick={() => {
                          setQuery(ex);
                          run(ex);
                        }}
                        className="group flex w-full items-center justify-between gap-4 py-3.5 text-left transition-colors duration-[400ms] ease-smooth"
                      >
                        <span className="text-[14.5px] text-zinc-400 transition-colors duration-[400ms] ease-smooth group-hover:text-zinc-100">
                          {ex}
                        </span>
                        <MagnifyingGlass className="h-3.5 w-3.5 shrink-0 text-muted transition-all duration-[400ms] ease-smooth group-hover:translate-x-0.5 group-hover:text-accent" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Range({
  label,
  value,
  display,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  display: string;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="min-w-[180px] flex-1">
      <span className="flex items-baseline justify-between gap-3">
        <span className="eyebrow">{label}</span>
        <span className="num text-[12.5px] text-zinc-300">{display}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="range-accent mt-2.5 w-full"
      />
    </label>
  );
}

function ResultSkeletons() {
  return (
    <div className="mt-8 space-y-2.5">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="sheen rounded-[18px] border border-white/[0.06] bg-white/[0.02] p-4"
          style={{ "--sheen-delay": `${i * 130}ms` } as CSSProperties}
        >
          <div className="h-3 w-1/3 rounded-full bg-white/[0.06]" />
          <div className="mt-3.5 h-2.5 w-full rounded-full bg-white/[0.04]" />
          <div className="mt-2 h-2.5 w-[86%] rounded-full bg-white/[0.035]" />
          <div className="mt-2 h-2.5 w-[54%] rounded-full bg-white/[0.03]" />
        </div>
      ))}
    </div>
  );
}

function ResultCard({ hit, index }: { hit: SemanticHit; index: number }) {
  const page = hit.page_num !== "?" ? `p.${hit.page_num}` : "";
  const section = hit.section_title ? truncate(hit.section_title, 40) : "";
  const colour = scoreColour(hit.score);

  return (
    <article className="group rounded-[18px] border border-white/[0.06] bg-white/[0.02] p-4 transition-all duration-[450ms] ease-smooth hover:-translate-y-px hover:border-white/[0.1] hover:bg-white/[0.035]">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-baseline gap-3">
          <span className="num shrink-0 text-[11px] text-subtle">
            {String(index).padStart(2, "0")}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13.5px] text-zinc-200">{truncate(hit.title, 60)}</p>
            <p className="mt-1 flex items-center gap-2 text-[11.5px] text-subtle">
              <span className="num text-accent-soft/80">{hit.content_type}</span>
              {page && <span className="num">{page}</span>}
              {section && <span className="truncate">{section}</span>}
            </p>
          </div>
        </div>

        {/* Score as a quiet meter, not a loud coloured badge. */}
        <div className="flex shrink-0 items-center gap-2.5">
          <span className="h-1 w-14 overflow-hidden rounded-full bg-white/[0.07]">
            <span
              className="block h-full rounded-full transition-[width] duration-700 ease-smooth"
              style={{ width: `${Math.max(4, Math.min(1, hit.score) * 100)}%`, background: colour }}
            />
          </span>
          <span className="num text-[11.5px]" style={{ color: colour }}>
            {formatScore(hit.score)}
          </span>
        </div>
      </div>

      <p className="mt-3 border-t border-white/[0.05] pt-3 text-[13.5px] leading-[1.65] text-zinc-400 [text-wrap:pretty]">
        {truncate(hit.text, 500)}
      </p>
    </article>
  );
}
