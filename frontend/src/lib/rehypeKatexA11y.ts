/**
 * Make KaTeX display equations reachable by keyboard.
 *
 * `.katex-display` is styled `overflow-x: auto` so a wide derivation scrolls
 * instead of breaking the chat bubble. A scrollable region that cannot take
 * focus is unreachable for anyone navigating by keyboard — WCAG 2.1.1. The
 * element is generated inside the math node by `rehype-katex`, so no
 * react-markdown `components` override can reach it; it has to be patched in
 * the hast tree afterwards.
 *
 * Deliberately dependency-free: a ten-line walk beats pulling in
 * `unist-util-visit` as a direct dependency just to set three properties.
 */

/** The slice of hast this plugin touches. */
interface HastNode {
  type: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function isDisplayMath(node: HastNode): boolean {
  const className = node.properties?.className;
  return Array.isArray(className) && className.includes("katex-display");
}

/**
 * Rehype plugin. Must run *after* `rehype-katex`, which creates the nodes.
 *
 * `role="group"` rather than `region`: a long answer can hold a dozen
 * equations, and a dozen landmarks would bury the real ones.
 */
export function rehypeKatexA11y() {
  return (tree: HastNode): void => {
    const walk = (node: HastNode): void => {
      if (node.type === "element" && isDisplayMath(node)) {
        node.properties = {
          ...node.properties,
          tabIndex: 0,
          role: "group",
          ariaLabel: "Equation, scroll horizontally to see the rest",
        };
      }
      node.children?.forEach(walk);
    };
    walk(tree);
  };
}
