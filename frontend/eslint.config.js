import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended, reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    rules: {
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      // This codebase uses the standard "fetch in an effect, setState in the async callback"
      // pattern throughout (no React Compiler / Suspense data layer in scope for this project).
      // eslint-plugin-react-hooks v7 flags that idiomatic pattern as an error; it is not a bug here.
      "react-hooks/set-state-in-effect": "off",
    },
  },
);
