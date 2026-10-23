// Test harness for the editor tabs: renders a tab inside the same EditorContext App builds, over real settings state, and lets
// the test read the settings back after the user's clicks. Not bundled (only tests import it).
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { TEXT, type Key } from "./i18n";
import { newSettings, type Settings } from "./model";
import { EditorContext, type Ctx } from "./ui";

/** Render `ui` over `initial` settings; `settings()` is what the editor holds now. */
export function renderEditor(ui: ReactElement, initial: Settings = newSettings()) {
  let current = initial;
  function Host() {
    const [s, setS] = useState(initial);
    current = s;
    const ctx: Ctx = {
      s, bad: () => false,
      t: (k: Key) => TEXT[s.language][k] ?? k,
      update: (fn) => setS((prev) => { const next = structuredClone(prev); fn(next); return next; }),
      tv: (field, v) => TEXT[s.language][`${field}.${v}` as Key] ?? v,
    };
    return <EditorContext.Provider value={ctx}>{ui}</EditorContext.Provider>;
  }
  return { user: userEvent.setup(), settings: () => current, ...render(<Host />) };
}
