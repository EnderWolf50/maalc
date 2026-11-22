// Shared controls: the editor context, labelled fields, and a reorder list whose rows drag and move from the keyboard.
import {
  Fragment, createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState,
  type ComponentProps, type KeyboardEvent as ReactKeyboardEvent, type ReactNode,
} from "react";
import { TEXT, fill, type Key } from "./i18n";
import type { Settings } from "./model";

export interface Ctx {
  s: Settings;
  /** Clone the settings, let fn change the clone, keep it. */
  update: (fn: (draft: Settings) => void) => void;
  t: (k: Key) => string;
  /** Translate an enum value, "difficulty" + "hard" -> 困難. */
  tv: (field: string, v: string) => string;
  /** The GUI shows Chinese: a game name is the data's Chinese one where it has one (i18n localName). */
  zh: boolean;
  /** A failed check points at this path or something under it. */
  bad: (path: string) => boolean;
  /** The element ids of the problems that point at this path or under it, space-separated; "" for none. */
  problemIds: (path: string) => string;
  /** The gift list the gift list tab shows: "default" or a list's id. Kept here so another tab can send the user to a list. */
  giftList: string;
  /** Show that list in the gift list tab; with `open`, also switch to the tab. */
  chooseList: (id: string, open?: boolean) => void;
  /** The team or plan each list tab shows, by id. Kept here: a tab switch unmounts the tab, and its own state with it. */
  picked: Picked;
  pick: (list: keyof Picked, id: string | undefined) => void;
}
/** The lists whose tab shows one item at a time: the Run tab shows the picked task's options (#814). */
export const PICK_LISTS = ["teams", "deployment_order_plans", "starlight_plans", "theme_pack_plans", "tasks"] as const;
export type PlanKey = Exclude<(typeof PICK_LISTS)[number], "teams" | "tasks">;
/** By id, so the pick stays on its item when the list is reordered; a tab's lead (the theme packs' default plan) by its own id;
 * a task list entry by its task's id and its place among that task's entries (Run.tsx entryKey). */
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

/** useState for one team of the team page (or another item a page shows one at a time): it goes back to `initial` when
 * `scope`, the team's id, changes, so a question asked or an Undo offered for one team shows neither on the next team picked
 * nor on the first one again (#664). Reset in the render, not by a remount (`key`): the panels the user left open stay open. A
 * part with no such state to keep, the Gift Search grid, is keyed by the team instead, which resets all its state at once. */
export function useScopedState<T>(scope: string, initial: T): [T, (value: T) => void] {
  const [held, setHeld] = useState({ scope, value: initial });
  if (held.scope !== scope) setHeld({ scope, value: initial });
  return [held.scope === scope ? held.value : initial, (value) => setHeld({ scope, value })];
}

/** Delete with one step back: `remove` takes item `i` out of a list tab's items (`edit` changes that list in the settings, `pick`
 * shows an item), and the note names it with an Undo button until the next delete or until the tab closes. Undo puts it back
 * before the item that followed it, which stays right when the list changes meanwhile (TeamsTab puts a team back in the
 * queue the Agent reorders the same way, #501, #803). A confirmation
 * would stop every delete to catch the rare wrong one; this lets it go and puts it back. */
