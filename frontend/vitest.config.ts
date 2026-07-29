import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Test config is deliberately separate from `vite.config.ts`.
 *
 * Importing `vitest/config` into the build config would make a production
 * build depend on a devDependency — and this project already had one outage
 * caused by a build-config subtlety (see the VITE_API_BASE_URL guard). Keeping
 * the two files apart means `vite build` never loads anything from vitest.
 * The alias below is the only duplication, and it is three lines.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    // No `globals` — tests import { describe, it, expect } from "vitest"
    // explicitly, so nothing is injected into the global type space and
    // tsconfig needs no extra `types` entry.
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/lib/**", "src/components/ui/**"],
    },
  },
});
