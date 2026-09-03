import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Review-screen files only: invoice photos come from signed, short-lived
    // storage URLs; the image optimizer would re-fetch after the signature
    // expires. Plain <img> is the right tool there (brand SVGs included).
    // Elsewhere the default rule stands.
    files: ["src/components/**", "src/app/invoices/**", "src/app/login/**"],
    rules: {
      "@next/next/no-img-element": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
