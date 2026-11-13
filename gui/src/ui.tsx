// Shared controls: the editor context, labelled fields, and a drag-or-button reorder list.
import { Fragment, createContext, useContext, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { TEXT, type Key } from "./i18n";
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
export function makeCtx({ s, setS, setPicked, ...rest }: Pick<Ctx, "s" | "bad" | "giftList" | "chooseList" | "picked"> & {
  setS: (next: (prev: Settings) => Settings) => void;
  setPicked: (next: (prev: Picked) => Picked) => void;
}): Ctx {
  return {
    s, ...rest, ...translate(s.language),
    update: (fn) => setS((prev) => { const next = structuredClone(prev); fn(next); return next; }),
    pick: (list, id) => setPicked((prev) => ({ ...prev, [list]: id })),
  };
}

/** A labelled control. Its note sits outside the label, so the control's name is the label alone (a screen reader read the
 * whole note as the name); the label is `display: contents`, so the span, the control and the note lay out as siblings. */
export function Field({ label, path, note, caution, children }: {
  label: string; path?: string; note?: string; caution?: boolean; children: ReactNode;
}) {
  const { bad } = useEditor();
  return (
    <div className={"field" + (path && bad(path) ? " bad" : "")} data-path={path}>
      <label><span>{label}</span>{children}</label>
      {note && <small className={caution ? "caution" : undefined}>{withBreaks(note)}</small>}
    </div>
  );
}

/** A panel summary's note of what the panel holds (a plan's name, ★ cost, a count), quiet beside its title. */
export const Holds = ({ children }: { children: ReactNode }) => <span className="holds">{children}</span>;

/** What a red mark (a tab's or a panel's dot) says to a screen reader. */
export function ProblemMark({ on }: { on: boolean }) {
  const { t } = useEditor();
  return on ? <span className="sr-only">{t("hasProblem")}</span> : null;
}

/** Arrow keys, Home and End along a row of tabs (role=tab): the next tab is chosen and takes the focus. */
export function tabKeys<T extends string>(ids: readonly T[], current: T, choose: (id: T) => void) {
  return (e: KeyboardEvent<HTMLElement>) => {
    const at = ids.indexOf(current), last = ids.length - 1;
    const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: last }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    const next = ids[(to + ids.length) % ids.length];
    choose(next);
    e.currentTarget.parentElement?.querySelector<HTMLElement>(`[data-tab="${next}"]`)?.focus();
  };
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
    <input type="number" value={value} min={min} max={max} step={1} disabled={disabled} aria-label={label}
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

/** A switch with its number (#137): off is null and greys the number out; switched on, it starts at `on`. */
export function ToggleNum({ label, path, value, on, min, max, note, onChange }: {
  label: string; path: string; value: number | null; on: number; min: number; max?: number; note?: string;
  onChange: (v: number | null) => void;
}) {
  const { bad } = useEditor();
  return (
    <div className={"toggle" + (bad(path) ? " bad" : "")} data-path={path}>
      <label className="check">
        <input type="checkbox" checked={value !== null} onChange={(e) => onChange(e.target.checked ? on : null)} />
        {label}
      </label>
      <Num value={value ?? on} min={min} max={max} disabled={value === null} label={label} onChange={onChange} />
      {note && <small>{withBreaks(note)}</small>}
    </div>
  );
}

/** The editor's icons, drawn in one stroke on a 16-unit square: every list that sorts or removes uses these. */
const ICONS = {
  up: "M8 13.5V3M3.5 7.5 8 3l4.5 4.5",
  down: "M8 2.5V13M3.5 8.5 8 13l4.5-4.5",
  remove: "M4 4l8 8M12 4l-8 8",
  undo: "M5.5 3.5 2 7l3.5 3.5M2.5 7H10a3.5 3.5 0 0 1 0 7H7",
  lock: "M4.5 7.5h7v6h-7zM6 7.5V5.5a2 2 0 0 1 4 0v2",
  search: "M7 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM10.6 10.6 14 14",
} as const;
export const Icon = ({ name }: { name: keyof typeof ICONS }) => (
  <svg className="ic" viewBox="0 0 16 16" aria-hidden><path d={ICONS[name]} /></svg>
);
/** The handle of a row that takes a drag: two columns of three dots. */
export const Grip = ({ className = "grip" }: { className?: string }) => (
  <svg className={"ic " + className} viewBox="0 0 16 16" aria-hidden>
    {[6, 10].flatMap((x) => [3.5, 8, 12.5].map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r={1.15} />))}
  </svg>
);

