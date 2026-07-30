import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

/** KaTeX renders into `.katex`; display math is wrapped in `.katex-display`. */
function katexRoots(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(".katex"));
}

describe("Markdown", () => {
  describe("existing behaviour is preserved", () => {
    it("renders plain markdown", () => {
      render(<Markdown>{"Hello **world**"}</Markdown>);
      expect(screen.getByText("world").tagName).toBe("STRONG");
    });

    it("renders GFM tables via remark-gfm", () => {
      const table = "| a | b |\n| - | - |\n| 1 | 2 |";
      const { container } = render(<Markdown>{table}</Markdown>);
      expect(container.querySelector("table")).not.toBeNull();
    });

    it("opens links in a new tab with a safe rel", () => {
      render(<Markdown>{"[site](https://example.com)"}</Markdown>);
      const link = screen.getByRole("link");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });
  });

  describe("math rendering", () => {
    it("renders inline $...$ math with KaTeX", () => {
      const { container } = render(<Markdown>{"Einstein wrote $E = mc^2$ here."}</Markdown>);
      expect(katexRoots(container)).toHaveLength(1);
      expect(container.textContent).not.toContain("$");
    });

    it("renders display $$...$$ math as a block", () => {
      const { container } = render(<Markdown>{"$$\n\\sum_{i=1}^{n} i\n$$"}</Markdown>);
      expect(container.querySelector(".katex-display")).not.toBeNull();
    });

    it("renders \\( ... \\) inline math via normalizeMath", () => {
      const { container } = render(<Markdown>{"Energy is \\(E = mc^2\\) exactly."}</Markdown>);
      expect(katexRoots(container)).toHaveLength(1);
      expect(container.textContent).not.toContain("\\(");
    });

    it("renders \\[ ... \\] display math via normalizeMath", () => {
      const { container } = render(<Markdown>{"\\[ \\frac{a}{b} \\]"}</Markdown>);
      expect(container.querySelector(".katex-display")).not.toBeNull();
    });

    it("does not render math inside a fenced code block", () => {
      const { container } = render(<Markdown>{"```\n\\(E = mc^2\\)\n```"}</Markdown>);
      expect(katexRoots(container)).toHaveLength(0);
      expect(container.querySelector("pre")).not.toBeNull();
    });

    it("shows an invalid formula as text instead of throwing", () => {
      // throwOnError must stay false, or one malformed formula from the model
      // would blank the whole answer.
      expect(() => render(<Markdown>{"$\\frac{$"}</Markdown>)).not.toThrow();
    });
  });

  describe("resource limits", () => {
    it("caps an absurd \\rule so it cannot blow up layout", () => {
      // KaTeX's maxSize defaults to Infinity and its own docs name
      // \rule{500em}{500em} as the hazard. An answer (or an injected source
      // passage) containing one would paint a multi-million-pixel box.
      const { container } = render(<Markdown>{"$\\rule{99999em}{99999em}$"}</Markdown>);
      const ems = Array.from(container.querySelectorAll<HTMLElement>("[style]"))
        .flatMap((el) => Array.from(el.getAttribute("style")?.matchAll(/([\d.]+)em/g) ?? []))
        .map((m) => Number(m[1]));
      expect(Math.max(0, ...ems)).toBeLessThanOrEqual(500);
    });

    it("does not hang on a deeply nested expression", () => {
      const deep = "\\frac{".repeat(60) + "x" + "}{y}".repeat(60);
      const start = Date.now();
      render(<Markdown>{`$${deep}$`}</Markdown>);
      expect(Date.now() - start).toBeLessThan(2000);
    });
  });

  describe("accessibility", () => {
    it("makes a horizontally scrollable equation reachable by keyboard", () => {
      // .katex-display is an overflow-x:auto container. A scrollable region
      // that cannot take focus is unreachable for keyboard users (WCAG 2.1.1).
      const { container } = render(<Markdown>{"$$\n\\sum_{i=1}^{n} i\n$$"}</Markdown>);
      const display = container.querySelector<HTMLElement>(".katex-display");
      expect(display).not.toBeNull();
      expect(display).toHaveAttribute("tabindex", "0");
      expect(display).toHaveAttribute("role");
      expect(display?.getAttribute("aria-label")).toBeTruthy();
    });

    it("keeps the MathML track for screen readers", () => {
      const { container } = render(<Markdown>{"$E = mc^2$"}</Markdown>);
      expect(container.querySelector(".katex-mathml")).not.toBeNull();
    });
  });

  describe("mixed markdown and math", () => {
    it("renders math inside a list item", () => {
      const { container } = render(<Markdown>{"- first $x^2$\n- second $y^2$"}</Markdown>);
      expect(container.querySelectorAll("li")).toHaveLength(2);
      expect(container.querySelectorAll(".katex")).toHaveLength(2);
    });

    it("renders math inside a table cell", () => {
      const md = "| sym | val |\n| - | - |\n| $\\alpha$ | 1 |";
      const { container } = render(<Markdown>{md}</Markdown>);
      expect(container.querySelector("table")).not.toBeNull();
      expect(container.querySelectorAll(".katex").length).toBeGreaterThan(0);
    });

    it("keeps bold and links working alongside math", () => {
      const { container } = render(
        <Markdown>{"**bold** and $x$ and [l](https://e.com)"}</Markdown>,
      );
      expect(container.querySelector("strong")).not.toBeNull();
      expect(container.querySelector("a")).not.toBeNull();
      expect(container.querySelector(".katex")).not.toBeNull();
    });

    it("renders an escaped dollar as a literal, not as math", () => {
      const { container } = render(<Markdown>{"costs \\$5 and \\$10 total"}</Markdown>);
      expect(container.querySelectorAll(".katex")).toHaveLength(0);
      expect(container.textContent).toContain("$5");
    });

    it("renders BARE currency as plain text end to end", () => {
      const { container } = render(<Markdown>{"costs $5 and $10 total"}</Markdown>);
      expect(container.querySelectorAll(".katex")).toHaveLength(0);
      expect(container.textContent).toContain("$5");
      expect(container.textContent).toContain("$10");
    });

    it("still renders a formula sitting next to currency", () => {
      const { container } = render(<Markdown>{"costs $5 but $E = mc^2$ holds"}</Markdown>);
      expect(container.querySelectorAll(".katex")).toHaveLength(1);
      expect(container.textContent).toContain("$5");
    });
  });

  describe("math is not an HTML injection vector", () => {
    it("does not execute \\href with a javascript: target", () => {
      const { container } = render(<Markdown>{"$\\href{javascript:alert(1)}{click}$"}</Markdown>);
      const hrefs = Array.from(container.querySelectorAll("a")).map((a) => a.getAttribute("href"));
      expect(hrefs.some((href) => href?.startsWith("javascript:"))).toBe(false);
    });

    it("does not emit a script tag from \\htmlData-style input", () => {
      const { container } = render(
        <Markdown>{"$\\htmlData{x=<script>alert(1)</script>}{y}$"}</Markdown>,
      );
      expect(container.querySelector("script")).toBeNull();
    });
  });
});
