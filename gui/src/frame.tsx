// The window's frame (#664): the navigation rail grouped by job, the sections a page stacks, and one settings row, after
// Windows 11's NavigationView, settings expander and settings card.
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Key } from "./i18n";
import { Icon, Num, PROBLEM_HINT, cautionClass, useEditor, withBreaks } from "./ui";

export interface RailItem<T extends string> { id: T; label: string; glyph: number; bad: boolean }

/** The navigation rail: groups of pages, a header over a group of several. It is a vertical tab list, as the top tab bar was
 * (tests and screen readers find a page as a tab): the arrow keys, Home and End move through the pages and open the one they
 * reach; Tab leaves the rail from the open page. The group headers are visual only (a tab list holds tabs only). */
export function Rail<T extends string>({ groups, current, onPick, label, compact }: {
  groups: { label?: Key; items: RailItem<T>[] }[]; current: T; onPick: (id: T) => void; label: string; compact: boolean;
}) {
  const { t } = useEditor();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const order = groups.flatMap((g) => g.items.map((x) => x.id));
  const onKey = (e: KeyboardEvent) => {
    const at = order.indexOf(current);
    const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: order.length - 1 }[e.key];
    if (to === undefined || e.altKey || e.ctrlKey || !order[to]) return;
    e.preventDefault();
    onPick(order[to]);
    refs.current[order[to]]?.focus();
  };
  return (
    <nav className={"rail" + (compact ? " compact" : "")} aria-label={label}>
      <div className="rail-items" role="tablist" aria-orientation="vertical" aria-label={label} onKeyDown={onKey}>
        {groups.map((g, i) => (
          <div key={i} className="rail-group" role="none">
            {g.label ? <div className="rail-head" aria-hidden>{t(g.label)}</div> : i > 0 && <hr aria-hidden />}
            {g.items.map((x) => (
              <button type="button" role="tab" key={x.id} data-tab={x.id} ref={(el) => { refs.current[x.id] = el; }}
                aria-selected={x.id === current} tabIndex={x.id === current ? 0 : -1} title={compact ? x.label : undefined}
                aria-describedby={x.bad ? PROBLEM_HINT : undefined}
                className={(x.id === current ? "selected" : "") + (x.bad ? " bad" : "")} onClick={() => onPick(x.id)}>
                <Icon glyph={x.glyph} />
                <span>{x.label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
      <span id={PROBLEM_HINT} hidden>{t("hasProblem")}</span>
    </nav>
  );
}

/** Whether the rail shows its icons only (Windows' compact navigation), remembered for this viewer; the title bar's button
 * switches it. */
export function useRailCompact() {
  const [compact, setCompact] = useState(() => remembered("rail.compact", false));
  return [compact, (on: boolean) => { setCompact(on); remember("rail.compact", on); }] as const;
}

/** This viewer's view choices (a section left open, the rail folded): browser storage can throw or be empty, so a choice
 * that cannot be read falls back to its default, and one that cannot be written is simply not remembered. */
const STORE_KEY = "maalc.gui."; // test-setup.ts clears these between tests
function remembered(id: string, fallback: boolean) {
  try {
    const v = localStorage.getItem(STORE_KEY + id);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}
function remember(id: string, on: boolean) {
  try { localStorage.setItem(STORE_KEY + id, on ? "1" : "0"); } catch { /* not remembered: still works */ }
}

/** A section of a page that folds (Windows 11's settings expander): its header says what is set inside, so a folded page
 * still reads as a summary. Open or closed is remembered per section id. A closed section opens when a problem points into it
 * (focusPath opens every <details> around a field). */
export function Section({ id, title, summary, open = false, bad, path, className, children }: {
  id: string; title: string; summary?: ReactNode; open?: boolean; bad?: boolean; path?: string; className?: string; children: ReactNode;
}) {
  const [isOpen, setOpen] = useState(() => remembered(`open.${id}`, open));
  return (
    <details className={"exp" + (className ? " " + className : "")} data-bad={bad || undefined} data-path={path} open={isOpen}
      onToggle={(e) => {
        const now = e.currentTarget.open;
        setOpen(now);
        remember(`open.${id}`, now);
      }}>
      <summary className={bad ? "bad" : undefined} aria-describedby={bad ? PROBLEM_HINT : undefined}>{title}{summary !== undefined && summary !== "" && <span className="exp-sum">{summary}</span>}</summary>
      <div className="exp-body">{children}</div>
    </details>
  );
}

/** A help longer than this folds: about three lines of a settings row's help column (Chinese runs about 2.2 characters to an
 * English word). */
const FOLD_CHARS = { zh: 90, en: 200 };
/** A first paragraph this short is shown whole when the help folds; a longer one shows its first sentence. */
const LEAD_CHARS = { zh: 60, en: 140 };
const CJK = /[㐀-鿿]/;

/** A help text under a setting. A long one shows its lead (its first paragraph when short, else its first sentence) and a
 * 顯示全部 button for the rest; a caution ("注意：") always shows whole. The whole text stays in one element, its lines split
 * by <br>, so it reads and searches as one; while folded it is hidden from the eye only (a screen reader reads it in full)
 * and the lead shown is hidden from screen readers, so they hear it once. */

export function Note({ text, block }: { text: string; block?: boolean }) {
  const { t } = useEditor();
  const [all, setAll] = useState(false);
  const caution = cautionClass(text);
  const zh = CJK.test(text), lead = text.split("\n")[0];
  const first = lead.length <= (zh ? LEAD_CHARS.zh : LEAD_CHARS.en) ? lead : lead.match(/^.*?[。！？]|^.*?[.!?](?=\s|$)/)?.[0] ?? lead;
  const long = !caution && first.length < text.length && text.length > (zh ? FOLD_CHARS.zh : FOLD_CHARS.en);
  const Tag = block ? "p" : "small";
  const body = <Tag className={[caution, block && "group-note", long && !all && "sr-only"].filter(Boolean).join(" ") || undefined}>{withBreaks(text)}</Tag>;
  if (!long) return body;
  return (
    <span className={"note" + (block ? " block" : "")}>
      {!all && <Tag className={(block ? "group-note " : "") + "preview"} aria-hidden>{first}</Tag>}
      {body}
      <button type="button" className="more" aria-expanded={all} onClick={(e) => { e.preventDefault(); setAll(!all); }}>
        {t(all ? "less" : "more")}
      </button>
    </span>
  );
}

/** A titled group of settings rows on a page (Windows 11 settings: a small heading over a stack of cards). */
export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="sgroup">
      <h3>{title}</h3>
      <div className="sgroup-rows">{children}</div>
    </section>
  );
}

/** A row whose control is a switch and a number (#137): the switch off greys the number out. Not a <label>: it holds two
 * controls, each named by the row's label. */
export function ToggleRow({ label, note, path, value, on, min, max, onChange }: {
  label: string; note?: string; path: string; value: number | null; on: number; min: number; max?: number;
  onChange: (v: number | null) => void;
}) {
  return (
    <Row many label={label} note={note} path={path} control={<>
      <input type="checkbox" className="switch" aria-label={label} checked={value !== null} onChange={(e) => onChange(e.target.checked ? on : null)} />
      <Num label={label} value={value ?? on} min={min} max={max} disabled={value === null} onChange={onChange} />
    </>} />
  );
}

/** One settings row (Windows 11's settings card): the label and its help on the left, the control on the right. The label
 * and the control share a <label> (laid out with display: contents), so a click on the label works the control and the
 * control is named by the label alone; the help sits outside it, since a label names its first control and a help's 顯示全部
 * button must not be that. A row of several controls (`many`) has no <label>: each control carries its own aria-label. */
export function Row({ label, note, path, mark, control, check, many, children }: {
  label: ReactNode; note?: string; path?: string; mark?: boolean; control?: ReactNode; check?: ReactNode; many?: boolean;
  children?: ReactNode;
}) {
  const { bad } = useEditor();
  const marked = mark ?? (path !== undefined && bad(path));
  const Main = many ? "span" : "label";
  return (
    <div className={"srow" + (check ? " check-row" : "") + (marked ? " bad" : "")} data-path={path}>
      <Main className="srow-main">
        <span className="srow-label">{label}</span>
        <span className="srow-ctl">{check ?? control}</span>
      </Main>
      {(note || children) && <span className="srow-help">{note && <Note text={note} />}{children}</span>}
    </div>
  );
}
