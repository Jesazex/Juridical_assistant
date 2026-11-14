import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // Общий .env проекта; этот адрес используется только dev/preview-прокси.
  const env = loadEnv(mode, "..", "PSB_");
  const apiProxy = {
    "/api": {
      target: env.PSB_DEV_API_UPSTREAM || "http://127.0.0.1:8000",
      changeOrigin: false,
    },
  };
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: apiProxy,
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
      proxy: apiProxy,
    },
  };
});
