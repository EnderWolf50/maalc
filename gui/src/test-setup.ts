// Vitest setup: the jest-dom matchers (toBeDisabled, toHaveAttribute, ...), a clean DOM between tests, and an empty
// localStorage for each test, which api.ts falls back on outside Tauri (the team options file, #780).
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Node 25 and later define a localStorage of their own, undefined without --localstorage-file, over jsdom's: the same
// in-memory storage on every Node, as jsdom gives one on Node 24 (CI).
if (typeof globalThis.localStorage === "undefined") {
  const items = new Map<string, string>();
  const storage: Storage = {
    get length() { return items.size; },
    clear: () => items.clear(),
    getItem: (k) => items.get(k) ?? null,
    key: (i) => [...items.keys()][i] ?? null,
    removeItem: (k) => { items.delete(k); },
    setItem: (k, v) => { items.set(k, String(v)); },
  };
  Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});
