/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // The shared .env/.env.example lives at the monorepo root, not here —
  // read VITE_ vars from there instead of requiring a duplicate file.
  envDir: "../..",
  server: {
    host: true,
    port: 5173,
  },
  test: {
    environment: "jsdom",
    // jsdom's localStorage needs a real origin — under the default
    // about:blank it's unavailable, which TenantProvider depends on.
    environmentOptions: { jsdom: { url: "http://localhost" } },
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
