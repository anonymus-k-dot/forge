import { defineConfig, loadEnv } from "vite";

// The app is served by Flask at /app/ (production build in web/dist). In development, Vite
// serves it at http://127.0.0.1:5173/app/ and forwards API calls to the Flask server
// (FORGE_API_ORIGIN, default http://127.0.0.1:5000; set it in the shell or web/.env.local).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, "FORGE_");
  const api = env.FORGE_API_ORIGIN || "http://127.0.0.1:5000";
  const proxy = {
    "/enhance": { target: api },
    "/health": { target: api },
  };
  return {
    base: "/app/",
    build: {
      outDir: "dist",
      emptyOutDir: true,
      target: "es2022",
    },
    server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
    preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy },
  };
});
