import { useEffect, useRef, useState } from "react";

/**
 * Rate-limit how often a fast-changing value reaches the render tree.
 *
 * Written for streamed chat answers. Every SSE token appends to the message,
 * and re-rendering on each one makes `rehype-katex` re-typeset *every* formula
 * in the message — including ones that finished many tokens ago. Measured on a
 * 993-character math-heavy answer: 249 tokens cost 3272 ms streamed versus
 * 37 ms for a single final render, an 87x waste, at 13 ms per token.
 *
 * This is a throttle, not a debounce: under a continuous stream it still
 * releases a value every `delayMs`, so text keeps flowing. A debounce would
 * show nothing until the stream paused.
 *
 * @param value    The rapidly-changing value.
 * @param delayMs  Minimum gap between released updates.
 * @param enabled  When false the value passes straight through untouched.
 * @returns The most recently released value.
 */
export function useThrottledValue<T>(value: T, delayMs: number, enabled: boolean): T {
  const [released, setReleased] = useState(value);
  const lastReleaseRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;

    const wait = Math.max(0, delayMs - (Date.now() - lastReleaseRef.current));
    // Always go through a timer, never setState directly in the effect body:
    // that keeps this clear of react-hooks/set-state-in-effect, and a 0ms
    // timeout still lands in the same frame for the leading edge.
    const timer = window.setTimeout(() => {
      lastReleaseRef.current = Date.now();
      setReleased(value);
    }, wait);

    return () => window.clearTimeout(timer);
  }, [value, delayMs, enabled]);

  // Returning `value` directly while disabled is the guarantee that a finished
  // stream is never left showing a truncated answer, no matter where the
  // pending timer happened to be.
  return enabled ? released : value;
}
