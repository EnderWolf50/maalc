// Shared controls: the editor context, labelled fields, and a drag-or-button reorder list.
import { Fragment, createContext, useContext, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Key } from "./i18n";
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
}
export const EditorContext = createContext<Ctx>(null!);
export const useEditor = () => useContext(EditorContext);

/** A help text as shown: each "\n" in it starts a new line, one topic to a line (#664). A text without one stays a string. */
export function withBreaks(text: string): ReactNode {
  const parts = text.split("\n");
  return parts.length === 1 ? text : parts.map((part, i) => <Fragment key={i}>{i > 0 && <br />}{part}</Fragment>);
}

/** A labelled control. Its note sits outside the label, so the control's name is the label alone (a screen reader read the
 * whole note as the name); the label is `display: contents`, so the span, the control and the note lay out as siblings. */
export function Field({ label, path, note, children }: { label: string; path?: string; note?: string; children: ReactNode }) {
  const { bad } = useEditor();
  return (
    <div className={"field" + (path && bad(path) ? " bad" : "")}>
      <label><span>{label}</span>{children}</label>
      {note && <small>{withBreaks(note)}</small>}
    </div>
  );
}

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
export function Decimal({ value, min, onChange }: { value: number; min: number; onChange: (v: number) => void }) {
  const [text, setText] = useState<string | null>(null); // null: not being typed in, the value shows
  return (
    <input type="text" inputMode="decimal" className="decimal" value={text ?? String(value)} onBlur={() => setText(null)}
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
    <div className={"toggle" + (bad(path) ? " bad" : "")}>
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
export function ReorderList<T>({ items, onChange, render, keyOf, selected, onSelect, badAt, className, numbered, onRemove, removeLabel }: {
  items: T[]; onChange: (items: T[]) => void; render: (item: T, i: number) => ReactNode; keyOf: (item: T) => string;
  selected?: number; onSelect?: (i: number, items: T[]) => void; badAt?: (i: number) => boolean; className?: string;
  numbered?: boolean; onRemove?: (i: number) => void; removeLabel?: string;
}) {
  const { t } = useEditor();
  const [dragging, setDragging] = useState<number | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    next.splice(to, 0, ...next.splice(from, 1));
    onChange(next);
    if (selected === from) onSelect?.(to, next);
  };
  return (
    <ol className={["reorder", numbered && "numbered", className].filter(Boolean).join(" ")} title={t("dragHint")}>
      {items.map((item, i) => (
        <li key={keyOf(item)} draggable
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
            <button type="button" className="icon" aria-label={t("up")} title={t("up")} disabled={i === 0}
              onClick={(e) => { e.stopPropagation(); move(i, i - 1); }}><Icon name="up" /></button>
            <button type="button" className="icon" aria-label={t("down")} title={t("down")} disabled={i === items.length - 1}
              onClick={(e) => { e.stopPropagation(); move(i, i + 1); }}><Icon name="down" /></button>
            {onRemove && (
              <button type="button" className="icon remove" aria-label={removeLabel ?? t("remove")} title={removeLabel ?? t("remove")}
                onClick={(e) => { e.stopPropagation(); onRemove(i); }}><Icon name="remove" /></button>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}
