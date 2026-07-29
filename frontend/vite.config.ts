import { defineConfig, type ConfigEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Fail the build when the API URL is missing in a production build.
 *
 * Previously the client fell back to http://localhost:8000, so a Vercel deploy
 * without VITE_API_BASE_URL shipped successfully and then pointed every visitor
 * at their own machine — a silent, confusing outage. Better to break the build.
 */
function assertProductionEnv({ mode }: ConfigEnv): void {
  if (mode !== "production") return;
  if (process.env.VITE_API_BASE_URL) return;

  throw new Error(
    "\n[build] VITE_API_BASE_URL is not set.\n" +
      "A production build must know where the ResearchRAG API lives.\n" +
      "Set it in Vercel → Project → Settings → Environment Variables, e.g.\n" +
      "  VITE_API_BASE_URL=https://<your-space>.hf.space\n",
  );
}

// https://vite.dev/config/
export default defineConfig((env) => {
  assertProductionEnv(env);

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
    },
    build: {
      // Split vendors so a change to app code doesn't invalidate the whole
      // bundle, and so the markdown renderer (only needed once an answer
      // arrives) is not on the critical path for first paint.
      rollupOptions: {
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom"],
            "vendor-query": ["@tanstack/react-query"],
            "vendor-markdown": ["react-markdown", "remark-gfm"],
            "vendor-icons": ["@phosphor-icons/react"],
          },
        },
      },
      chunkSizeWarningLimit: 600,
    },
  };
});
