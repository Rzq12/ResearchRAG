import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FilePdf, Paperclip, UploadSimple } from "@phosphor-icons/react";

import { Button } from "@/components/ui/Button";
import { Section } from "@/components/ui/Card";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { useWorkspace } from "@/context/WorkspaceContext";
import { useConfig } from "@/hooks/useServerData";
import { useSingleFlight } from "@/hooks/useSingleFlight";
import { uploadPdf } from "@/lib/api";

/** Mirror of app/pdf_service.py: a PDF's KB title is `filename.replace(".pdf", "")`. */
function kbTitleFromFilename(filename: string): string {
  return filename.split(".pdf").join("");
}

export function PdfUpload() {
  const { session } = useAuth();
  const { data: config } = useConfig();
  const toast = useToast();
  const qc = useQueryClient();
  const { refreshSuggestions } = useWorkspace();
  const inputRef = useRef<HTMLInputElement>(null);

  const scope = session?.userId ?? "anonymous";
  const maxMb = config?.max_upload_mb ?? 20;

  const [files, setFiles] = useState<File[]>([]);

  // Latched: a second click re-uploaded every selected PDF through the full
  // parse/embed pipeline and fired a second suggestions LLM call.
  const { run: ingest, pending: busy } = useSingleFlight(async () => {
    if (!files.length) return;
    const addedTitles: string[] = [];
    {
      for (const f of files) {
        if (f.size > maxMb * 1024 * 1024) {
          toast.warning(`${f.name} is too large (max ${maxMb} MB).`);
          continue;
        }
        try {
          const res = await uploadPdf(f);
          if (res.chunks_added > 0) {
            addedTitles.push(kbTitleFromFilename(res.filename || f.name));
            const cov = res.coverage?.coverage_pct;
            const detail =
              `${res.chunks_added} chunks` + (cov != null ? ` · coverage ${cov}%` : "");
            // Distinguish a revision from a first ingest — silently accepting a
            // corrected file and saying nothing is how stale answers happen.
            toast.success(
              res.replaced_revision
                ? `${f.name}: updated to this revision · ${detail}`
                : `${f.name}: ${detail}`,
            );
          } else {
            toast.info(`${f.name}: already indexed (identical file)`);
          }
        } catch (err) {
          toast.warning(`${f.name}: ${(err as Error).message}`);
        }
      }

      qc.invalidateQueries({ queryKey: ["documents", scope] });
      qc.invalidateQueries({ queryKey: ["kb-stats", scope] });

      // Not awaited: the questions arrive in the chat panel on their own time.
      if (addedTitles.length) void refreshSuggestions({ titles: addedTitles });

      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
    }
  });

  return (
    <Section title="Upload PDF" icon={<Paperclip className="h-4 w-4" />}>
      <div className="space-y-3">
        <label className="group flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border border-dashed border-white/[0.10] bg-white/[0.02] px-3 py-5 text-center text-xs text-muted transition-colors duration-200 hover:border-accent/40 hover:text-zinc-300">
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf"
            multiple
            className="hidden"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
          {files.length ? (
            <FilePdf className="h-5 w-5 text-accent" />
          ) : (
            <UploadSimple className="h-5 w-5 transition-transform duration-200 group-hover:-translate-y-0.5" />
          )}
          {files.length ? `${files.length} file(s) selected` : "Click to choose PDF files"}
        </label>

        {files.length > 0 && (
          <Button variant="primary" fullWidth onClick={ingest} loading={busy}>
            Ingest {files.length} PDF(s)
          </Button>
        )}
      </div>
    </Section>
  );
}
