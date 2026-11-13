// Shared controls: the editor context, labelled fields, and a drag-or-button reorder list.
import { Fragment, createContext, useContext, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { TEXT, fill, type Key } from "./i18n";
import type { Settings } from "./model";

export interface Ctx {
  s: Settings;
  /** Clone the settings, let fn change the clone, keep it. */
  update: (fn: (draft: Settings) => void) => void;
  t: (k: Key) => string;
  /** Translate an enum value, "difficulty" + "hard" -> 困難. */
  tv: (field: string, v: string) => string;
  /** A failed check points at this path or something under it. */
  bad: (path: string) => boolean;
  /** The gift list the gift list tab shows: "default" or a list's id. Kept here so another tab can send the user to a list. */
  giftList: string;
  /** Show that list in the gift list tab; with `open`, also switch to the tab. */
  chooseList: (id: string, open?: boolean) => void;
  /** Open a page of the editor by its tab id ("teams", "starlight"); absent where there is one page (the tests' harness). */
  openTab?: (tab: string) => void;
  /** The team or plan each list tab shows, by id. Kept here: a tab switch unmounts the tab, and its own state with it. */
  picked: Picked;
  pick: (list: keyof Picked, id: string | undefined) => void;
}
/** The lists whose tab shows one item at a time. */
export const PICK_LISTS = ["teams", "deployment_order_plans", "starlight_plans", "theme_pack_plans"] as const;
export type PlanKey = Exclude<(typeof PICK_LISTS)[number], "teams">;
/** By id, so the pick stays on its item when the list is reordered; a tab's lead (the theme packs' default plan) by its own id. */
export type Picked = Partial<Record<(typeof PICK_LISTS)[number], string>>;
export const isPickList = (section: string): section is keyof Picked => PICK_LISTS.some((x) => x === section);
export const EditorContext = createContext<Ctx>(null!);
export const useEditor = () => useContext(EditorContext);

/** The index of the item `list` shows (-1: the lead, or nothing in an empty list), and a setter by id. None picked, or the
 * picked one gone: the lead when the tab has one (`leadId`), else the first. What shows is pinned by id, so it stays on screen
 * when another writer reorders the list (#501). */
export function usePick(list: keyof Picked, items: { id: string }[], leadId?: string) {
  const { picked, pick } = useEditor();
  const at = items.findIndex((x) => x.id === picked[list]);
  const i = at >= 0 ? at : leadId !== undefined || !items.length ? -1 : 0;
  const shown = i >= 0 ? items[i].id : leadId;
  useEffect(() => { if (shown !== picked[list]) pick(list, shown); }, [list, shown, picked, pick]);
  return [i, (id: string | undefined) => pick(list, id)] as const;
}

/** Delete with one step back: `remove` takes item `i` out of a list tab's items (`edit` changes that list in the settings, `pick`
 * shows an item), and the note names it with an Undo button until the next delete or until the tab closes. Undo puts it back
 * before the item that followed it, which stays right when the Agent reorders the list meanwhile (#501). A confirmation
 * would stop every delete to catch the rare wrong one; this lets it go and puts it back. */
export function useUndo() {
  const { t } = useEditor();
  const [last, setLast] = useState<{ name: string; undo: () => void } | null>(null);
  const note = last && (
    <p className="notice" role="status">
      {fill(t("undo.deleted"), { name: last.name })}{" "}
      <button type="button" onClick={() => { last.undo(); setLast(null); }}>{t("undo")}</button>
    </p>
  );
  const remove = <T extends { id: string; name: string }>(items: T[], i: number, edit: (fn: (list: T[]) => void) => void,
    pick: (id: string | undefined) => void) => {
    const item = items[i], next = items[i + 1]?.id;
    edit((list) => { list.splice(i, 1); });
    pick(items[i - 1]?.id ?? next);
    setLast({
      name: item.name || "—",
      undo: () => {
        edit((list) => { const at = list.findIndex((x) => x.id === next); list.splice(at < 0 ? Math.min(i, list.length) : at, 0, item); });
        pick(item.id);
      },
    });
  };
  return [note, remove] as const;
}

const FOCUSABLE = "input:not(:disabled), select:not(:disabled), textarea:not(:disabled), button:not(:disabled), [tabindex]:not([tabindex='-1'])";

/** Scroll to and focus the field a problem path points at: the element in <main> whose data-path is that path or the nearest
 * one above it ("teams/1/id" finds the team's editor, "teams/1"). Closed panels around it open. The element itself takes the
 * focus when it can (a row with tabIndex -1), else its first enabled control. */
export function focusPath(path: string) {
  let el: HTMLElement | undefined;
  for (const at of document.querySelectorAll<HTMLElement>("main [data-path]")) {
    const p = at.dataset.path!;
    // on a tie the later one, inside the other in document order: a plan's editor in its tab's panel
    if ((path === p || path.startsWith(p + "/")) && p.length >= (el?.dataset.path!.length ?? 0)) el = at;
  }
  if (!el) return;
  for (let d = el.closest("details"); d; d = d.parentElement!.closest("details")) d.open = true;
  el.scrollIntoView?.({ block: "center" });
  const target = el.hasAttribute("tabindex") || el.matches(FOCUSABLE) ? el : el.querySelector<HTMLElement>(FOCUSABLE);
  target?.focus({ preventScroll: true });
}

/** A help text as shown: each "\n" in it starts a new line, one topic to a line (#664). A text without one stays a string. */
export function withBreaks(text: string): ReactNode {
  const parts = text.split("\n");
  return parts.length === 1 ? text : parts.map((part, i) => <Fragment key={i}>{i > 0 && <br />}{part}</Fragment>);
}

/** The text of one language: a key, or an enum value of a field, falls back to itself. */
export function translate(lang: Settings["language"]): Pick<Ctx, "t" | "tv"> {
  const text = TEXT[lang];
  return { t: (k) => text[k] ?? k, tv: (field, v) => text[`${field}.${v}` as Key] ?? v };
}

/** The context App and the test harness build over their settings state. */
export function makeCtx({ s, setS, setPicked, ...rest }: Pick<Ctx, "s" | "bad" | "giftList" | "chooseList" | "picked" | "openTab"> & {
  setS: (next: (prev: Settings) => Settings) => void;
  setPicked: (next: (prev: Picked) => Picked) => void;
}): Ctx {
  return {
    s, ...rest, ...translate(s.language),
    update: (fn) => setS((prev) => { const next = structuredClone(prev); fn(next); return next; }),
    pick: (list, id) => setPicked((prev) => ({ ...prev, [list]: id })),
  };
}

export function Field({ label, path, note, children }: { label: string; path?: string; note?: string; children: ReactNode }) {
  const { bad } = useEditor();
  return (
    <label className={"field" + (path && bad(path) ? " bad" : "")} data-path={path}>
      <span>{label}</span>
      {children}
      {note && <small className={cautionClass(note)}>{withBreaks(note)}</small>}
    </label>
  );
}

export function Select({ value, options, label, onChange }: {
  value: string; options: string[]; label?: (v: string) => string; onChange: (v: string) => void;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o} value={o}>{label ? label(o) : o}</option>)}
    </select>
  );
}

