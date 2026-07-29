import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useThrottledValue } from "./useThrottledValue";

describe("useThrottledValue", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows the first value straight away", () => {
    const { result } = renderHook(() => useThrottledValue("a", 50, true));
    act(() => void vi.advanceTimersByTime(0));
    expect(result.current).toBe("a");
  });

  it("holds back an update that arrives inside the window", () => {
    const { result, rerender } = renderHook(({ v }) => useThrottledValue(v, 50, true), {
      initialProps: { v: "a" },
    });
    act(() => void vi.advanceTimersByTime(0));

    rerender({ v: "ab" });
    act(() => void vi.advanceTimersByTime(10));
    expect(result.current).toBe("a");
  });

  it("releases the latest value once the window elapses", () => {
    const { result, rerender } = renderHook(({ v }) => useThrottledValue(v, 50, true), {
      initialProps: { v: "a" },
    });
    act(() => void vi.advanceTimersByTime(0));

    rerender({ v: "ab" });
    act(() => void vi.advanceTimersByTime(10));
    rerender({ v: "abc" });
    act(() => void vi.advanceTimersByTime(60));

    // Intermediate "ab" is skipped entirely — that is the whole point.
    expect(result.current).toBe("abc");
  });

  it("throttles rather than debounces: a steady stream still updates", () => {
    const { result, rerender } = renderHook(({ v }) => useThrottledValue(v, 50, true), {
      initialProps: { v: "0" },
    });
    act(() => void vi.advanceTimersByTime(0));

    // A token every 10ms for 100ms — a debounce would never fire.
    for (let i = 1; i <= 10; i++) {
      rerender({ v: String(i) });
      act(() => void vi.advanceTimersByTime(10));
    }
    expect(result.current).not.toBe("0");
  });

  it("passes the value straight through when disabled", () => {
    const { result, rerender } = renderHook(({ v }) => useThrottledValue(v, 50, false), {
      initialProps: { v: "a" },
    });
    rerender({ v: "final" });
    expect(result.current).toBe("final");
  });

  it("reveals the full value immediately when throttling switches off", () => {
    // This is the guarantee that matters: when the stream ends, the user must
    // never be left looking at a truncated answer.
    const { result, rerender } = renderHook(({ v, on }) => useThrottledValue(v, 50, on), {
      initialProps: { v: "a", on: true },
    });
    act(() => void vi.advanceTimersByTime(0));

    rerender({ v: "a full answer", on: true });
    expect(result.current).toBe("a");

    rerender({ v: "a full answer", on: false });
    expect(result.current).toBe("a full answer");
  });

  it("does not leave a timer running after unmount", () => {
    const { rerender, unmount } = renderHook(({ v }) => useThrottledValue(v, 50, true), {
      initialProps: { v: "a" },
    });
    act(() => void vi.advanceTimersByTime(0));
    rerender({ v: "ab" });
    unmount();
    expect(() => act(() => void vi.advanceTimersByTime(200))).not.toThrow();
  });
});
