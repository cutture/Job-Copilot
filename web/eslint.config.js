import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Build output, so `eslint .` lints only the source.
  { ignores: ["dist/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