export function Num({ value, min, max, disabled, label, onChange }: {
  value: number; min: number; max?: number; disabled?: boolean; label?: string; onChange: (v: number) => void;
}) {
  return (
    <input type="number" aria-label={label} value={value} min={min} max={max} step={1} disabled={disabled}
      onChange={(e) => onChange(e.target.value === "" ? min : Math.trunc(Number(e.target.value)))} />
  );
}

/** A number with decimals (#381). A text field: a number field's value reads "" on the way from "0" to "0.5", which React
 * would write back. Each text that reads as a number of at least `min` is the value; leaving the field shows the value again. */
export function Decimal({ value, min, label, onChange }: { value: number; min: number; label?: string; onChange: (v: number) => void }) {
  const [text, setText] = useState<string | null>(null); // null: not being typed in, the value shows
  return (
    <input type="text" inputMode="decimal" className="decimal" aria-label={label} value={text ?? String(value)} onBlur={() => setText(null)}
      onChange={(e) => {
        setText(e.target.value);
        const v = Number(e.target.value);
        if (e.target.value.trim() !== "" && Number.isFinite(v) && v >= min) onChange(v);
      }} />
  );
}

/** Native HTML drag and drop, plus the keyboard: each row takes the focus, ↑ and ↓ go to the row above or below (and select
 * it in a list that selects), Alt+↑ and Alt+↓ move the row; the up/down buttons do the same for the mouse. Needs
 * "dragDropEnabled": false on the Tauri window (tauri.conf.json): on Windows Tauri otherwise replaces WebView2's drop handler
 * and no HTML5 drop fires (#64). */
