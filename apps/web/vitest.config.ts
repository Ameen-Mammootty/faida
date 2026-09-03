import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// M7 WP-71 (decision D14): vitest for the pure decisions behind the login
// gate and for api.ts's token attach and 401 path. Node environment, no DOM
// library: the tests stub `fetch` and `window` themselves.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/__tests__/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
