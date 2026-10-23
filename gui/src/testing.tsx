// Test harness for the editor tabs: renders a tab inside the same EditorContext App builds, over real settings state, and lets
// the test read the settings back after the user's clicks. Not bundled (only tests import it).
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { TEXT, type Key } from "./i18n";
import { newSettings, type Settings } from "./model";
import { EditorContext, type Ctx } from "./ui";

/** Render `ui` over `initial` settings; `settings()` is what the editor holds now, `opened()` the lists something asked the
 * gift list tab to open (there is no tab bar here). */
export function renderEditor(ui: ReactElement, initial: Settings = newSettings()) {
  let current = initial;
  const opened: string[] = [];
  function Host() {
    const [s, setS] = useState(initial);
    const [giftList, setGiftList] = useState("default");
    current = s;
    const ctx: Ctx = {
      s, bad: () => false, giftList,
      chooseList: (id, open) => { setGiftList(id); if (open) opened.push(id); },
      t: (k: Key) => TEXT[s.language][k] ?? k,
      update: (fn) => setS((prev) => { const next = structuredClone(prev); fn(next); return next; }),
      tv: (field, v) => TEXT[s.language][`${field}.${v}` as Key] ?? v,
    };
    return <EditorContext.Provider value={ctx}>{ui}</EditorContext.Provider>;
  }
  return { user: userEvent.setup(), settings: () => current, opened: () => opened, ...render(<Host />) };
}
