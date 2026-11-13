// Vitest setup: the jest-dom matchers (toBeDisabled, toHaveAttribute, ...), a clean DOM between tests, and no section left
// open by an earlier test (frame.tsx remembers open sections in localStorage).
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  const store = window.localStorage; // jsdom's; Node's own global localStorage is undefined without --localstorage-file
  if (!store) return;
  const keys = Array.from({ length: store.length }, (_, i) => store.key(i)).filter((k) => k?.startsWith("maalc.gui."));
  for (const k of keys) store.removeItem(k!);
});
