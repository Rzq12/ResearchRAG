import { useState, type ReactNode } from "react";
import { Database, Flask, List, SidebarSimple, SignOut, X } from "@phosphor-icons/react";

import { SidebarContent } from "./Sidebar";
import { useAuth } from "@/context/AuthContext";
import { useSettings } from "@/context/SettingsContext";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import { cn } from "@/lib/utils";

/**
 * Workspace shell: a floating glass island nav on top, the thread in the
 * centre, and the source/ingest rail on the right. The rail is collapsible on
 * desktop (state persists across reloads) and becomes the off-canvas drawer
 * below `lg`.
 */
export function AppShell({ nav, children }: { nav?: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [railOpen, setRailOpen] = useLocalStorage<boolean>("rr_rail_open", true);
  const { session, logout } = useAuth();
  const { kbOnly, setKbOnly } = useSettings();

  return (
    <div className="relative flex h-[100dvh] flex-col overflow-hidden bg-zinc-950">
      {/* Ambient wash — single accent hue, no purple. */}
      <div className="pointer-events-none fixed inset-0 z-0" aria-hidden>
        <div className="absolute left-[8%] top-[-14%] h-[520px] w-[720px] rounded-full bg-accent/[0.07] blur-[140px]" />
        <div className="absolute bottom-[-18%] right-[2%] h-[420px] w-[560px] rounded-full bg-accent/[0.03] blur-[150px]" />
      </div>
      <div className="grain" aria-hidden />

      {/* Floating island nav */}
      <header className="relative z-30 flex shrink-0 justify-center px-4 pt-5">
        <div className="island w-full max-w-3xl lg:w-auto lg:max-w-none">
          <button
            onClick={() => setOpen(true)}
            className="icon-btn lg:hidden"
            aria-label="Open menu — views, scope and sources"
          >
            <List className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-2 pr-3 lg:border-r lg:border-white/[0.07]">
            <Flask className="h-4 w-4 text-accent" />
            <span className="text-[13.5px] font-medium tracking-tight text-white">ResearchRAG</span>
          </div>

          {nav && <nav className="hidden gap-1 sm:flex">{nav}</nav>}

          <div className="ml-auto flex items-center gap-2 lg:ml-0 lg:border-l lg:border-white/[0.07] lg:pl-3">
            <button
              onClick={() => setKbOnly(!kbOnly)}
              className={cn("pill hidden sm:flex", kbOnly && "pill-active")}
              title={
                kbOnly
                  ? "Answers use your ingested papers only"
                  : "Falls back to live OpenAlex / web when the KB seems irrelevant"
              }
            >
              <Database className="h-3.5 w-3.5" />
              {kbOnly ? "Library only" : "Library + web"}
            </button>
            {/* Desktop-only: below `lg` the rail is the drawer, which has its
                own trigger on the left of the island. */}
            <button
              onClick={() => setRailOpen(!railOpen)}
              className={cn("icon-btn hidden lg:grid", railOpen && "text-accent")}
              title={railOpen ? "Hide sources rail" : "Show sources rail"}
              aria-label={railOpen ? "Hide sources rail" : "Show sources rail"}
              aria-expanded={railOpen}
            >
              <SidebarSimple className="h-4 w-4" />
            </button>
            <button
              onClick={logout}
              className="icon-btn"
              title={session ? `Sign out ${session.displayName}` : "Sign out"}
              aria-label="Sign out"
            >
              <SignOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Thread + rail — full bleed, so the rail stays flush with the right
          edge. Collapsing it hands the whole width back to the thread. */}
      <div
        className={cn(
          "relative z-10 grid min-h-0 flex-1 gap-6 px-4 pb-4 pt-1 lg:px-6",
          railOpen && "lg:grid-cols-[minmax(0,1fr)_clamp(288px,26vw,352px)]",
        )}
      >
        <main className="min-h-0 min-w-0">{children}</main>
        <aside
          className={cn(
            "hidden min-h-0 overflow-y-auto scrollbar-thin pb-2",
            railOpen && "rail-in lg:block",
          )}
        >
          <SidebarContent />
        </aside>
      </div>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute right-0 top-0 h-full w-[22rem] max-w-[88vw] overflow-y-auto scrollbar-thin border-l border-white/[0.07] bg-zinc-950 p-3 shadow-2xl animate-fade-up">
            <button
              onClick={() => setOpen(false)}
              className="icon-btn absolute right-4 top-4 z-10"
              aria-label="Close panel"
            >
              <X className="h-4 w-4" />
            </button>
            {/* The island nav hides below `sm`, so the drawer carries the view
                switcher and the library-scope toggle on phones. */}
            <SidebarContent showIdentity nav={nav} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
    </div>
  );
}
