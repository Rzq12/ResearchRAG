import { useCallback, useRef, useState } from "react";

/**
 * Run an async action, refusing to start it again while it is still running.
 *
 * React state cannot do this on its own. Setting `loading` to true does not make
 * it true for the rest of the current event batch — every handler that already
 * closed over `loading === false` still sees false. A double-click, or an Enter
 * key held a fraction too long, therefore ran the action twice before the first
 * render carrying `loading === true` ever committed. On an LLM-backed endpoint
 * that silently doubled the user's upstream quota spend.
 *
 * The ref latch flips synchronously, before any await, so the second call is
 * rejected immediately regardless of where React is in its render cycle.
 * `pending` remains available for rendering spinners and disabled states.
 */
export function useSingleFlight<A extends unknown[]>(
  action: (...args: A) => Promise<void>,
): { run: (...args: A) => Promise<void>; pending: boolean } {
  // Survives re-renders even though `action` (and therefore `run`) is a fresh
  // closure each time — the latch lives in the ref, not in the callback.
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async (...args: A) => {
      if (inFlight.current) return;
      inFlight.current = true;
      setPending(true);
      try {
        await action(...args);
      } finally {
        inFlight.current = false;
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending };
}
