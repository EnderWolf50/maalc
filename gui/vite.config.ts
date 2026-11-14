import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { settingsValidatorPlugin } from "./settingsValidator";

// Tauri expects a fixed port (tauri.conf.json devUrl).
export default defineConfig({
  plugins: [react(), settingsValidatorPlugin()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    // agent/settings.schema.json and tests/settings_cases.json live outside gui/.
    fs: { allow: [".."] },
    watch: { ignored: ["**/src-tauri/**"] },
  },
  // Component tests (src/*.test.tsx) render into jsdom; the pure-function tests do not care which environment they run in.
  // The stylesheets are processed so a test can read what a rule sets (`import css from "./index.css?raw"`; unprocessed, it is "").
  test: { environment: "jsdom", setupFiles: ["./src/test-setup.ts"], css: { include: [/index\.css/, /giftlists\.css/] } },
});
