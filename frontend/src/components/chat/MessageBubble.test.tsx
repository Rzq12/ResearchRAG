import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "@/lib/types";

const assistant = (content: string): ChatMessage => ({ role: "assistant", content });

describe("MessageBubble streaming", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("renders a finished answer in full straight away", () => {
    render(<MessageBubble message={assistant("The answer is $x=1$ here.")} />);
    expect(screen.getByText(/The answer is/)).toBeInTheDocument();
  });

  it("does not re-render on every token while streaming", () => {
    const { rerender } = render(<MessageBubble message={assistant("a")} streaming />);
    act(() => void vi.advanceTimersByTime(0));

    rerender(<MessageBubble message={assistant("ab")} streaming />);
    act(() => void vi.advanceTimersByTime(5));
    rerender(<MessageBubble message={assistant("abc")} streaming />);
    act(() => void vi.advanceTimersByTime(5));

    // Both updates landed inside one 50ms window, so neither has been shown.
    expect(screen.queryByText("abc")).toBeNull();
  });

  it("catches up to the latest content once the window elapses", () => {
    const { rerender } = render(<MessageBubble message={assistant("a")} streaming />);
    act(() => void vi.advanceTimersByTime(0));

    rerender(<MessageBubble message={assistant("abc")} streaming />);
    act(() => void vi.advanceTimersByTime(60));

    expect(screen.getByText("abc")).toBeInTheDocument();
  });

  it("shows the complete answer the moment streaming stops", () => {
    // The regression that matters: a pending throttle tick must never leave a
    // finished answer truncated on screen.
    const full = "The full and final answer.";
    const { rerender } = render(<MessageBubble message={assistant("The full")} streaming />);
    act(() => void vi.advanceTimersByTime(0));

    rerender(<MessageBubble message={assistant(full)} streaming />);
    expect(screen.queryByText(full)).toBeNull();

    rerender(<MessageBubble message={assistant(full)} />);
    expect(screen.getByText(full)).toBeInTheDocument();
  });

  it("still renders math in a streamed answer", () => {
    const { container, rerender } = render(<MessageBubble message={assistant("")} streaming />);
    act(() => void vi.advanceTimersByTime(0));

    rerender(<MessageBubble message={assistant("Energy is \\(E = mc^2\\).")} streaming />);
    act(() => void vi.advanceTimersByTime(60));

    expect(container.querySelector(".katex")).not.toBeNull();
  });
});
