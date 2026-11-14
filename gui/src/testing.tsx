// Test harness for the editor tabs: renders a tab inside the same EditorContext App builds, over real settings state, and lets
// the test read the settings back after the user's clicks. Not bundled (only tests import it).
import { render, screen, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { expect } from "vitest";
import { newSettings, type Settings, type TextRun } from "./model";
import { EditorContext, makeCtx, type Picked } from "./ui";

/** Render `ui` over `initial` settings; `settings()` is what the editor holds now, `opened()` the lists something asked the
 * gift list tab to open (there is no tab bar here). */
export function renderEditor(ui: ReactElement, initial: Settings = newSettings()) {
  let current = initial;
  const opened: string[] = [];
  function Host() {
    const [s, setS] = useState(initial);
    const [giftList, setGiftList] = useState("default");
    const [picked, setPicked] = useState<Picked>({});
    current = s;
    const ctx = makeCtx({
      s, setS, problemIds: () => "", giftList, picked, setPicked,
      chooseList: (id, open) => { setGiftList(id); if (open) opened.push(id); },
    });
    return <EditorContext.Provider value={ctx}>{ui}</EditorContext.Provider>;
  }
  return { user: userEvent.setup(), settings: () => current, opened: () => opened, ...render(<Host />) };
}

/** The side list of a tab that shows one item at a time (the team queue, a plan tab's plans): queries inside its <aside>. */
export const sideList = () => within(document.querySelector("aside")!);

/** Pick the team or plan named `name` in the side list, as the user clicks it. */
export const pickInList = (user: UserEvent, name: string) => user.click(sideList().getByText(name));

/** A grace effect line's text, its runs joined. */
export const textOf = (runs: TextRun[]) => runs.map((r) => r.text).join("");

/** The stylesheet's plain rules, `selector { body }`, enough to read what a selector sets (`import css from "./index.css?raw"`). */
export function cssRules(text: string) {
  return [...text.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
}

/** Expect `text`, a help text of several lines ("\n"), to show each line on its own: every element that shows it holds the
 * lines with a <br> between each two (ui.tsx withBreaks). Fails when none does, as when the "\n" shows as a space. */
export function expectLines(text: string) {
  const lines = text.split("\n");
  expect(lines.length).toBeGreaterThan(1);
  const shown = screen.getAllByText((_, el) => !!el && el.textContent === lines.join("") && [...el.children].every((c) => c.tagName === "BR"));
  for (const el of shown) expect(el.querySelectorAll("br")).toHaveLength(lines.length - 1);
}
