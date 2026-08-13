import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import path from "path";

import { cloudflare } from "@cloudflare/vite-plugin";

// NOTE: LLM keys are NOT exposed to the client anymore. Browser calls go
// through the Cloudflare Worker proxy at /api/llm (api-worker.js), where
// the key lives as a worker secret.
export default defineConfig({
  plugins: [react(), svgr({
    svgrOptions: {
      icon: true,
      exportType: "named",
      namedExport: "ReactComponent",
    },
  }), cloudflare()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});