export function useUndo() {
  const [last, setLast] = useState<{ name: string; undo: () => void } | null>(null);
  const note = last && <UndoNote name={last.name} onUndo={() => { last.undo(); setLast(null); }} />;
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

/** Delete a row with one step back, for a list the Agent never reorders (override rows, a team's skill rows): `remove` takes
 * row `i` out of `rows` through `edit`, and the note names it with an Undo button that puts it back in its place (at the end
 * when the list got shorter) until the next delete. `scope` names whose rows they are (a team's id): picking another drops the
 * note, so an Undo never puts a row into the next team picked. `undone` hears the row an Undo put back and the place it had
 * (the Run tab picks a task list entry it brought back). The teams and plans use useUndo. */
export function useUndoRow<T>(edit: (fn: (rows: T[]) => void) => void, scope = "", undone?: (row: T, at: number) => void) {
  const [last, setLast] = useScopedState<{ row: T; at: number; name: string } | null>(scope, null);
  const note = last && (
    <UndoNote name={last.name} onUndo={() => {
      edit((rows) => { rows.splice(Math.min(last.at, rows.length), 0, last.row); });
      setLast(null);
      undone?.(last.row, last.at);
    }} />
  );
  const remove = (rows: T[], i: number, name: string) => {
    setLast({ row: rows[i], at: i, name: name || "—" });
    edit((list) => { list.splice(i, 1); });
  };
  return [note, remove] as const;
}

/** The note after a delete: what went, and the Undo button that puts it back. */
function UndoNote({ name, onUndo }: { name: string; onUndo: () => void }) {
  const { t } = useEditor();
  return (
    <p className="notice" role="status">
      {fill(t("undo.deleted"), { name })}{" "}
      <button type="button" onClick={onUndo}>{t("undo")}</button>
    </p>
  );
}

/** `/` focuses a search box from anywhere on the page but a field or a dialog, which have their own keys (the gift list, the theme
 * pack plan). */
export function useSlashFocus(box: { current: HTMLElement | null }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || typingIn(e.target)) return;
      e.preventDefault();
      box.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [box]);
}
/** Whether a key's target is a field or inside a dialog, whose keys are its own. */
export const typingIn = (target: EventTarget | null) =>
  !!(target as HTMLElement | null)?.closest?.("input, select, textarea, [role=dialog], [role=alertdialog]");

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
export function makeCtx({ s, setS, setPicked, ...rest }: Pick<Ctx, "s" | "problemIds" | "giftList" | "chooseList" | "picked"> & {
  setS: (next: (prev: Settings) => Settings) => void;
  setPicked: (next: (prev: Picked) => Picked) => void;
}): Ctx {
  return {
    s, ...rest, ...translate(s.language), zh: s.language === "zh_tw",
    bad: (path) => rest.problemIds(path) !== "",
    update: (fn) => setS((prev) => { const next = structuredClone(prev); fn(next); return next; }),
    pick: (list, id) => setPicked((prev) => ({ ...prev, [list]: id })),
  };
}

/** The tab a key moves to in a row of tabs: the arrows step, round at the ends; Home and End jump to them. Undefined for
 * any other key. */
export function nextTab<T>(tabs: readonly T[], at: T, key: string): T | undefined {
  const i = tabs.indexOf(at), n = tabs.length;
  const to = ({ ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: n - 1 } as Record<string, number>)[key];
  return to === undefined ? undefined : tabs[(to + n) % n];
}

/** The problem ids of the field around a control ("" for none), for its aria attributes (useMark). */
const MarkContext = createContext("");

/** The ids of more text the controls inside take as their description, after their problems' (useMark): the settings key a
 * field of the Run tab shows (Run.tsx DescribedByKey). */
export const DescribeContext = createContext("");

/** A control's aria attributes: in a field marked red, invalid and described by the problems' text, which a screen reader
 * reads with it (#695); described too by what DescribeContext names. */
export function useMark() {
  const ids = useContext(MarkContext);
  const described = [ids, useContext(DescribeContext)].filter(Boolean).join(" ");
  return { ...(ids ? { "aria-invalid": true } as const : {}), ...(described ? { "aria-describedby": described } : {}) };
}

/** The frame of a field, red when a check fails at `path` or under it, with the data-path a problem's jump finds (focusPath).
 * The controls inside take the mark (Input, Choice). `as` is its tag; `marked` false keeps the mark off, for a frame whose
 * problems are marked further in. `title` is its tooltip. */
export function Mark({ as: Tag = "div", path, className, marked = true, title, children }: {
  as?: "div" | "label" | "td"; path?: string; className?: string; marked?: boolean; title?: string; children: ReactNode;
}) {
  const { problemIds } = useEditor();
  const ids = path && marked ? problemIds(path) : "";
  return (
    <Tag className={[className, ids && "bad"].filter(Boolean).join(" ") || undefined} data-path={path} title={title}>
      <MarkContext.Provider value={ids}>{children}</MarkContext.Provider>
    </Tag>
  );
}

/** True: the controls inside (Input, Choice and what is built on them, a ReorderList) are disabled. The Run tab's settings
 * during a run, which reads them (#815). */
export const LockContext = createContext(false);

/** A plain <input> or <select> that takes the mark of its field, and the lock around it; Select, Num and Decimal are built on
 * them. */
