/**
 * Normalise LaTeX delimiters so `remark-math` can see them.
 *
 * `remark-math` only understands `$…$` and `$$…$$`, but LLMs routinely emit the
 * other standard LaTeX forms — `\(…\)` for inline and `\[…\]` for display.
 * Without this pass those answers render as literal backslash noise.
 */

/**
 * Code that must never be rewritten: a closed fenced block, an *unclosed*
 * fenced block (mid-stream, the closing fence has not arrived yet), or an
 * inline code span. Split with a capturing group so the segments come back
 * interleaved with the prose.
 *
 * Both fence alternatives are anchored to the start of a line (`m` flag, up to
 * the three leading spaces CommonMark allows). Without that anchor a stray
 * ``` written mid-sentence — an answer explaining markdown, for instance —
 * looks like an unterminated block, and every formula after it silently stops
 * rendering for the rest of the message.
 */
const CODE_SEGMENT = /(^ {0,3}```[\s\S]*?^ {0,3}```[^\n]*|^ {0,3}```[\s\S]*|`[^`\n]*`)/gm;

/**
 * Both patterns are non-greedy and require a closing delimiter, which is what
 * makes them safe during streaming: a half-arrived `\(E = mc` simply does not
 * match and is left alone until its `\)` shows up.
 *
 * No lookbehind is used to exclude an escaped `\\(`. Lookbehind is unsupported
 * on Safari < 16.4, and the tradeoff is not worth it: a `\(…\)` pair in prose
 * is math essentially every time.
 */
const DISPLAY_MATH = /\\\[([\s\S]+?)\\\]/g;
const INLINE_MATH = /\\\(([\s\S]+?)\\\)/g;

/**
 * Rewrite the LaTeX delimiters in one run of non-code markdown.
 *
 * Display math must end up with its `$$` fences alone on their own lines.
 * `remark-math` only produces a block formula when `$$` opens a line — written
 * inline as `$$ x $$` it degrades to *inline* math, silently losing the
 * centering and the larger operators. A single newline is enough to interrupt
 * the surrounding paragraph, so no blank line is inserted.
 */
function normalizeProse(prose: string): string {
  return prose
    .replace(DISPLAY_MATH, (_match, formula: string) => `\n$$\n${formula.trim()}\n$$\n`)
    .replace(INLINE_MATH, (_match, formula: string) => `$${formula}$`);
}

/**
 * Convert `\(…\)` to `$…$` and `\[…\]` to `$$…$$`, leaving code untouched.
 *
 * Text already using `$` delimiters passes through unchanged, so this is safe
 * to run over every message regardless of which form the model chose.
 *
 * @param markdown Raw markdown, possibly a partial chunk from a stream.
 * @returns The same markdown with math delimiters normalised to dollars.
 */
export function normalizeMath(markdown: string): string {
  if (!markdown) return markdown;

  // split() with a capturing group yields [prose, code, prose, code, …], so
  // the odd indices are the code segments that must be passed through as-is.
  return markdown
    .split(CODE_SEGMENT)
    .map((segment, index) => (index % 2 === 1 ? segment : normalizeProse(segment)))
    .join("");
}
