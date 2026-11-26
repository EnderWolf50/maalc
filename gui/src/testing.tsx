// Test harness for the editor tabs: renders a tab inside the same EditorContext App builds, over real settings state, and lets
// the test read the settings back after the user's clicks. Not bundled (only tests import it).
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { expect } from "vitest";
import { newSettings, type Settings, type Team, type TextRun } from "./model";
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

/** A team list and its queue in the same order, as adding the teams one by one in the editor makes them (#803): to spread
 * into a test's settings. */
export const queuedTeams = (teams: Team[]) => ({ teams, team_queue: teams.map((t) => t.id) });

/** Add team `team` last in the team list, and last in the queue, as the user adds it to both (#954). */
export function addQueued(s: Settings, team: Team) {
  s.teams.push(team);
  s.team_queue.push(team.id);
}

/** The side list of a tab that shows one item at a time (the team list, a plan tab's plans): queries inside its <aside>. */
export const sideList = () => within(document.querySelector("aside")!);

/** Pick the team or plan named `name` in the side list, as the user clicks it. */
export const pickInList = (user: UserEvent, name: string) => user.click(sideList().getByText(name));

/** Move `row` of a sortable list from the keyboard, as the user does: the focus on the row, then Alt with `key`. */
export async function altMove(user: UserEvent, row: HTMLElement, key: "ArrowUp" | "ArrowDown" | "Home" | "End") {
  row.focus();
  await user.keyboard(`{Alt>}{${key}}{/Alt}`);
}

/** Where a theme pack chip holds its English name: its `.nm`, or in the Chinese UI the small `.en` under the Chinese name
 * (#899). A `getByText` selector. */
export const PACK_EN = ".pk .nm, .pk .nm .en";
/** The English name in a chip's `.nm` in name mode (the unlisted packs' chip: its label). A card with a cover holds the
 * Chinese name alone there. */
export const englishOf = (nm: Element) => (nm.querySelector(".en") ?? nm).textContent;

/** The DataTransfer a test's drag event carries: what the lists set on it (jsdom has none). */
export const dt = () => ({ setData() {}, effectAllowed: "", dropEffect: "" });

/** Pick up row `from` of a sortable list and hold it over row `to`, not dropped: what the rows show during a drag. Returns
 * the pointer leaving `to` and the drag's end (cancelled). */
export function dragHeld(from: Element, to: Element) {
  fireEvent.dragStart(from, { dataTransfer: dt() });
  fireEvent.dragOver(to, { dataTransfer: dt() });
  return { leave: () => fireEvent.dragLeave(to, { dataTransfer: dt() }), end: () => fireEvent.dragEnd(from, { dataTransfer: dt() }) };
}

/** Drag row `from` of a sortable list (ui.tsx ReorderList) onto row `to` and drop it: the HTML5 events the list handles. The
 * real window takes a drag only in the foreground or over DevTools (docs/agents/gui-driving.md). */
export function dragOnto(from: Element, to: Element) {
  dragHeld(from, to);
  fireEvent.drop(to, { dataTransfer: dt() });
  fireEvent.dragEnd(from, { dataTransfer: dt() });
}

/** A grace effect line's text, its runs joined. */
export const textOf = (runs: TextRun[]) => runs.map((r) => r.text).join("");

/** An sRGB channel (0-1) made linear, as WCAG 2 and the sRGB curve define it. */
export const linear = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const relativeLuminance = (rgb: number[]) => rgb.map(linear).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
/** WCAG 2's contrast ratio of two sRGB colours (channels 0-1). */
export const contrast = (a: number[], b: number[]) => {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

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
 * its longhands count as different properties. `at` is where the pointer or the keyboard focus is: true, a `:hover` in a
 * selector matches as with the pointer over it; an element, the pointer is over that one (`:hover` matches it and the elements
 * around it); `{ focus }`, that element has a focus that draws its ring (`:focus-visible` matches it, as the browser marks a
 * focus the keyboard moved). Without, neither ever matches: jsdom's own `:focus-visible` gives another answer the second time
 * it is asked. With `pseudo` ("::after"), the value its pseudo-element gets: only the selectors that end in it count, matched without
 * it; without, a selector with a pseudo-element never counts. */
export function cssValueOf(text: string, el: Element, prop: string, at: boolean | Element | { focus: Element } = false, pseudo = "") {
  // the elements the pointer is over (the one under it and its ancestors) and the one with the focus, marked while matching
  const pointed: Element[] = [];
  for (let x = at instanceof Element ? at : null; x; x = x.parentElement) pointed.push(x);
  const focused = typeof at === "object" && !(at instanceof Element) ? at.focus : null;
  for (const x of pointed) x.setAttribute(HOVERED, "");
  focused?.setAttribute(FOCUSED, "");
  let best: { rank: number; value: string } | undefined;
  try {
    for (const { selector, body } of cssRules(text)) {
      const declared = body.match(new RegExp(`(?:^|[;\\s])${prop}:\\s*([^;]+)`))?.[1].trim();
      if (!declared) continue;
      const value = declared.replace(/\s*!important$/, "");
      for (const whole of selectorsOf(selector)) {
        if (pseudo ? !whole.endsWith(pseudo) : whole.includes("::")) continue;
        const one = pseudo ? whole.slice(0, -pseudo.length) : whole;
        if ((at !== true && !pointed.length && one.includes(":hover")) || (!focused && one.includes(":focus-visible"))) continue;
        if (!el.matches(one.replace(/:hover/g, pointed.length ? `[${HOVERED}]` : "").replace(/:focus-visible/g, `[${FOCUSED}]`))) continue;
        const rank = specificity(one) + (value === declared ? 0 : 1e9);
        if (!best || rank >= best.rank) best = { rank, value };
      }
    }
  } finally {
    for (const x of pointed) x.removeAttribute(HOVERED);
    focused?.removeAttribute(FOCUSED);
  }
  return best?.value;
}
const HOVERED = "data-test-hovered", FOCUSED = "data-test-focused";

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
