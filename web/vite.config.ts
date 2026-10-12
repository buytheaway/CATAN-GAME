import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const backend = new URL(env.VITE_WS_URL || "ws://127.0.0.1:8000/ws");
  backend.protocol = backend.protocol === "wss:" ? "https:" : "http:";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      fs: {
        // Resolved raw imports can retain query/NTFS suffixes at the deny check.
        deny: [".env*", "*.{crt,pem}*", "**/.git/**"],
      },
      proxy: {
        // Same backend as the configured development WebSocket.
        "/api": backend.origin,
        "/ws": { target: backend.origin, ws: true },
      },
    },
    preview: { host: "127.0.0.1" },
  };
});