export const Input = (props: ComponentProps<"input">) => <input {...useMark()} {...props} disabled={useContext(LockContext) || props.disabled} />;
export const Choice = (props: ComponentProps<"select">) => <select {...useMark()} {...props} disabled={useContext(LockContext) || props.disabled} />;

/** A field: its label, the control, a note under it; `title` is the tooltip of the whole field, its label included. */
export function Field({ label, path, note, title, children }: {
  label: ReactNode; path?: string; note?: string; title?: string; children: ReactNode;
}) {
  return (
    <Mark as="label" className="field" path={path} title={title}>
      <span>{label}</span>
      {children}
      {note && <small>{withBreaks(note)}</small>}
    </Mark>
  );
}

export function Select({ value, options, label, onChange }: {
  value: string; options: string[]; label?: (v: string) => string; onChange: (v: string) => void;
}) {
  return (
    <Choice value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o} value={o}>{label ? label(o) : o}</option>)}
    </Choice>
  );
}

export function Num({ value, min, max, disabled, onChange }: {
  value: number; min: number; max?: number; disabled?: boolean; onChange: (v: number) => void;
}) {
  return (
    <Input type="number" value={value} min={min} max={max} step={1} disabled={disabled}
      onChange={(e) => onChange(e.target.value === "" ? min : Math.trunc(Number(e.target.value)))} />
  );
}

/** A number with decimals (#381). A text field: a number field's value reads "" on the way from "0" to "0.5", which React
 * would write back. Each text that reads as a number of at least `min` is the value; leaving the field shows the value again. */
export function Decimal({ value, min, onChange }: { value: number; min: number; onChange: (v: number) => void }) {
  const [text, setText] = useState<string | null>(null); // null: not being typed in, the value shows
  return (
    <Input type="text" inputMode="decimal" className="decimal" value={text ?? String(value)} onBlur={() => setText(null)}
      onChange={(e) => {
        setText(e.target.value);
        const v = Number(e.target.value);
        if (e.target.value.trim() !== "" && Number.isFinite(v) && v >= min) onChange(v);
      }} />
  );
}

/** A switch with its number (#137): off is null and greys the number out; switched on, it starts at `on`. */
export function ToggleNum({ label, path, value, on, min, max, note, onChange }: {
  label: ReactNode; path: string; value: number | null; on: number; min: number; max?: number; note?: string;
  onChange: (v: number | null) => void;
}) {
  return (
    <Mark className="toggle" path={path}>
      <label className="check">
        <Input type="checkbox" checked={value !== null} onChange={(e) => onChange(e.target.checked ? on : null)} />
        {label}
      </label>
      <Num value={value ?? on} min={min} max={max} disabled={value === null} onChange={onChange} />
      {note && <small>{withBreaks(note)}</small>}
    </Mark>
  );
}

/** The place a row moves to on a key: Alt+↑ one up, Alt+↓ one down, Alt+Home first, Alt+End last; undefined for any other key
 * and for a move past either end. */
function moveKey(e: { key: string; altKey: boolean; ctrlKey: boolean; metaKey: boolean }, i: number, n: number) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return undefined;
  const to = ({ ArrowUp: i - 1, ArrowDown: i + 1, Home: 0, End: n - 1 } as Record<string, number>)[e.key];
  return to === undefined || to < 0 || to >= n || to === i ? undefined : to;
}

/** The keyboard's way to reorder a sortable list whose rows have no move buttons (ReorderList, the skill rows; #873): each row
 * takes the focus with Tab, says how it moves, and moves on Alt with an arrow, Home or End (moveKey). The moved row keeps the
 * focus, given back after the render: WebView2 moves the focus to <body> when React moves a focused row to reorder the list
 * (seen 2026-11-22; jsdom keeps it there, so the tests cannot show it). Its new place is read out (「移到第 2 位，共
 * 3 位」) by aria-live, not role="status", which the Undo note under a list is; the words come in anew each move, as a
 * screen reader reads only what the region gains, so a second move to the same place is read too. Locked (LockContext), no
 * key moves a row. `list` goes on the <ol>, `row` on each row with `onKey` from its onKeyDown (true: the key moved it),
 * `readOut` after the list. */
