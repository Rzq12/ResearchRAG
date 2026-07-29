// Flat config (ESLint 9+). `npm run lint` previously failed outright — the
// script existed but eslint was never a dependency and no config was present,
// so the lint gate was silently a no-op.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Build output and deps are not ours to lint.
  { ignores: ["dist/**", "node_modules/**"] },

  // Application source: browser globals, React rules.
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs["recommended-latest"].rules,
      // Fast Refresh only works when a module exports components exclusively;
      // constant exports (variants, config objects) are safe alongside them.
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // The `_` prefix marks a binding as intentionally unused.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },

  // Build tooling runs in Node, not the browser.
  {
    files: ["*.config.{js,ts}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.node,
    },
  },
);
