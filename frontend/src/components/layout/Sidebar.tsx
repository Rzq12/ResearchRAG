import type { ReactNode } from "react";
import { Database, Flask, SignOut } from "@phosphor-icons/react";

import { Button } from "@/components/ui/Button";
import { Toggle } from "@/components/ui/Toggle";
import { ModelSelector } from "@/components/sidebar/ModelSelector";
import { RetrievalFilters } from "@/components/sidebar/RetrievalFilters";
import { OpenAlexSearch } from "@/components/sidebar/OpenAlexSearch";
import { PdfUpload } from "@/components/sidebar/PdfUpload";
import { KnowledgeBase } from "@/components/sidebar/KnowledgeBase";
import { useAuth } from "@/context/AuthContext";
import { useSettings } from "@/context/SettingsContext";

interface SidebarContentProps {
  /** Drawer-only: the identity block (the island nav owns it on desktop). */
  showIdentity?: boolean;
  /**
   * Drawer-only: the view switcher pills. The island nav hides below `sm`, so
   * the drawer has to carry navigation — otherwise Semantic search becomes
   * unreachable on phones.
   */
  nav?: ReactNode;
  /** Called after a nav pill is picked, so the drawer can close itself. */
  onNavigate?: () => void;
}

/**
 * Source rail. Every section is its own double-bezel card instead of a flat
 * list divided by hairlines — the identity block, view switcher and scope
 * toggle only appear in the mobile drawer, since the island nav owns them on
 * desktop.
 */
export function SidebarContent({ showIdentity = false, nav, onNavigate }: SidebarContentProps) {
  const { session, logout } = useAuth();
  const { kbOnly, setKbOnly } = useSettings();

  return (
    <div className="flex flex-col gap-3.5 pt-1">
      {showIdentity && (
        <RailCard>
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.03]">
              <Flask className="h-[18px] w-[18px] text-accent" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-zinc-100">
                {session?.displayName}
              </div>
              <div className="truncate text-[11px] text-zinc-500">@{session?.userId}</div>
            </div>
            <Button variant="ghost" size="icon" onClick={logout} title="Sign out">
              <SignOut className="h-4 w-4" />
            </Button>
          </div>
        </RailCard>
      )}

      {nav && (
        <RailCard>
          <div className="space-y-3">
            <span className="eyebrow">View</span>
            {/* Clicks bubble from the pills, so one handler closes the drawer. */}
            <div className="flex flex-wrap gap-1" onClick={onNavigate}>
              {nav}
            </div>
            <Toggle
              checked={kbOnly}
              onChange={setKbOnly}
              icon={<Database className="h-4 w-4" />}
              label={kbOnly ? "Library only" : "Library + web"}
              hint={
                kbOnly
                  ? "Answers use your ingested papers only."
                  : "Falls back to live OpenAlex / web when the library seems irrelevant."
              }
            />
          </div>
        </RailCard>
      )}

      <RailCard>
        <ModelSelector />
      </RailCard>

      <RailCard>
        <KnowledgeBase />
      </RailCard>

      <RailCard>
        <div className="space-y-4">
          <OpenAlexSearch />
          <RetrievalFilters />
        </div>
      </RailCard>

      <RailCard>
        <PdfUpload />
      </RailCard>
    </div>
  );
}

function RailCard({ children }: { children: ReactNode }) {
  return (
    <section className="bezel">
      <div className="bezel-core p-4">{children}</div>
    </section>
  );
}