export function useKeyMoves(n: number, move: (from: number, to: number) => void) {
  const { t } = useEditor();
  const locked = useContext(LockContext);
  const list = useRef<HTMLOListElement>(null);
  const follow = useRef<number | null>(null);
  const [said, setSaid] = useState({ words: "", n: 0 });
  const hint = useId();
  useLayoutEffect(() => {
    if (follow.current === null) return;
    (list.current?.children[follow.current] as HTMLElement | undefined)?.focus();
    follow.current = null;
  });
  return {
    list,
    row: { tabIndex: 0, "aria-describedby": locked ? undefined : hint },
    onKey(e: ReactKeyboardEvent, i: number) {
      const to = locked || e.target !== e.currentTarget ? undefined : moveKey(e, i, n);
      if (to === undefined) return false;
      e.preventDefault();
      follow.current = to;
      move(i, to);
      setSaid((x) => ({ words: fill(t("movedTo"), { n: to + 1, of: n }), n: x.n + 1 }));
      return true;
    },
    readOut: (
      <>
        <span id={hint} className="sr-only">{t("moveHint")}</span>
        <span className="sr-only" aria-live="polite">{said.words && <span key={said.n}>{said.words}</span>}</span>
      </>
    ),
  };
}

/** A sortable list: the whole row drags (no handle, no move buttons), the dragged row dimmed and a line where it lands; from the
 * keyboard a row moves with Alt and an arrow (useKeyMoves). Native HTML drag and drop, which needs "dragDropEnabled": false on
 * the Tauri window (tauri.conf.json): on Windows Tauri otherwise replaces WebView2's drop handler and no HTML5 drop fires (#64). */
export function ReorderList<T>({ items, onChange, render, keyOf, selected, onSelect, badAt, label, help }: {
  items: T[]; onChange: (items: T[]) => void; render: (item: T, i: number) => ReactNode; keyOf: (item: T) => string;
  selected?: number; onSelect?: (i: number, items: T[]) => void; badAt?: (i: number) => boolean;
  /** the list's name, which a screen reader reads before its rows */
  label?: string;
  /** how the list works (the team queue's turns), its tooltip before how to drag it */
  help?: string;
}) {
  const { t } = useEditor();
  const locked = useContext(LockContext); // the rows still select: the Run tab shows a task's options during a run
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const move = (from: number, to: number) => {
    if (locked || to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    next.splice(to, 0, ...next.splice(from, 1));
    onChange(next);
    if (selected === from) onSelect?.(to, next);
  };
  const moves = useKeyMoves(items.length, move);
  // a row dropped lands where the row under it was: after it when dragged down, before it when dragged up
  const dropAt = (i: number) => dragging !== null && over === i && dragging !== i && (dragging < i ? "drop-after" : "drop-before");
  return (
    <>
      <ol ref={moves.list} className={"reorder" + (locked ? " locked" : "")} aria-label={label}
        title={[help, !locked && t("dragHint")].filter(Boolean).join("\n") || undefined}>
        {items.map((item, i) => (
          <li key={keyOf(item)} draggable={!locked} {...moves.row}
            className={[selected === i && "selected", dragging === i && "dragging", badAt?.(i) && "bad", dropAt(i)].filter(Boolean).join(" ")}
            // a list that selects (teams, plans) picks with Enter or Space, as by a click
            aria-current={onSelect && selected === i ? true : undefined}
            onKeyDown={(e) => {
              if (moves.onKey(e, i)) return;
              if (onSelect && e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onSelect(i, items); }
            }}
            onClick={() => onSelect?.(i, items)}
            onDragStart={(e) => { setDragging(i); e.dataTransfer.effectAllowed = "move"; }}
            onDragEnd={() => { setDragging(null); setOver(null); }}
            onDragOver={(e) => { e.preventDefault(); setOver(i); }}
            onDragLeave={() => setOver((o) => (o === i ? null : o))}
            onDrop={(e) => { e.preventDefault(); if (dragging !== null) move(dragging, i); setDragging(null); setOver(null); }}>
            {/* a wrong row says so besides its red frame: a cross, and words for a screen reader */}
            {badAt?.(i) && <span className="badmark"><span aria-hidden>✕</span><span className="sr-only">{t("hasProblem")}</span></span>}
            <span className="item">{render(item, i)}</span>
          </li>
        ))}
      </ol>
      {moves.readOut}
    </>
  );
}
