import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { normalizeMath } from "@/lib/math";
import { rehypeKatexA11y } from "@/lib/rehypeKatexA11y";
import { cn } from "@/lib/utils";

/**
 * KaTeX renders LLM-authored strings, so treat every option as a security
 * control rather than a default to inherit silently:
 *
 * - `trust: false` keeps `\href`, `\url` and `\includegraphics` inert, which is
 *   what stops a `javascript:` URL reaching the DOM.
 * - `throwOnError: false` degrades one malformed formula into red inline text
 *   instead of throwing and blanking the entire answer.
 * - `strict: "ignore"` avoids a console warning per unusual glyph; answers are
 *   frequently in Indonesian and mix scripts.
 * - `output` is left at the default `htmlAndMathml` so screen readers get the
 *   MathML track.
 */
const KATEX_OPTIONS = {
  trust: false,
  throwOnError: false,
  strict: "ignore" as const,
  // KaTeX writes this as an inline `style="color:…"` on the error span, which
  // outranks any class-based rule — so the readable-on-dark colour has to be
  // set here, not in index.css. This is Tailwind's rose-300.
  errorColor: "#fda4af",
  // KaTeX's own docs name `\rule{500em}{500em}` as the abuse case, yet maxSize
  // defaults to Infinity — an answer, or an injected source passage, could
  // paint a multi-million-pixel box and lock up layout. 50em already exceeds
  // the chat bubble; no legitimate formula needs more.
  maxSize: 50,
  // Default, set explicitly: caps macro expansion so \def recursion cannot
  // spin the parser.
  maxExpand: 1000,
};

/** Renders GitHub-flavoured markdown, with LaTeX math, in the chat prose style. */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("prose-chat", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, KATEX_OPTIONS], rehypeKatexA11y]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  );
}