/** Native HTML drag and drop, plus up/down buttons for the keyboard. Needs "dragDropEnabled": false on the Tauri
 * window (tauri.conf.json): on Windows Tauri otherwise replaces WebView2's drop handler and no HTML5 drop fires (#64).
 * Every sorted list draws its rows alike: grip, place number (`numbered`), the item, then ↑ ↓ and, with `onRemove`, ✕. */
export function ReorderList<T>({ items, onChange, render, keyOf, selected, onSelect, badAt, className, numbered, onRemove, removeLabel, nameOf }: {
  items: T[]; onChange: (items: T[]) => void; render: (item: T, i: number) => ReactNode; keyOf: (item: T) => string;
  selected?: number; onSelect?: (i: number, items: T[]) => void; badAt?: (i: number) => boolean; className?: string;
  numbered?: boolean; onRemove?: (i: number) => void; removeLabel?: string;
  /** The row's name for a screen reader: its buttons say "上移 Team a", not "上移" in every row. */
  nameOf?: (item: T) => string;
}) {
  const { t } = useEditor();
  const [dragging, setDragging] = useState<number | null>(null);
  const list = useRef<HTMLOListElement>(null);
  // The arrow just pressed, focused again once the row is drawn in its new place; the other one when it went disabled
  // (the row reached an end), so the focus does not fall to the page.
  const refocus = useRef<{ key: string; dir: "up" | "down" } | null>(null);
  useLayoutEffect(() => {
    if (!refocus.current) return;
    const { key, dir } = refocus.current;
    refocus.current = null;
    const row = [...(list.current?.children ?? [])].find((li) => (li as HTMLElement).dataset.key === key);
    const button = (d: string) => row?.querySelector<HTMLButtonElement>(`[data-mv="${d}"]`);
    const target = button(dir);
    (target?.disabled ? button(dir === "up" ? "down" : "up") : target)?.focus();
  });
  const named = (verb: string, item: T) => (nameOf ? `${verb} ${nameOf(item)}` : verb);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    next.splice(to, 0, ...next.splice(from, 1));
    onChange(next);
    if (selected === from) onSelect?.(to, next);
  };
  return (
    <ol ref={list} className={["reorder", numbered && "numbered", className].filter(Boolean).join(" ")} title={t("dragHint")}>
      {items.map((item, i) => (
        <li key={keyOf(item)} data-key={keyOf(item)} draggable
          className={[selected === i && "selected", dragging === i && "dragging", badAt?.(i) && "bad"].filter(Boolean).join(" ")}
          // A list that selects (teams, plans) is reached by Tab and picked with Enter or Space, as by a click.
          tabIndex={onSelect ? 0 : undefined} aria-current={onSelect && selected === i ? true : undefined}
          onKeyDown={(e) => { if (onSelect && e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSelect(i, items); } }}
          onClick={() => onSelect?.(i, items)}
          onDragStart={(e) => { setDragging(i); e.dataTransfer.effectAllowed = "move"; }}
          onDragEnd={() => setDragging(null)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); if (dragging !== null) move(dragging, i); setDragging(null); }}>
          <Grip />
          <span className="item">{render(item, i)}</span>
          <span className="moves">
            {/* One row has nowhere to move: no arrows. */}
            {items.length > 1 && <>
              <button type="button" className="icon" data-mv="up" aria-label={named(t("up"), item)} title={t("up")} disabled={i === 0}
                onClick={(e) => { e.stopPropagation(); refocus.current = { key: keyOf(item), dir: "up" }; move(i, i - 1); }}><Icon name="up" /></button>
              <button type="button" className="icon" data-mv="down" aria-label={named(t("down"), item)} title={t("down")} disabled={i === items.length - 1}
                onClick={(e) => { e.stopPropagation(); refocus.current = { key: keyOf(item), dir: "down" }; move(i, i + 1); }}><Icon name="down" /></button>
            </>}
            {onRemove && (
              <button type="button" className="icon remove" aria-label={named(removeLabel ?? t("remove"), item)} title={removeLabel ?? t("remove")}
                onClick={(e) => { e.stopPropagation(); onRemove(i); }}><Icon name="remove" /></button>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
