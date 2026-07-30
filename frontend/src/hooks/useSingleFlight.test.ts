import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useSingleFlight } from "./useSingleFlight";

/** A promise the test resolves by hand, so an action can be held open. */
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe("useSingleFlight", () => {
  it("refuses a second call while the first is still running", async () => {
    const gate = deferred();
    let started = 0;
    const { result } = renderHook(() =>
      useSingleFlight(async () => {
        started += 1;
        await gate.promise;
      }),
    );

    await act(async () => {
      void result.current.run();
      void result.current.run();
      void result.current.run();
    });

    expect(started).toBe(1);

    await act(async () => {
      gate.resolve();
    });
    // Latch released — the action is runnable again.
    await act(async () => {
      void result.current.run();
    });
    expect(started).toBe(2);
  });

  it("reports pending across the action's lifetime", async () => {
    const gate = deferred();
    const { result } = renderHook(() =>
      useSingleFlight(async () => {
        await gate.promise;
      }),
    );

    expect(result.current.pending).toBe(false);
    await act(async () => {
      void result.current.run();
    });
    expect(result.current.pending).toBe(true);

    await act(async () => {
      gate.resolve();
    });
    expect(result.current.pending).toBe(false);
  });

  it("releases the latch when the action throws", async () => {
    let started = 0;
    const { result } = renderHook(() =>
      useSingleFlight(async () => {
        started += 1;
        throw new Error("boom");
      }),
    );

    // A rejected action must not wedge the control shut forever — that would
    // turn one transient network error into a dead button for the session.
    await act(async () => {
      await result.current.run().catch(() => undefined);
    });
    await act(async () => {
      await result.current.run().catch(() => undefined);
    });

    expect(started).toBe(2);
    expect(result.current.pending).toBe(false);
  });

  it("passes arguments through to the action", async () => {
    const seen: string[] = [];
    const { result } = renderHook(() =>
      useSingleFlight(async (title: string) => {
        seen.push(title);
      }),
    );

    await act(async () => {
      await result.current.run("paper-a");
    });
    await act(async () => {
      await result.current.run("paper-b");
    });

    expect(seen).toEqual(["paper-a", "paper-b"]);
  });
});
