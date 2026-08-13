import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import path from "path";

import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig(({ mode }) => {
  // Vite only exposes VITE_-prefixed vars to the client by default.
  // Re-expose the plain LLM_* names so src/lib/llm_client.ts can read
  // LLM_API_URL / LLM_API_KEY / LLM_MODEL straight from .env.
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react(), svgr({
      svgrOptions: {
        icon: true,
        exportType: "named",
        namedExport: "ReactComponent",
      },
    }), cloudflare()],
    define: {
      "import.meta.env.LLM_API_URL": JSON.stringify(env.LLM_API_URL ?? ""),
      "import.meta.env.LLM_API_KEY": JSON.stringify(env.LLM_API_KEY ?? ""),
      "import.meta.env.LLM_MODEL": JSON.stringify(env.LLM_MODEL ?? ""),
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  };
});