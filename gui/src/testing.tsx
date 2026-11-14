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

// A selector's specificity as one number (ids, then classes, attributes and pseudo-classes, then types), enough for the sheet's
// own selectors; :not() counts its argument, as the cascade does, but :is() and :where() count every argument (the cascade
// takes :is()'s most specific one and nothing of :where()), so a rule using them can win here where it would lose.
const specificity = (sel: string) => (sel.match(/#[\w-]+/g) ?? []).length * 10000
  + (sel.match(/\.[\w-]+|\[[^\]]*\]|:(?!not\()[\w-]+/g) ?? []).length * 100 + (sel.match(/(?:^|[\s>+~(])[a-z][\w-]*/gi) ?? []).length;

// A selector list's selectors: split at its commas outside () and [], so `a:is(.b, .c)` stays one.
const selectorsOf = (list: string) => {
  const out = [""];
  let depth = 0;
  for (const c of list) {
    if (c === "," && depth === 0) { out.push(""); continue; }
    depth += "([".includes(c) ? 1 : ")]".includes(c) ? -1 : 0;
    out[out.length - 1] += c;
  }
  return out.map((x) => x.trim());
};

/** The value the stylesheet gives `el` for `prop` (`filter`, `background`), as the cascade picks it: of the rules that set it
 * and match `el`, an !important one first, then the most specific, the later one on a tie. What it does not read: a rule
 * inside @media counts whether or not its query holds (`cssRules` drops the @media), there are no layers, and a shorthand and
 * its longhands count as different properties. With `hover`, a `:hover` in a selector matches as with the pointer over it;
 * without, it never does. */
export function cssValueOf(text: string, el: Element, prop: string, hover = false) {
  let best: { rank: number; value: string } | undefined;
  for (const { selector, body } of cssRules(text)) {
    const declared = body.match(new RegExp(`(?:^|[;\\s])${prop}:\\s*([^;]+)`))?.[1].trim();
    if (!declared) continue;
    const value = declared.replace(/\s*!important$/, "");
    for (const one of selectorsOf(selector)) {
      if (one.includes("::") || (!hover && one.includes(":hover")) || !el.matches(one.replace(/:hover/g, ""))) continue;
      const rank = specificity(one) + (value === declared ? 0 : 1e9);
      if (!best || rank >= best.rank) best = { rank, value };
    }
  }
  return best?.value;
}

/** What a `filter` value does to an image: `light`, the share of its light left (its brightness() steps multiplied), and
 * `colour`, the share of its colour left (its saturate() steps and 1 - grayscale() multiplied: both move toward the same grey,
 * so they compose that way). An amount may be a number or a percentage; other steps are left out. */
export function filterEffect(filter = "") {
  const args = (fn: string) => [...filter.matchAll(new RegExp(`\\b${fn}\\(([\\d.]+)(%?)\\)`, "g"))]
    .map((m) => Number(m[1]) / (m[2] ? 100 : 1));
  const product = (xs: number[]) => xs.reduce((a, b) => a * b, 1);
  return { light: product(args("brightness")), colour: product(args("saturate")) * product(args("grayscale").map((g) => 1 - Math.min(g, 1))) };
}

/** Expect `text`, a help text of several lines ("\n"), to show each line on its own: every element that shows it holds the
 * lines with a <br> between each two (ui.tsx withBreaks). Fails when none does, as when the "\n" shows as a space. */
export function expectLines(text: string) {
  const lines = text.split("\n");
  expect(lines.length).toBeGreaterThan(1);
  const shown = screen.getAllByText((_, el) => !!el && el.textContent === lines.join("") && [...el.children].every((c) => c.tagName === "BR"));
  for (const el of shown) expect(el.querySelectorAll("br")).toHaveLength(lines.length - 1);
}
