import { AuthPage } from "@/components/auth/AuthPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { useAuth } from "@/context/AuthContext";
import { useConfig } from "@/hooks/useServerData";
import { Spinner } from "@/components/ui/Spinner";
import { API_BASE_URL } from "@/lib/api";

export default function App() {
  const { isAuthenticated } = useAuth();
  const { isLoading, isError, error } = useConfig();

  if (isLoading) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-3 bg-zinc-950">
        <Spinner className="h-6 w-6" />
        <p className="text-sm text-muted">Connecting to the ResearchRAG API…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-zinc-950 px-4">
        <div className="max-w-md rounded-2xl border border-rose-500/30 bg-rose-950/10 p-6 text-center">
          <h2 className="text-lg font-semibold tracking-tight text-rose-200">Cannot reach the API</h2>
          <p className="mt-2 text-sm text-zinc-400">
            {(error as Error)?.message ||
              "The backend did not respond. Make sure the FastAPI server is running."}
          </p>
          <p className="mt-3 break-all text-xs text-muted">
            Configured API base URL:{" "}
            <code className="font-mono text-zinc-300">{API_BASE_URL}</code>
          </p>
          <p className="mt-2 text-xs text-muted">
            Set <code className="font-mono text-zinc-300">VITE_API_BASE_URL</code> in your environment
            and reload.
          </p>
        </div>
      </div>
    );
  }

  return isAuthenticated ? <DashboardPage /> : <AuthPage />;
}
