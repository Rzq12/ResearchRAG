// Registers @testing-library/jest-dom matchers (toBeInTheDocument, ...) on
// vitest's `expect`. Loaded via `setupFiles` in vitest.config.ts.
import "@testing-library/jest-dom/vitest";

// jsdom implements no layout, so Element.prototype.scrollIntoView is absent
// entirely (not just inert). Any component that keeps a view pinned to the
// bottom — the chat transcript does — therefore throws on mount rather than
// simply doing nothing. Stub it once here so component tests exercise the real
// component instead of a jsdom gap.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
