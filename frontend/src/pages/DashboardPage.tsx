import { useState } from "react";
import { ChatText, MagnifyingGlass } from "@phosphor-icons/react";

import { AppShell } from "@/components/layout/AppShell";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { SemanticSearchPanel } from "@/components/search/SemanticSearchPanel";
import { WorkspaceProvider } from "@/context/WorkspaceContext";
import { cn } from "@/lib/utils";

type Tab = "chat" | "search";

export function DashboardPage() {
  const [tab, setTab] = useState<Tab>("chat");

  /* Tabs are pills inside the island nav instead of underlined browser tabs. */
  const nav = (
    <>
      <button
        onClick={() => setTab("chat")}
        className={cn("pill", tab === "chat" && "pill-active")}
      >
        <ChatText className="h-3.5 w-3.5" /> Assistant
      </button>
      <button
        onClick={() => setTab("search")}
        className={cn("pill", tab === "search" && "pill-active")}
      >
        <MagnifyingGlass className="h-3.5 w-3.5" /> Semantic search
      </button>
    </>
  );

  return (
    <WorkspaceProvider>
      <AppShell nav={nav}>
        <div className="h-full">
          {/* Keep both mounted so chat state survives tab switches. */}
          <div className={cn("h-full", tab !== "chat" && "hidden")}>
            <ChatPanel />
          </div>
          <div className={cn("h-full", tab !== "search" && "hidden")}>
            <SemanticSearchPanel />
          </div>
        </div>
      </AppShell>
    </WorkspaceProvider>
  );
}
