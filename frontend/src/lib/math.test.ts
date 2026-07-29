import { describe, expect, it } from "vitest";

import { normalizeMath } from "./math";

describe("normalizeMath", () => {
  describe("LaTeX bracket delimiters", () => {
    it("converts inline \\( ... \\) to single dollars", () => {
      expect(normalizeMath("Energy is \\(E = mc^2\\) exactly.")).toBe(
        "Energy is $E = mc^2$ exactly.",
      );
    });

    // The `$$` fences must land on their own lines: remark-math only emits a
    // *block* formula when `$$` opens a line. Written inline as `$$ x $$` it
    // silently degrades to inline math — verified against the real pipeline.
    it("converts display \\[ ... \\] to block double dollars", () => {
      expect(normalizeMath("\\[ \\sum_{i=1}^{n} x_i \\]")).toBe("\n$$\n\\sum_{i=1}^{n} x_i\n$$\n");
    });

    it("converts several occurrences in one string", () => {
      expect(normalizeMath("\\(a\\) and \\(b\\) then \\[c\\]")).toBe(
        "$a$ and $b$ then \n$$\nc\n$$\n",
      );
    });

    it("converts display math spanning multiple lines", () => {
      const input = "Before\n\\[\n  x = y\n\\]\nAfter";
      expect(normalizeMath(input)).toBe("Before\n\n$$\nx = y\n$$\n\nAfter");
    });

    it("keeps backslash commands inside the formula intact", () => {
      expect(normalizeMath("\\(\\alpha \\times \\beta\\)")).toBe("$\\alpha \\times \\beta$");
    });
  });

  describe("existing dollar math", () => {
    it("leaves inline $...$ untouched", () => {
      expect(normalizeMath("The value $x^2$ grows.")).toBe("The value $x^2$ grows.");
    });

    it("leaves display $$...$$ untouched", () => {
      expect(normalizeMath("$$\n\\frac{a}{b}\n$$")).toBe("$$\n\\frac{a}{b}\n$$");
    });
  });

  describe("code is never rewritten", () => {
    it("leaves \\( inside a fenced code block alone", () => {
      const input = "```python\nprint('\\(not math\\)')\n```";
      expect(normalizeMath(input)).toBe(input);
    });

    it("leaves \\[ inside a fenced code block alone", () => {
      const input = "```\narr\\[0\\]\n```";
      expect(normalizeMath(input)).toBe(input);
    });

    it("leaves \\( inside an inline code span alone", () => {
      const input = "Call `f\\(x\\)` to run it.";
      expect(normalizeMath(input)).toBe(input);
    });

    it("still converts math outside a fenced block", () => {
      const input = "\\(a\\)\n```\n\\(b\\)\n```\n\\(c\\)";
      expect(normalizeMath(input)).toBe("$a$\n```\n\\(b\\)\n```\n$c$");
    });
  });

  describe("streaming safety", () => {
    it("leaves an unterminated \\( alone", () => {
      expect(normalizeMath("Energy is \\(E = mc")).toBe("Energy is \\(E = mc");
    });

    it("leaves an unterminated \\[ alone", () => {
      expect(normalizeMath("\\[ \\sum_{i=1}")).toBe("\\[ \\sum_{i=1}");
    });

    it("converts the closed pair and leaves a trailing open one", () => {
      expect(normalizeMath("\\(a\\) then \\(b")).toBe("$a$ then \\(b");
    });

    it("leaves an unterminated fenced block's contents alone", () => {
      const input = "text\n```\n\\(a\\)";
      expect(normalizeMath(input)).toBe(input);
    });
  });

  // A fence is only a fence at the start of a line. A stray ``` written
  // mid-sentence — an answer *about* markdown, say — used to be treated as an
  // unterminated block, so every formula after it silently stopped rendering.
  describe("a mid-sentence ``` is not a fence", () => {
    it("still converts math after an inline triple backtick", () => {
      expect(normalizeMath("Use ``` for fences. Then \\(a=b\\).")).toBe(
        "Use ``` for fences. Then $a=b$.",
      );
    });

    it("does not swallow prose between a stray ``` and a later real fence", () => {
      const input = "Use ``` inline. Also \\(a\\).\n```\ncode\n```";
      expect(normalizeMath(input)).toBe("Use ``` inline. Also $a$.\n```\ncode\n```");
    });

    it("still treats an indented fence (up to 3 spaces) as a fence", () => {
      const input = "  ```\n\\(a\\)\n  ```";
      expect(normalizeMath(input)).toBe(input);
    });
  });

  describe("passthrough", () => {
    it("returns an empty string unchanged", () => {
      expect(normalizeMath("")).toBe("");
    });

    it("returns plain prose unchanged", () => {
      expect(normalizeMath("No math here at all.")).toBe("No math here at all.");
    });

    // Known, accepted limitation. Single-dollar inline math is kept enabled
    // because models emit `$x$` constantly, but that means bare currency like
    // "$5 and $10" is parsed as a formula downstream. normalizeMath does not
    // guess at intent; the mitigation is the SYSTEM_PROMPT rule telling the
    // model to write literal amounts as `\$5`.
    it("passes bare currency through without escaping it", () => {
      expect(normalizeMath("costs $5 and $10 total")).toBe("costs $5 and $10 total");
    });

    it("leaves already-escaped currency alone", () => {
      expect(normalizeMath("costs \\$5 and \\$10 total")).toBe("costs \\$5 and \\$10 total");
    });

    it("does not treat an escaped backslash as a delimiter", () => {
      // "\\\\(" in the source is a literal backslash followed by "(" — a Windows
      // path or a regex, not the start of a formula.
      expect(normalizeMath("path\\\\(x)")).toBe("path\\\\(x)");
    });
  });
});
