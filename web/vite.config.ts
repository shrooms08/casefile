import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the FastAPI server runs on :8000 (`uv run casefile serve`); /api is proxied to it.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { port: 4173 },
});
