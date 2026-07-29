import { Component, type ErrorInfo, type ReactNode } from "react";
import { ArrowClockwise, Warning } from "@phosphor-icons/react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time exceptions anywhere below it.
 *
 * Without this, a single throw in any component unmounts the whole tree and
 * leaves a blank page with no route to recovery — the user's only option is to
 * guess that a reload might help.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Wire an error reporter (Sentry et al.) here when one is configured.
    console.error("Unhandled render error:", error, info.componentStack);
  }

  private reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="flex min-h-[100dvh] items-center justify-center bg-zinc-950 px-4"
      >
        <div className="w-full max-w-md rounded-2xl border border-white/[0.07] bg-white/[0.02] p-7 text-center">
          <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-xl border border-amber-500/25 bg-amber-500/10">
            <Warning className="h-5 w-5 text-amber-400" />
          </div>
          <h1 className="text-[17px] font-medium tracking-tight text-white">
            Something broke on this screen
          </h1>
          <p className="mt-2 text-[13.5px] leading-relaxed text-zinc-400">
            The rest of your library is safe — nothing was lost. Try again, and if it keeps
            happening the message below will help diagnose it.
          </p>

          <pre className="mt-4 max-h-28 overflow-auto rounded-lg border border-white/[0.05] bg-zinc-900 p-3 text-left font-mono text-[11.5px] text-zinc-400">
            {error.message || String(error)}
          </pre>

          <div className="mt-5 flex justify-center gap-2">
            <button
              onClick={this.reset}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-zinc-950 transition-all duration-200 ease-smooth hover:bg-accent-soft active:scale-[0.98]"
            >
              <ArrowClockwise className="h-4 w-4" />
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="rounded-xl border border-white/[0.08] px-4 py-2.5 text-sm text-zinc-300 transition-all duration-200 ease-smooth hover:bg-white/[0.04] active:scale-[0.98]"
            >
              Reload app
            </button>
          </div>
        </div>
      </div>
    );
  }
}