export function ReorderList<T>({ items, onChange, render, keyOf, selected, onSelect, badAt, label }: {
  items: T[]; onChange: (items: T[]) => void; render: (item: T, i: number) => ReactNode; keyOf: (item: T) => string;
  selected?: number; onSelect?: (i: number, items: T[]) => void; badAt?: (i: number) => boolean; label?: string;
}) {
  const { t } = useEditor();
  const [dragging, setDragging] = useState<number | null>(null);
  const [focused, setFocused] = useState(0); // the row that takes Tab in a list that does not select
  const rows = useRef(new Map<string, HTMLLIElement>());
  const refocus = useRef<string | null>(null); // a row moved by the keyboard keeps the focus after React moves it
  useEffect(() => {
    if (refocus.current === null) return;
    rows.current.get(refocus.current)?.focus();
    refocus.current = null;
  });
  const stop = selected !== undefined && selected >= 0 ? selected : Math.min(focused, items.length - 1);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    next.splice(to, 0, ...next.splice(from, 1));
    onChange(next);
    if (selected === from) onSelect?.(to, next);
    setFocused(to);
  };
  const onKey = (e: KeyboardEvent, i: number) => {
    if (e.target !== e.currentTarget) return; // a button inside the row
    const to = { ArrowUp: i - 1, ArrowDown: i + 1, Home: 0, End: items.length - 1 }[e.key];
    if (to === undefined || to < 0 || to >= items.length) return;
    e.preventDefault();
    if (e.altKey) {
      if (e.key === "Home" || e.key === "End") return;
      refocus.current = keyOf(items[i]);
      move(i, to);
      return;
    }
    onSelect?.(to, items);
    setFocused(to);
    rows.current.get(keyOf(items[to]))?.focus();
  };
  return (
    <ol className={"reorder" + (onSelect ? " selecting" : "")} title={`${t("dragHint")}\n${t("list.keys")}`} aria-label={label}>
      {items.map((item, i) => (
        <li key={keyOf(item)} draggable tabIndex={i === stop ? 0 : -1} aria-current={selected === i ? "true" : undefined}
          aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown" aria-describedby={badAt?.(i) ? PROBLEM_HINT : undefined}
          ref={(el) => { if (el) rows.current.set(keyOf(item), el); else rows.current.delete(keyOf(item)); }}
          className={[selected === i && "selected", dragging === i && "dragging", badAt?.(i) && "bad"].filter(Boolean).join(" ")}
          onClick={() => { onSelect?.(i, items); setFocused(i); }}
          onKeyDown={(e) => onKey(e, i)}
          onDragStart={(e) => { setDragging(i); e.dataTransfer.effectAllowed = "move"; }}
          onDragEnd={() => setDragging(null)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); if (dragging !== null) move(dragging, i); setDragging(null); }}>
          <span className="grip" aria-hidden>⋮⋮</span>
          <span className="item">{render(item, i)}</span>
          <span className="moves">
            <button type="button" className="icon" tabIndex={-1} aria-label={t("up")} title={t("up")} disabled={i === 0}
              onClick={(e) => { e.stopPropagation(); move(i, i - 1); }}><Icon glyph={GLYPHS.up} /></button>
            <button type="button" className="icon" tabIndex={-1} aria-label={t("down")} title={t("down")} disabled={i === items.length - 1}
              onClick={(e) => { e.stopPropagation(); move(i, i + 1); }}><Icon glyph={GLYPHS.down} /></button>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The Segoe Fluent Icons glyphs (the icon font of Windows 11) the editor uses, by job: one glyph per job everywhere. */
export const GLYPHS = {
  remove: 0xe74d, // delete a team, a plan or a row
  close: 0xe711, // take an entry out of a list
  up: 0xe70e, down: 0xe70d, // move an entry
  reset: 0xe777, save: 0xe74e, error: 0xeb90, menu: 0xe700, language: 0xe774,
} as const;

/** A Segoe Fluent Icons glyph, by its code point; decorative, so screen readers skip it. */
export function Icon({ glyph, className }: { glyph: number; className?: string }) {
  return <i className={"icon-glyph" + (className ? " " + className : "")} aria-hidden>{String.fromCodePoint(glyph)}</i>;
}

/** A help text that warns about a spend starts "注意：" or "Caution:" (#682's rule for those notes): it shows as a caution. */
export const cautionClass = (text: string) => (/^(注意：|Caution:)/.test(text) ? "caution" : undefined);

/** The id of the hidden text "this has a problem" (the rail holds it): a page, section or row with a red dot points at it
 * with aria-describedby, so a screen reader says what the dot shows. */
export const PROBLEM_HINT = "problem-hint";
