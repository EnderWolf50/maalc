// Shared controls: the editor context, labelled fields, and a drag-or-button reorder list.
import { createContext, useContext, useState, type ReactNode } from "react";
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
}
export const EditorContext = createContext<Ctx>(null!);
export const useEditor = () => useContext(EditorContext);

export function Field({ label, path, note, children }: { label: string; path?: string; note?: string; children: ReactNode }) {
  const { bad } = useEditor();
  return (
    <label className={"field" + (path && bad(path) ? " bad" : "")}>
      <span>{label}</span>
      {children}
      {note && <small>{note}</small>}
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

export function Num({ value, min, max, onChange }: { value: number; min: number; max?: number; onChange: (v: number) => void }) {
  return (
    <input type="number" value={value} min={min} max={max} step={1}
      onChange={(e) => onChange(e.target.value === "" ? min : Math.trunc(Number(e.target.value)))} />
  );
}

/** Native HTML drag and drop, plus up/down buttons for the keyboard. Needs "dragDropEnabled": false on the Tauri
 * window (tauri.conf.json): on Windows Tauri otherwise replaces WebView2's drop handler and no HTML5 drop fires (#64). */
export function ReorderList<T>({ items, onChange, render, keyOf, selected, onSelect, badAt }: {
  items: T[]; onChange: (items: T[]) => void; render: (item: T, i: number) => ReactNode; keyOf: (item: T) => string;
  selected?: number; onSelect?: (i: number) => void; badAt?: (i: number) => boolean;
}) {
  const { t } = useEditor();
  const [dragging, setDragging] = useState<number | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    next.splice(to, 0, ...next.splice(from, 1));
    onChange(next);
    if (selected === from) onSelect?.(to);
  };
  return (
    <ol className="reorder" title={t("dragHint")}>
      {items.map((item, i) => (
        <li key={keyOf(item)} draggable
          className={[selected === i && "selected", dragging === i && "dragging", badAt?.(i) && "bad"].filter(Boolean).join(" ")}
          onClick={() => onSelect?.(i)}
          onDragStart={(e) => { setDragging(i); e.dataTransfer.effectAllowed = "move"; }}
          onDragEnd={() => setDragging(null)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); if (dragging !== null) move(dragging, i); setDragging(null); }}>
          <span className="grip" aria-hidden>⋮⋮</span>
          <span className="item">{render(item, i)}</span>
          <button type="button" className="icon" aria-label={t("up")} title={t("up")} disabled={i === 0}
            onClick={(e) => { e.stopPropagation(); move(i, i - 1); }}>↑</button>
          <button type="button" className="icon" aria-label={t("down")} title={t("down")} disabled={i === items.length - 1}
            onClick={(e) => { e.stopPropagation(); move(i, i + 1); }}>↓</button>
        </li>
      ))}
    </ol>
  );
}
