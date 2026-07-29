import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names with conflict resolution. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Stable colour for a research-topic badge (mirrors app/topic_classifier.py). */
const TOPIC_COLOURS: Record<string, string> = {
  "Machine Learning": "#6366f1",
  "Deep Learning": "#8b5cf6",
  "NLP / Large Language Models": "#06b6d4",
  "Computer Vision": "#10b981",
  "RAG / Information Retrieval": "#f59e0b",
  "Reinforcement Learning": "#ef4444",
  "Bioinformatics / Computational Biology": "#84cc16",
  "Robotics / Control Systems": "#f97316",
  "Data Science / Statistics": "#3b82f6",
  "Security / Privacy": "#ec4899",
  "Human-Computer Interaction": "#14b8a6",
  Other: "#6b7280",
};

export function topicColour(topic: string): string {
  return TOPIC_COLOURS[topic] ?? "#6b7280";
}

/** Colour ramp for similarity/relevance scores [0,1]. */
export function scoreColour(score: number): string {
  if (score >= 0.5) return "#10b981";
  if (score >= 0.3) return "#f59e0b";
  return "#ef4444";
}

export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/**
 * Strip a leading emoji / symbol run from backend-provided strings (the model
 * catalog and provider hints ship with emoji prefixes). Keeps the UI emoji-free
 * per the design skills without touching the backend.
 */
export function stripLeadingSymbols(text: string): string {
  return text.replace(/^[^\p{L}\p{N}]+/u, "").trim();
}

/**
 * Reference source labels. The backend uses four distinct values:
 *   "upload"        — a PDF the user uploaded (in the KB)
 *   "openalex"      — an OpenAlex abstract ingested into the KB
 *   "openalex-live" — a LIVE OpenAlex fallback (NOT in the KB)
 *   "web"           — a DuckDuckGo web fallback (NOT in the KB)
 * See app/fallback.py and app/rag.py.build_context.
 */
export interface SourceMeta {
  label: string;
  /** True when the reference actually comes from the user's knowledge base. */
  fromKb: boolean;
  className: string;
}

export function sourceMeta(source: string): SourceMeta {
  switch (source) {
    case "upload":
      return { label: "Uploaded", fromKb: true, className: "bg-emerald-500/15 text-emerald-300" };
    case "openalex":
      return { label: "OpenAlex", fromKb: true, className: "bg-orange-500/15 text-orange-300" };
    case "openalex-live":
      return { label: "OpenAlex · live", fromKb: false, className: "bg-sky-500/15 text-sky-300" };
    case "web":
      return { label: "Web", fromKb: false, className: "bg-amber-500/15 text-amber-300" };
    default:
      return { label: source || "Source", fromKb: false, className: "bg-slate-600/30 text-slate-300" };
  }
}

/** Format a value that may be a number or the sentinel "?" for page numbers. */
export function formatScore(score: number): string {
  return score.toFixed(3);
}
