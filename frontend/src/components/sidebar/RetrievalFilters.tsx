import { useEffect, useMemo, useState } from "react";
import { Funnel } from "@phosphor-icons/react";

import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Collapsible } from "@/components/ui/Collapsible";
import { useSettings } from "@/context/SettingsContext";
import { useDocuments } from "@/hooks/useServerData";
import type { WhereFilter } from "@/lib/types";

const SECTIONS = [
  "All sections",
  "abstract",
  "introduction",
  "related_work",
  "methods",
  "results",
  "discussion",
  "conclusion",
];

/** Metadata filtering (document / section / year) → builds the Chroma where. */
export function RetrievalFilters() {
  const { setWhereFilter } = useSettings();
  const { data } = useDocuments();

  const [doc, setDoc] = useState("All documents");
  const [section, setSection] = useState("All sections");
  const [year, setYear] = useState(0);

  const titles = useMemo(
    () => Array.from(new Set((data?.documents ?? []).map((d) => d.title))).sort(),
    [data],
  );

  useEffect(() => {
    const clauses: Record<string, unknown>[] = [];
    if (doc !== "All documents") clauses.push({ title: doc });
    if (section !== "All sections") clauses.push({ section_label: section });
    if (year > 0) clauses.push({ year: { $gte: year } });

    let where: WhereFilter = null;
    if (clauses.length > 1) where = { $and: clauses };
    else if (clauses.length === 1) where = clauses[0];
    setWhereFilter(where);
  }, [doc, section, year, setWhereFilter]);

  const activeCount = [doc !== "All documents", section !== "All sections", year > 0].filter(
    Boolean,
  ).length;

  return (
    <Collapsible
      title={
        <span className="flex items-center gap-2">
          <Funnel className="h-4 w-4 text-muted" />
          Retrieval filters
          {activeCount > 0 && (
            <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
              {activeCount}
            </span>
          )}
        </span>
      }
    >
      <div className="space-y-3">
        <Select
          label="Document"
          options={["All documents", ...titles].map((t) => ({ value: t, label: t }))}
          value={doc}
          onChange={(e) => setDoc(e.target.value)}
        />
        <Select
          label="Section"
          options={SECTIONS.map((s) => ({ value: s, label: s }))}
          value={section}
          onChange={(e) => setSection(e.target.value)}
        />
        <Input
          label="Published ≥ year (0 = off; OpenAlex only)"
          type="number"
          min={0}
          max={2100}
          value={year || ""}
          onChange={(e) => setYear(Number(e.target.value) || 0)}
        />
        {activeCount > 0 && (
          <p className="text-[11px] text-accent">
            {activeCount} filter(s) active — BM25 skipped, vector search only.
          </p>
        )}
      </div>
    </Collapsible>
  );
}
