import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Tauri expects a fixed port (tauri.conf.json devUrl).
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    // agent/settings.schema.json and tests/settings_cases.json live outside gui/.
    fs: { allow: [".."] },
    watch: { ignored: ["**/src-tauri/**"] },
  },
  // Component tests (src/*.test.tsx) render into jsdom; the pure-function tests do not care which environment they run in.
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"] },
});
