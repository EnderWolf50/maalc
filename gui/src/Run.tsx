// The Run tab (#814, #815, #816, #875, spec #811 「設定視窗」, spec #871 「版面（L1 B）」, spec 04 sections 5, 12 and 14), in two
// columns with no titles over them, whose first frames start on one line. Left, the task list (ticks, drag or Alt+↑↓: the run
// order; a row copied or removed, any task added back, #811, #877; during a run each row's state) beside the picked task's
// options (the Mirror Dungeon task's under the team queue and its start flags, #878), then the global options (folded) and the
// scheduled runs (Schedules.tsx). Right, held in view as the page scrolls,
// the run console: Start, Stop and the run's status, the emulator with the device scan, and the live log, in that order idle
// and running. A narrow window
// (NARROW) puts the console's Start line on top and its emulator and log under the options. Each control writes the settings
// key the runner or the agent reads at a task's start, and shows that key after its label while the pointer is over the field
// or the field draws a focus ring: the agent's stop lines name an option by it ("run/start_team: team 'x' was deleted ...").
// A team pick lists the settings' teams as they are now. During a run the settings it reads are locked (LockContext): a task
// still shows its options when clicked.
import {
  memo, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState,
  type KeyboardEvent as ReactKeyboardEvent, type ReactNode,
} from "react";
import { fill, type Key } from "./i18n";
import { LockIcon } from "./KeywordGrid";
import { TASK_ORDER, nextRuns, schema, type Difficulty, type LuxOptions, type Settings } from "./model";
import {
  LOG_LINES, crashed, isRunning, sameAddress, sameList, useRunner, type Device, type LogLine, type RunView,
} from "./runner";
import * as api from "./api";
import { SchedulesSection } from "./Schedules";
import {
  Choice, DescribeContext, Field, Input, LockContext, Mark, Num, ReorderList, Select, translate, useEditor, usePick, useUndoRow,
  withBreaks,
} from "./ui";

const RUN = schema.properties.run.properties as Record<string, { enum?: (string | number)[] }>;
const runEnum = (k: string) => RUN[k].enum!.map(String);
const LUX_MODES: string[] = schema.$defs.luxcavation.properties.mode.enum;
/** The task ids (agent/settings.schema.json $defs.task); a new file lists them as model.ts newSections says. */
export const TASKS: string[] = schema.$defs.task.enum;
/** The run keys every task reads (the global options): the rest of run is the Mirror Dungeon task's. */
export const GLOBAL_KEYS = ["webhook_url", "auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const;
const isGlobal = (key: string) => (GLOBAL_KEYS as readonly string[]).includes(key);
/** The settings paths that hold each task's options, a task with none left out: the one table the tab, its problem marks
 * and the read-back's notice go by. The team queue is the Mirror Dungeon task's too: only that task reads it (#878). */
const TASK_ROOTS: Record<string, string[]> = {
  MirrorDungeon: [...Object.keys(RUN).filter((k) => !isGlobal(k)).map((k) => `run/${k}`), "team_queue"],
  ExpLuxcavation: ["luxcavation/exp"], ThreadLuxcavation: ["luxcavation/thread"], ChargeEnkephalin: ["charge_enkephalin"],
};
const within = (path: string, root: string) => path === root || path.startsWith(root + "/");

/** The task whose options hold a settings path: the Run tab shows that task's options to reach the field. Undefined for a
 * global option and anything else. */
export const taskOfPath = (path: string) => Object.keys(TASK_ROOTS).find((id) => TASK_ROOTS[id].some((root) => within(path, root)));
/** A task's name in the GUI's language; an id the GUI does not know (a hand edit, which the schema check names) as it is. */
export const taskName = (t: (k: Key) => string, id: string) => (TASKS.includes(id) ? t(`task.${id}` as Key) : id);
/** The text key of a task option's label by its settings path: run/<key> is run.<key>, luxcavation/<task>/<key> lux.<key>,
 * charge_enkephalin/count charge.count. */
export const optionLabel = (path: string): Key => {
  const parts = path.split("/");
  const key = parts[parts.length - 1];
  return (parts[0] === "luxcavation" ? `lux.${key}` : parts[0] === "charge_enkephalin" ? `charge.${key}` : `run.${key}`) as Key;
};

/** The id of the element that shows settings key `path` (KeyLabel), which its field's controls take as their description. The
 * tab shows each key once. */
const keyId = (path: string) => `key:${path}`;
/** A field's label with its settings key after it, small: the key a stop line names. The key shows while the pointer is over
 * the field or the field draws a focus ring, and keeps its room while hidden, so nothing moves when it shows (index.css). It
 * stays on the label's line: in a narrow column it is cut short rather than take a second line, which put the field below
 * its neighbour's; its tooltip and a screen reader still give it whole. One span, so a switch's flex row (.check) keeps the
 * label and its key as one item. `text` is the label, by default the task option's (optionLabel). */
function KeyLabel({ path, text }: { path: string; text?: string }) {
  const { t } = useEditor();
  return (
    <span className="keyed">
      <span className="kl">{text ?? t(optionLabel(path))}</span><code className="key" id={keyId(path)} aria-hidden title={path}>{path}</code>
    </span>
  );
}
/** The id of the hidden text that holds how a field works (its tooltip), which its controls take as their description too. */
const helpId = (path: string) => `help:${path}`;
/** The controls inside take settings key `path` as their description, so a screen reader reads the field's label as its name and
 * the key after it, whether or not the key shows; then `help`, how the field works, which the eye gets as the field's tooltip
 * (spec #871: on the page stays what warns of a cost or a risk). Every field of the tab that shows a key is one of the three
 * below. */
const DescribedByKey = ({ path, help, children }: { path: string; help?: string; children: ReactNode }) => (
  <DescribeContext.Provider value={help ? `${keyId(path)} ${helpId(path)}` : keyId(path)}>
    {children}{help && <span id={helpId(path)} hidden>{help}</span>}
  </DescribeContext.Provider>
);
/** A field of the tab: its label and settings key, the control, a note; how it works (`help`) its tooltip. */
const KeyField = ({ path, label, note, help, children }: { path: string; label?: string; note?: string; help?: string; children: ReactNode }) => (
  <DescribedByKey path={path} help={help}>
    <Field label={<KeyLabel path={path} text={label} />} path={path} note={note} title={help}>{children}</Field>
  </DescribedByKey>
);
/** A switch of the tab with its note under it (#721): the label's text the size of the fields', its key after it. */
function Switch({ path, checked, note, onChange }: { path: string; checked: boolean; note?: string; onChange: (on: boolean) => void }) {
  return (
    <DescribedByKey path={path}>
      <Mark className="toggle" path={path}>
        <label className="check">
          <Input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><KeyLabel path={path} />
        </label>
        {note && <small>{withBreaks(note)}</small>}
      </Mark>
    </DescribedByKey>
  );
}
/** A switch with its number (off is null and greys the number out; switched on, it starts at `on`), laid out as the fields
 * beside it (#878, spec #871 round 5 item 4): its label and key on top in a field label's size, the switch and the number on
 * one line under it, so the number's box is level with a neighbour's select. Both controls take the label as their name. */
function KeyToggleNum({ path, value, on, min, note, onChange }: {
  path: string; value: number | null; on: number; min: number; note?: string; onChange: (v: number | null) => void;
}) {
  const label = useId();
  return (
    <DescribedByKey path={path}>
      <Mark className="field toggle-field" path={path}>
        <span id={label}><KeyLabel path={path} /></span>
        <div className="tf-line">
          <Input type="checkbox" checked={value !== null} aria-labelledby={label} onChange={(e) => onChange(e.target.checked ? on : null)} />
          <Input type="number" value={value ?? on} min={min} step={1} disabled={value === null} aria-labelledby={label}
            onChange={(e) => onChange(e.target.value === "" ? min : Math.trunc(Number(e.target.value)))} />
        </div>
        {note && <small>{withBreaks(note)}</small>}
      </Mark>
    </DescribedByKey>
  );
}

/** How many entries of entry j's task come before it (a task may be listed more than once, #811). */
const nthOf = (tasks: { id: string }[], j: number) => tasks.slice(0, j).filter((x) => x.id === tasks[j].id).length;
/** An entry's pick key: its task's id for the task's first entry, `<id>#<n>` for the one after n others, so the pick stays on
 * its entry when the list is reordered; a pick by id alone is the task's first entry. */
export const entryKey = (tasks: { id: string }[], j: number) => {
  const n = nthOf(tasks, j);
  return n ? `${tasks[j].id}#${n}` : tasks[j].id;
};

/** A task list entry as its row shows it: `key` its pick key (entryKey), `nth` its place among its task's entries (from 0),
 * `of` how many the task has. */
type Row = Settings["tasks"][number] & { key: string; nth: number; of: number };

export function RunTab() {
  const { s } = useEditor();
  const rows: Row[] = s.tasks.map((x, j) => ({
    ...x, key: entryKey(s.tasks, j), nth: nthOf(s.tasks, j), of: s.tasks.filter((y) => y.id === x.id).length,
  }));
  const [i, setSel] = usePick("tasks", rows.map((x) => ({ id: x.key })));
  const picked = rows[i];
  const { view, reveal, revealed } = useRunner();
  const locked = isRunning(view);
  const narrow = useNarrow();
  // MaaFramework's own output in the log: held here, so the log keeps it when the window crosses NARROW and moves the log
  const raw = useState(false);
  // the device scan the tab's opening starts, and whether 手動設定 is open: held here too, so a NARROW crossing, which moves
  // the emulator, neither scans again nor folds it
  const scan = useScan();
  const manual = useState(false);
  // a scheduled run's window shows its log and Stop (spec #811 「定時執行」): the console, held in view beside the list; a
  // narrow window's log, under the list and the options (Stop stays on the line held at the page's top)
  const shown = useRef<HTMLElement | null>(null);
  const keep = useCallback((el: HTMLElement | null) => { shown.current = el; }, []);
  useEffect(() => {
    if (!reveal) return;
    shown.current?.scrollIntoView?.({ block: "start" });
    revealed?.();
  }, [reveal]);
  return (
    <div className="run-page"><LockContext.Provider value={locked}>
      <div className={"run-grid" + (narrow ? " narrow" : "")}>
        {/* The run console first in the page's order, so the first Tab reaches Start. Wide, the grid draws it in the right
            column, in one order idle and running: Start, the emulator, the log, which takes the column's remaining height.
            Narrow, Start, Stop and the status are one line held at the page's top, the emulator and the log under the options. */}
        {narrow ? <RunControls /> : (
          <div className="run-console" ref={keep}>
            <RunControls />
            <EmulatorFields scan={scan} manual={manual} />
            <RunLog raw={raw} />
          </div>
        )}
        <div className="run-main">
          {/* no titles over the columns: the list, the options and the console start on one line */}
          <div className="split">
            <TaskList rows={rows} pickedAt={i} setSel={setSel} />
            <section className="task-options">{picked && <TaskOptions id={picked.id} />}</section>
          </div>
          {narrow && <><EmulatorFields scan={scan} manual={manual} /><RunLog folded raw={raw} boxRef={keep} /></>}
          <GlobalOptions />
          {/* the run reads no schedule: they stay open to edits during a run (#816) */}
          <LockContext.Provider value={false}><SchedulesSection /></LockContext.Provider>
        </div>
      </div>
    </LockContext.Provider></div>
  );
}

/** A small drawn icon of the task rows, the list's add button and the team queue's flags: a 16 px box, a 1.5 px line, drawn
 * `size` px; `filled` fills the shape too (a start team's lit flag). */
const Glyph = ({ d, filled = false, size = 14 }: { d: string; filled?: boolean; size?: number }) => (
  <svg viewBox="0 0 16 16" width={size} height={size} aria-hidden fill={filled ? "currentColor" : "none"} stroke="currentColor"
    strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);
const COPY = "M5.5 5.5h7v7h-7z M3.5 10.5v-7h7", CROSS = "M4.5 4.5l7 7 M11.5 4.5l-7 7", PLUS = "M8 3.5v9 M3.5 8h9";
const FLAG = "M4.5 14V2.5 M4.5 3h7l-1.75 2.75L11.5 8.5h-7z";

/** Whether a one-line element shows all it holds, measured again after each render and as its width changes: false once its
 * content is wider than it is. True where nothing is laid out (the tests' DOM). Its CSS must give it the same width either
 * way (index.css .tr-next.clipped), or it would go back and forth. */
function useFits<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [fits, setFits] = useState(true);
  const check = () => { const el = ref.current; if (el) setFits(el.scrollWidth <= el.clientWidth + 1); };
  useLayoutEffect(check); // the names it holds may have changed
  useLayoutEffect(() => {
    if (!ref.current || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(check);
    watch.observe(ref.current);
    return () => watch.disconnect();
  }, []);
  return [ref, fits] as const;
}

/** A difficulty as a small plate of its own, ahead of the team it names: Hard's filled, Normal's a frame, neither red (red is
 * an error's). */
function DiffPlate({ d }: { d: Difficulty }) {
  const { tv } = useEditor();
  return <b className="dchip" data-d={d}>{tv("difficulty", d)}</b>;
}

/** Whether the next runs name two teams, one a difficulty: then each mark names its difficulty with its plate. */
const splitRuns = (plays: ReturnType<typeof nextRuns>) => plays.length === 2 && plays[0].team !== plays[1].team;

/** The next Mirror Dungeon run on the task's row (spec #871 「隊伍佇列」): 「下一局」, then each difficulty's plate and its team,
 * Normal first, or the one team alone that plays every difficulty the task plays; a lit flag after them while a start team
 * is set. One line: where the names do not fit, it leaves the row, and a screen reader, rather than take a second line (the
 * queue's own marks still say it); the row is then one line high, as the others. */
function NextTeams() {
  const { s, t } = useEditor();
  const plays = nextRuns(s);
  const name = (id: string | null) => (id === null ? t("queue.no_team") : s.teams.find((x) => x.id === id)?.name || "—");
  const [line, fits] = useFits<HTMLSpanElement>();
  return (
    <span className={"tr-next" + (fits ? "" : " clipped")} ref={line} aria-hidden={fits ? undefined : true}>
      <span className="lbl">{t("queue.next")}</span>
      {splitRuns(plays)
        ? plays.map((p) => <span key={p.difficulty} className="nt-team"><DiffPlate d={p.difficulty} />{name(p.team)}</span>)
        : <span className="nt-team">{name(plays[0].team)}</span>}
      {s.run.start_team !== null && (
        <span className="flag-on" title={t("queue.flag_on")}><Glyph d={FLAG} filled /><span className="sr-only">{t("queue.flag_on")}</span></span>
      )}
    </span>
  );
}

/** Each row's state in the run the window shows, by row (spec #871 「執行中的任務清單」): the runner posts the ticked entries in
 * the list's order, so the k-th ticked row is the run's k-th task. Held while the list is the run's (runner.ts RunView list):
 * the lock keeps it so during the run, and after it the first tick, move, copy, remove or add ends them for good, as the list
 * and the run no longer read together. Null then, before a run, and when the ticked rows are not the run's tasks. */
function rowStates(tasks: Settings["tasks"], view: RunView) {
  if (!view.tasks.length || !view.list || !sameList(view.list, tasks)) return null;
  const ticked = tasks.flatMap((x, j) => (x.enabled ? [j] : []));
  if (ticked.length !== view.tasks.length || ticked.some((j, k) => tasks[j].id !== view.tasks[k].entry)) return null;
  return new Map(ticked.map((j, k) => [j, view.tasks[k]]));
}

/** The task list (spec #871 「任務清單（3B）」): each entry a row with its tick and name (#n when its task is listed more than
 * once), dragged or moved with Alt to set the run order (ReorderList). A row's copy and remove show over its end under the
 * pointer or the keyboard's focus and take no room (index.css .tr-acts); 「加入任務」 under the list adds any task. During a
 * run the list cannot change, and the line where 加入任務 was says so: the one note of the lock on the page. */
function TaskList({ rows, pickedAt, setSel }: { rows: Row[]; pickedAt: number; setSel: (key: string) => void }) {
  const { s, update, t, bad } = useEditor();
  const locked = useContext(LockContext);
  const states = rowStates(s.tasks, useRunner().view);
  // the row that says which team plays the next Mirror Dungeon run: the first ticked one, which a run plays first
  const firstMirror = s.tasks.findIndex((x) => x.id === "MirrorDungeon" && x.enabled);
  // the row the focus goes to after the render: a removed row's button, or the Undo note's, leaves with what it removed or
  // put back, and the focus would drop to the page's top; it goes to the row that took the removed one's place, or to the
  // row put back (加入任務 when the list is empty)
  const aside = useRef<HTMLElement>(null);
  const focusAt = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (focusAt.current === null) return;
    const rowEls = aside.current?.querySelectorAll<HTMLElement>("ol.reorder > li");
    (rowEls?.[Math.min(focusAt.current, rowEls.length - 1)] ?? aside.current?.querySelector<HTMLElement>(".add-task > button"))?.focus();
    focusAt.current = null;
  });
  // an Undo puts the entry back where it was and picks it, as the team list's does
  const [undoNote, removeRow] = useUndoRow<Settings["tasks"][number]>((fn) => update((d) => fn(d.tasks)), "", (row, at) => {
    const tasks = [...s.tasks];
    tasks.splice(Math.min(at, tasks.length), 0, row);
    setSel(entryKey(tasks, Math.min(at, s.tasks.length)));
    focusAt.current = Math.min(at, s.tasks.length);
  });
  // a new entry of task `id` at place `at`, unticked (it runs only once ticked), and picked: a copy right under the row it
  // copies, an add at the end
  const insertAt = (at: number, id: string) => {
    const tasks = [...s.tasks.slice(0, at), { id, enabled: false }, ...s.tasks.slice(at)];
    update((d) => { d.tasks = tasks; });
    setSel(entryKey(tasks, at));
  };
  // any row goes, a task's only one too (加入任務 lists it again); the pick stays on its entry, and moves to the row that takes
  // the removed one's place when it was the one removed (the row before, when it was the last). A pick key counts its task's
  // entries before it, so it is counted again in the list without the row.
  const removeAt = (j: number) => {
    const tasks = s.tasks.filter((_, k) => k !== j);
    removeRow(s.tasks, j, taskName(t, s.tasks[j].id));
    if (tasks.length) setSel(entryKey(tasks, j === pickedAt ? Math.min(j, tasks.length - 1) : pickedAt > j ? pickedAt - 1 : pickedAt));
    focusAt.current = j;
  };
  return (
    <aside className="task-list" data-path="tasks" ref={aside}>
      {/* a moved list's rows still carry the keys of before the move: the pick's key is counted in the list after it */}
      <ReorderList items={rows} keyOf={(x) => x.key} selected={pickedAt} onSelect={(j, list) => setSel(entryKey(list, j))}
        label={t("tasks.title")} badAt={(j) => bad(`tasks/${j}`) || (TASK_ROOTS[rows[j].id] ?? []).some(bad)}
        onChange={(moved) => update((d) => { d.tasks = moved.map(({ id, enabled }) => ({ id, enabled })); })}
        render={(x, j) => {
          const name = taskName(t, x.id);
          const copyName = fill(t("tasks.copy"), { name }), removeName = fill(t("tasks.remove"), { name });
          const task = states?.get(j); // the run's task on this row
          return (
            // its id only here, in its tooltip: the agent's stop lines name a task by it ("the ExpLuxcavation task"). Its state
            // in a run (data-state: "off" for a row the run left out, which fades) in words, their colour alone: the row itself
            // stays as it was (#871, round 4 item 5), so a running row does not read as the picked one, nor a failed one as a
            // wrong one
            <span className="task-row" title={fill(t("tasks.row_tip"), { name, id: x.id })}
              data-state={states ? task?.state ?? "off" : undefined}>
              {/* the tick's own hit area, the first line and the row's padding; a click there ticks and leaves the picked task as
                  it is */}
              <label className="tick" onClick={(e) => e.stopPropagation()}>
                <Input type="checkbox" checked={x.enabled} aria-label={fill(t(x.of > 1 ? "tasks.tick_nth" : "tasks.tick"), { name, n: x.nth + 1 })}
                  onChange={(e) => update((d) => { d.tasks[j].enabled = e.target.checked; })} />
              </label>
              <span className="tr-main">
                <span className="tr-line">
                  <span className={"tr-name" + (x.enabled ? "" : " muted")}>{name}</span>
                  {x.of > 1 && <em className="qtag" title={fill(t("tasks.entry_tip"), { n: x.nth + 1, name, of: x.of })}>#{x.nth + 1}</em>}
                </span>
                {/* until its task starts: from then the queue's head is the team playing */}
                {j === firstMirror && (!task || task.state === "pending") && <NextTeams />}
                {/* why it failed or was cancelled (runner.ts: the runner's reason, else the bot's stop line), in English
                    until #881 */}
                {task?.reason && <small className="tr-reason">{reasonText(t, task.reason, name)}</small>}
              </span>
              {task && <span className="tr-state">{t(`runner.state.${task.state}`)}</span>}
              {!locked && (
                <span className="tr-acts">
                  <button type="button" className="icon" title={copyName} aria-label={copyName}
                    onClick={(e) => { e.stopPropagation(); insertAt(j + 1, x.id); }}><Glyph d={COPY} /></button>
                  <button type="button" className="icon remove" title={removeName} aria-label={removeName}
                    onClick={(e) => { e.stopPropagation(); removeAt(j); }}><Glyph d={CROSS} /></button>
                </span>
              )}
            </span>
          );
        }} />
      {!rows.length && <p className="muted">{t("tasks.empty")}</p>}
      {/* an Undo during a run would change the list it reads: it waits for the run's end */}
      {!locked && undoNote}
      {/* under the list, not over the page: a run moves nothing in the console or the columns' tops */}
      {locked ? <p className="run-locked" role="status"><LockIcon className="lock" />{t("runner.locked")}</p> : <AddTask onPick={(id) => insertAt(s.tasks.length, id)} />}
    </aside>
  );
}

/** 「＋ 加入任務」 and its menu, which opens over the page and moves nothing under it: each task by name, in a new file's
 * order (the schema's default, model.ts TASK_ORDER), with how often the list has it where that is not once. Open, the focus
 * is on its first item; the arrows, Home and End step through it, Escape closes it back to the button, and Tab or a click
 * outside closes it too. A pick adds the task (TaskList append). */
function AddTask({ onPick }: { onPick: (id: string) => void }) {
  const { s, t } = useEditor();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useId();
  const items = () => [...(box.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? [])];
  const close = (refocus: boolean) => { setOpen(false); if (refocus) button.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    items()[0]?.focus();
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  const onKey = (e: ReactKeyboardEvent) => {
    const list = items(), at = list.indexOf(document.activeElement as HTMLButtonElement);
    const to = ({ ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: list.length - 1 } as Record<string, number>)[e.key];
    if (to !== undefined) { e.preventDefault(); list[(to + list.length) % list.length]?.focus(); }
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (e.key === "Tab") setOpen(false); // and the focus goes on to what follows, as from any other control
  };
  return (
    <div className="add-task" ref={box}>
      <button type="button" ref={button} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menu : undefined}
        onClick={() => setOpen(!open)}>
        <Glyph d={PLUS} />{t("tasks.add")}
      </button>
      {open && (
        <div className="add-menu" role="menu" id={menu} aria-label={t("tasks.add")} onKeyDown={onKey}>
          {TASK_ORDER.map((id) => {
            const n = s.tasks.filter((x) => x.id === id).length;
            return (
              // the pointer moves the focus as the arrows do: one item lit, the one a key acts on
              <button type="button" role="menuitem" tabIndex={-1} key={id} onPointerEnter={(e) => e.currentTarget.focus()}
                onClick={() => { onPick(id); close(true); }}>
                <span>{taskName(t, id)}</span><small>{n === 0 ? t("tasks.absent") : n > 1 ? fill(t("tasks.listed"), { n }) : ""}</small>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Below this width the tab is one column (index.css .run-grid.narrow): the console's column no longer fits beside the
 * options. */
const NARROW = "(max-width: 1180px)";
/** Whether the window is narrower than NARROW, followed as it is resized; false where nothing is laid out (the tests). */
function useNarrow() {
  const query = typeof matchMedia === "function" ? matchMedia(NARROW) : null;
  const [narrow, setNarrow] = useState(query?.matches ?? false);
  useEffect(() => {
    if (!query) return;
    const on = () => setNarrow(query.matches);
    query.addEventListener("change", on);
    return () => query.removeEventListener("change", on);
  }, []);
  return narrow;
}

/** Where the run got to: the running task's place among the tasks it posted, or how many ended while none runs; "" before
 * the first task starts. */
function progressOf(v: RunView) {
  const at = v.tasks.findIndex((x) => x.state === "running");
  const ended = v.tasks.filter((x) => x.state !== "pending" && x.state !== "running").length;
  return at < 0 && !ended ? "" : `${at >= 0 ? at + 1 : ended}/${v.tasks.length}`;
}

/** What the status line says of the run: nothing while idle (the buttons say it); before the first task, the connection and
 * the resource; then the task it is on, of how many; how it ended. The time it took follows outside the line (useTook). */
function statusOf(t: (k: Key) => string, v: RunView) {
  if (v.phase === "idle") return "";
  // ended before its end event: the window ended its tree after a stop, or it crashed and the run failed (spec #811). The
  // result as a phrase, its full stop left out: the time it took follows it (「已停止 · 01:29」)
  if (v.phase === "ended") return t(crashed(v) ? "runner.result.crashed" : v.exit && !v.exit.ended ? "runner.result.stopped"
    : `runner.result.${v.result ?? "failed"}`).replace(/[。.]$/, "");
  const progress = progressOf(v);
  const parts = [
    v.phase === "stopping" && t("runner.stopping"),
    ...(progress ? [progress] : [
      v.link ? fill(t(`runner.link.${v.link.state}`), { address: v.link.address }) : t("runner.status_starting"),
      v.resource && t(`runner.resource.${v.resource}`),
    ]),
  ];
  return parts.filter(Boolean).join(" · ");
}

/** A span of time as the status line shows it: 03:42, or 1:03:42 from an hour on. */
const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60;
  const mmss = `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  return h ? `${h}:${mmss}` : mmss;
};

/** A log time (HH:MM:SS.mmm, the runner's clock, runner/runlog.py) as a moment: today, or yesterday when today's is still
 * more than a minute ahead of now (a run that went past midnight). Null for a time that does not read. */
function fromClock(text: string) {
  const [h, m, s] = text.split(":").map(Number);
  if (![h, m, s].every(Number.isFinite)) return null;
  const d = new Date();
  d.setHours(h, m, Math.floor(s), Math.round((s % 1) * 1000));
  return d.getTime() > Date.now() + 60_000 ? d.getTime() - 86_400_000 : d.getTime();
}

/** How long the run has run, or ran: from its first log line (the run's line 1, while the window still keeps it), else from
 * when the window saw it start, to now; once it ended, to its last log line (the runner's `end` line), else to when the
 * window saw it end, so a page loaded again later still says how long it ran. It ticks each second while the run runs. ""
 * while idle. */
function useTook(view: RunView) {
  const running = isRunning(view);
  const was = useRef(view.phase);
  const [seen, setSeen] = useState<number | null>(() => (view.phase === "idle" ? null : Date.now()));
  const [ended, setEnded] = useState<number | null>(() => (view.phase === "ended" ? Date.now() : null));
  const [, tick] = useState(0);
  useEffect(() => {
    const before = was.current;
    was.current = view.phase;
    if (running && !isRunning({ ...view, phase: before })) { setSeen(Date.now()); setEnded(null); }
    if (view.phase === "ended" && before !== "ended") setEnded(Date.now());
  }, [view.phase]);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [running]);
  const first = view.log[0]?.n === 1 ? fromClock(view.log[0].t) : null;
  const last = view.phase === "ended" && first !== null && view.log.length ? fromClock(view.log[view.log.length - 1].t) : null;
  const from = first ?? seen;
  return view.phase === "idle" || from === null ? "" : clock((last ?? ended ?? Date.now()) - from);
}

/** The bot's English names of its tasks, as its lines write them (agent/lux_actions.py LUX), by task id. */
const BOT_NAMES: Record<string, string> = { "EXP Luxcavation": "ExpLuxcavation", "Thread Luxcavation": "ThreadLuxcavation" };
/** A task a line of the runner or the bot names, by its id or the bot's English name, longest first; not the pass page's
 * 「Clear EXP Luxcavation」 row, the game's own label the bot quotes (agent/lux_actions.py). */
const NAMED = new RegExp(`(?<!Clear )\\b(${[...Object.keys(BOT_NAMES), ...TASKS].sort((a, b) => b.length - a.length).join("|")})\\b`, "g");
/** A line with each task it names written as the list names it: 「[run] 紐本 status=failed」 for "[run] ThreadLuxcavation
 * status=failed". The runner's log file keeps the line as it came. */
const namesInList = (t: (k: Key) => string, text: string) => text.replace(NAMED, (m) => taskName(t, BOT_NAMES[m] ?? m));
/** A task's reason under its row (`name`, its task's name in the list): the tasks it names as the list names them, and the
 * row's own name in front left out, which the row says already (「defeated with the 2 retries used up」 under 紐本, for
 * "Thread Luxcavation: defeated with the 2 retries used up"). */
function reasonText(t: (k: Key) => string, reason: string, name: string) {
  const text = namesInList(t, reason);
  return text.startsWith(`${name}: `) ? text.slice(name.length + 2) : text;
}
/** A line that says a task failed or was stopped, or the run did (runner/session.py finish, error and end; agent/actions.py
 * stop): drawn in the failed state's colour. */
const FAILED_LINE = /\bstatus=(failed|stopped)\b|^\[run\] (error |end (failed|stopped)\b)|^\[maalc\] stop: /;

/** One line of the live log: its time, where it came from (a class, so the bot's own lines read apart) and its text, the tasks
 * a line of the runner or the bot names as the list names them (`rename`, one function a language, so the rows already
 * drawn are not drawn again at each new line), the line as it came its tooltip; a failure's line in the failed state's
 * colour. */
const LogRow = memo(function LogRow({ line, rename }: { line: LogLine; rename: (text: string) => string }) {
  const ours = line.source === "runner" || line.source === "agent";
  const text = ours ? rename(line.line) : line.line;
  return (
    <li className={`src-${line.source}` + (ours && FAILED_LINE.test(line.line) ? " failed" : "")} title={text !== line.line ? line.line : undefined}>
      <time>{line.t}</time><span>{text}</span>
    </li>
  );
});

/** Start (it saves first), Stop and what the run is doing, on the page itself with no frame of their own. Idle, the status
 * says nothing: the buttons say it. A save under way says so in the status, not on a line of its own under the buttons,
 * which would move the console down as Start is pressed. Why Start is off, and how a start or a run went wrong, show under
 * the line in a block of their own, which a narrow window does not hold at the page's top with the line. */
function RunControls() {
  const { t } = useEditor();
  const { view, start, stop, blocked } = useRunner();
  const running = isRunning(view);
  const took = useTook(view);
  const saving = blocked === "saving" && !running;
  const notes = [
    blocked && !saving && !running && <p key="blocked" className="caution">{t(`runner.blocked_${blocked}`)}</p>,
    view.refused && <p key="refused" className="caution" role="alert">{fill(t("runner.refused"), { error: view.refused })}</p>,
    view.killed && <p key="killed" className="caution" role="alert">{fill(t("runner.killed"), { reason: view.killed })}</p>,
  ].filter(Boolean);
  return (<>
    <div className="runner run-controls">
      <div className="runner-bar">
        {/* how Start works is its tooltip */}
        <button type="button" className="primary" title={t("runner.start_note")} disabled={running || blocked !== null} onClick={start}>
          {t("runner.start")}
        </button>
        <button type="button" disabled={view.phase !== "running"} onClick={stop}>
          {view.phase === "stopping" ? t("runner.stopping") : t("runner.stop")}
        </button>
        {/* the clock after the status, outside its live region: a screen reader reads the state as it changes, not each second */}
        <span className="runner-state">
          <span className="runner-status" role="status" data-phase={view.phase}>{saving ? t("runner.blocked_saving") : statusOf(t, view)}</span>
          {took && <span className="runner-took"> · {took}</span>}
        </span>
      </div>
    </div>
    {notes.length > 0 && <div className="runner run-notes">{notes}</div>}
  </>);
}

/** The live log (the last LOG_LINES lines, MaaFramework's own output hidden unless `raw` asks for it) and how a run that
 * crashed ended. In the console's column it takes the column's remaining height, empty but for one faint line
 * until a run logs. `folded` (a narrow window, under the list and the options) it is a panel, folded until a run starts. How
 * much the window keeps and where the whole log is: its title's tooltip. `boxRef` takes its frame. */
function RunLog({ folded = false, raw: [showConsole, setShowConsole], boxRef }: {
  folded?: boolean; raw: [boolean, (on: boolean) => void]; boxRef?: (el: HTMLElement | null) => void;
}) {
  const { t, s } = useEditor();
  const { view } = useRunner();
  const running = isRunning(view);
  const rename = useMemo(() => {
    const { t: inLanguage } = translate(s.language);
    return (text: string) => namesInList(inLanguage, text);
  }, [s.language]);
  // the frame's name is its title alone, not the switch beside it
  const title = useId();
  const [open, setOpen] = useState(running || view.log.length > 0);
  useEffect(() => { if (running) setOpen(true); }, [running]);
  const shown = showConsole ? view.log : view.log.filter((l) => l.source !== "console");
  // the log follows its newest line while the user has not scrolled up from the bottom
  const pane = useRef<HTMLOListElement>(null);
  const follow = useRef(true);
  useLayoutEffect(() => { if (follow.current && pane.current) pane.current.scrollTop = pane.current.scrollHeight; }, [view.log, showConsole, open]);
  const note = fill(t("runner.log_note"), { n: LOG_LINES });
  // the title, then the raw-output switch at its right: a click on the switch ticks it, and folds no panel
  const head = (<>
    <span className="lg-title" id={title} title={note}>{t("runner.log")}</span>
    <label className="check" title={t("runner.console_note")}>
      <input type="checkbox" checked={showConsole} onChange={(e) => setShowConsole(e.target.checked)} />{t("runner.console")}
    </label>
  </>);
  const body = (<>
    {crashed(view) && (
      <div className="crash" role="alert">
        <p>{fill(t("runner.crash"), { code: view.exit!.code ?? "—" })}</p>
        <pre>{view.exit!.tail.join("\n")}</pre>
      </div>
    )}
    <div className="log-well">
      <ol className={"run-log" + (shown.length ? "" : " empty")} ref={pane} aria-label={t("runner.log")} tabIndex={0}
        onScroll={(e) => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24; }}>
        {shown.map((l) => <LogRow key={l.n} line={l} rename={rename} />)}
      </ol>
      {!shown.length && <small className="log-empty">{t("runner.log_empty")}</small>}
    </div>
  </>);
  if (folded) return (
    <details className="panel runner run-log-box" ref={boxRef} aria-labelledby={title} open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{head}</summary>
      {body}
    </details>
  );
  return (
    <fieldset className="runner run-log-box" ref={boxRef} aria-labelledby={title}>
      <legend>{head}</legend>
      {body}
    </fieldset>
  );
}

/** The picked task's options, under no title of their own: the Mirror Dungeon task's groups carry their own titles, and another
 * task's options sit in one frame titled with its name. Its id (the agent's stop lines name a task by it, "the
 * ExpLuxcavation task") is not on the page. */
function TaskOptions({ id }: { id: string }) {
  const { t } = useEditor();
  if (id === "MirrorDungeon") return <MirrorOptions />;
  const fields: Record<string, ReactNode> = {
    ExpLuxcavation: <LuxFields task="exp" />, ThreadLuxcavation: <LuxFields task="thread" />, ChargeEnkephalin: <ChargeFields />,
  };
  return (
    <fieldset className="task-opts">
      <legend>{taskName(t, id)}</legend>
      {fields[id] ?? <p className="muted">{t("tasks.none")}</p>}
    </fieldset>
  );
}

/** The Mirror Dungeon task's options (spec 04 section 5): the team queue, which only this task reads, the box's whole width on
 * top (#878), then three groups by what they decide: the run itself, the weekly bonuses, what happens when something fails. */
function MirrorOptions() {
  const { s, update, t, tv } = useEditor();
  const run = s.run;
  const pastFive = run.target_floor > 5;
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  type Pick = "difficulty" | "weekly_bonus_use" | "weekly_bonus_amount" | "starlight_unaffordable" | "after_retries" | "theme_pack_refresh";
  const pick = (k: Pick, note?: string) => (
    <KeyField path={`run/${k}`} note={note}>
      <Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />
    </KeyField>
  );
  return (
    <div className="groups">
      <MirrorTeams />
      <fieldset>
        <legend>{t("run.group_run")}</legend>
        <div className="grid">
          {pick("difficulty")}
          <KeyField path="run/target_floor" note={pastFive ? t("run.target_floor_note") : undefined}>
            <Select value={String(run.target_floor)} options={runEnum("target_floor")} label={(v) => tv("target_floor", v)}
              onChange={(v) => set({ target_floor: Number(v) })} />
            {/* Remove once the probe runs (#853-#856) have played floors 6-15 live: until then a screen there may be unknown. */}
            {pastFive && <small>{t("run.target_floor_entry_note")}</small>}
          </KeyField>
          <KeyToggleNum path="run/runs" value={run.runs} on={1} min={1} note={t("run.runs_note")} onChange={(v) => set({ runs: v })} />
          {pick("theme_pack_refresh", t("run.theme_pack_refresh_note"))}
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_weekly")}</legend>
        <div className="grid">
          {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
          {pick("weekly_bonus_amount")}
          <Switch path="run/stop_when_weekly_bonus_out" checked={run.stop_when_weekly_bonus_out}
            onChange={(on) => set({ stop_when_weekly_bonus_out: on })} />
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_failure")}</legend>
        <div className="grid">
          {pick("starlight_unaffordable")}
          <KeyField path="run/wipe_retries">
            <Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} />
          </KeyField>
          {pick("after_retries", t("run.after_retries_note"))}
        </div>
      </fieldset>
    </div>
  );
}

/** The team queue at the top of the Mirror Dungeon options (#878, spec #871 「隊伍佇列（只在鏡牢選項裡）」, ADR 0014):
 * team_queue in its order, dragged or moved with Alt (its moves change team_queue only; the Agent's show once the window reads
 * them). Every row on the list's own columns (index.css): its place, the team's name (cut short), its slot, its usage when kept
 * to one difficulty, the next-run mark against the flag, and the flag. A disabled team is struck through in its place; an id
 * that names no team (a hand edit, which the check names) is a row of its own. The flag writes run.start_team: on, off, one
 * team at most, none on a disabled team but to clear it. How the queue turns is the list's tooltip; under it, while a flag is
 * set, what it costs or why the task will stop. A run locks the order and the flags (LockContext). */
function MirrorTeams() {
  const { s, update, t, tv, bad } = useEditor();
  const locked = useContext(LockContext);
  const byId = new Map(s.teams.map((x) => [x.id, x]));
  // an id twice (a hand edit, which the check names) still gets a row of its own: `repeat` counts its rows before this one
  const seen = new Map<string, number>();
  const rows = s.team_queue.map((id) => { const repeat = seen.get(id) ?? 0; seen.set(id, repeat + 1); return { id, repeat }; });
  const plays = nextRuns(s), split = splitRuns(plays);
  const start = s.run.start_team;
  const setStart = (id: string | null) => update((d) => { d.run.start_team = id; });
  // the start team's state: set on an enabled team (the flag stays in the file), on a disabled or a deleted one (the agent
  // stops the task at its start, task_options.py start_team_errors): a deleted one has no row whose flag clears it
  const flagged = start === null ? null : byId.get(start);
  const said = start === null ? null : !flagged ? "gone" : flagged.enabled ? "kept" : "off";
  return (
    <fieldset className="mirror-teams" data-path="team_queue">
      <legend>{t("queue.title")}</legend>
      <div className="mt-order" data-path="run/start_team">
        {rows.length > 0 && (
          <ReorderList items={rows} keyOf={(x) => (x.repeat ? `${x.id}#${x.repeat}` : x.id)} badAt={(j) => bad(`team_queue/${j}`)}
            label={t("queue.title")} help={t("queue.help")}
            onChange={(moved) => update((d) => { d.team_queue = moved.map((x) => x.id); })}
            render={(x, j) => {
              const team = byId.get(x.id), first = x.repeat === 0;
              const on = first && start === x.id, off = team !== undefined && !team.enabled;
              const name = team ? team.name || "—" : `? ${x.id}`;
              // the runs this row's team plays next, on its first row
              const marks = first ? plays.filter((p) => p.team === x.id) : [];
              return (
                // the cells a space apart, which a grid does not draw, so the row reads as words; the name takes a problem's jump
                <span className={"mt-row" + (off ? " off" : "")} title={off ? t("queue.off_tip") : undefined}>
                  <span className="place">{j + 1}</span>{" "}
                  <span className="mt-name" data-path={`team_queue/${j}`} tabIndex={-1}>
                    {name}{off && <span className="sr-only">{t("team.off_read")}</span>}
                  </span>{" "}
                  <small className="mt-slot">{team && `TEAMS #${team.game_team}`}</small>{" "}
                  <span className="mt-use">{team && team.usage !== "any" && <em className="qtag">{tv("usage", team.usage)}</em>}</span>{" "}
                  <span className="mt-mark">
                    {marks.length > 0 && <span className="mt-next">{t("queue.next")}{split && marks.map((p) => <DiffPlate key={p.difficulty} d={p.difficulty} />)}</span>}
                  </span>
                  {team ? (
                    // its words are drawn over it (index.css .start-flag::after); title="" keeps the list's own tooltip off them
                    <button type="button" className={"start-flag" + (on ? " on" : "")} aria-pressed={on}
                      aria-label={fill(t(on ? "queue.flag_clear" : "queue.flag_set"), { name })} title=""
                      data-tip={t(on ? "queue.flag_tip_on" : "queue.flag_tip")} disabled={locked || (off && !on)}
                      onClick={(e) => { e.stopPropagation(); setStart(on ? null : x.id); }}>
                      <Glyph d={FLAG} filled={on} size={16} />
                    </button>
                  ) : <span />}
                </span>
              );
            }} />
        )}
      </div>
      {said === "kept" && <p className="muted mt-note">{t("queue.flag_kept")}</p>}
      {said === "off" && <p className="caution mt-note">{t("queue.flag_off_note")}</p>}
      {said === "gone" && (
        <p className="caution mt-note">
          {fill(t("queue.flag_gone_note"), { id: start! })}{" "}
          <button type="button" disabled={locked} onClick={() => setStart(null)}>{t("queue.flag_clear_gone")}</button>
        </p>
      )}
    </fieldset>
  );
}

/** A Luxcavation task's team pick: `none` first (null), then the settings' teams as they are now, by name and slot. A team
 * deleted since stays the value, shown as deleted with why the task will stop, until another is picked: the agent stops the
 * task at its start over it. */
function TeamPick({ value, none, onChange }: { value: string | null; none: string; onChange: (v: string | null) => void }) {
  const { s, t } = useEditor();
  const ids = s.teams.map((x) => x.id);
  const gone = value !== null && !s.teams.some((x) => x.id === value);
  const label = (id: string) => {
    if (id === "") return none;
    const x = s.teams.find((y) => y.id === id);
    return x ? fill(t("teamPick"), { name: x.name || "—", slot: x.game_team }) : fill(t("teamPick.gone"), { id });
  };
  return (<>
    <Select value={value ?? ""} options={["", ...ids, ...(gone ? [value] : [])]} label={label} onChange={(v) => onChange(v || null)} />
    {gone && <small className="caution">{t("teamPick.gone_note")}</small>}
  </>);
}

/** A Luxcavation task's options (spec 04 section 12). */
function LuxFields({ task }: { task: keyof Settings["luxcavation"] }) {
  const { s, update, t, tv } = useEditor();
  const opts = s.luxcavation[task];
  const set = (patch: Partial<LuxOptions>) => update((d) => { Object.assign(d.luxcavation[task], patch); });
  const path = `luxcavation/${task}`;
  return (
    <div className="stack">
      <p className="muted">{withBreaks(t(`lux.${task}_note`))}</p>
      <div className="grid">
        <KeyField path={`${path}/mode`}>
          <Select value={opts.mode} options={LUX_MODES} label={(v) => tv("lux_mode", v)} onChange={(v) => set({ mode: v })} />
        </KeyField>
        <KeyField path={`${path}/count`} note={opts.mode === "daily" ? t("lux.count_unused") : undefined}>
          <Num value={opts.count} min={1} disabled={opts.mode === "daily"} onChange={(v) => set({ count: v })} />
        </KeyField>
        <KeyField path={`${path}/team`} note={t("lux.team_note")}>
          <TeamPick value={opts.team} none={t("lux.team_none")} onChange={(v) => set({ team: v })} />
        </KeyField>
        <Switch path={`${path}/consecutive`} checked={opts.consecutive} note={t("lux.consecutive_note")}
          onChange={(on) => set({ consecutive: on })} />
        <KeyField path={`${path}/retries`} note={t("lux.retries_note")}>
          <Num value={opts.retries} min={0} onChange={(v) => set({ retries: v })} />
        </KeyField>
      </div>
    </div>
  );
}

/** Charge Enkephalin's count (spec 04 section 12): it spends Lunacy, which its note says first. */
function ChargeFields() {
  const { s, update, t } = useEditor();
  return (
    <div className="stack">
      <p className="caution">{withBreaks(t("charge.note"))}</p>
      <div className="grid">
        <KeyField path="charge_enkephalin/count">
          <Num value={s.charge_enkephalin.count} min={0} max={10} onChange={(v) => update((d) => { d.charge_enkephalin.count = v; })} />
        </KeyField>
      </div>
    </div>
  );
}

/** The four options every task reads (spec 04 section 5): the webhook and three switches, each with its note, in a panel
 * folded at first (the user's call, 2026-11-20). Folded, its title turns red when one of them has a problem; a problem's
 * jump opens it (ui.tsx focusPath). */
function GlobalOptions() {
  const { s, update, t, bad } = useEditor();
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  return (
    <details className={"panel globals" + (GLOBAL_KEYS.some((k) => bad(`run/${k}`)) ? " bad" : "")}>
      <summary>{t("globals.title")}</summary>
      <p className="muted">{t("globals.note")}</p>
      <div className="grid">
        <KeyField path="run/webhook_url" note={t("run.webhook_url_note")}>
          <Input type="url" value={s.run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />
        </KeyField>
        {GLOBAL_KEYS.filter((k): k is Exclude<typeof k, "webhook_url"> => k !== "webhook_url").map((k) => (
          <Switch key={k} path={`run/${k}`} checked={s.run[k]} note={t(`run.${k}_note`)} onChange={(on) => set({ [k]: on })} />
        ))}
      </div>
    </details>
  );
}

/** The last device scan: none yet, under way, the devices it found, or why it found none. */
type Scan = { state: "none" } | { state: "scanning" } | { state: "found"; devices: Device[] } | { state: "failed"; error: string };

/** The device scan (#876): once as the tab opens, unless a run is under way or starting then (偵測 is locked until it ends;
 * the user's call, 2026-11-20), and at each press of 偵測 or 重新偵測. It lists the adb devices only and connects to none.
 * The first scan waits until the window knows whether a run is under way or starting (Runner.settled: a page loaded again
 * during a run, a window a schedule opened). A tab that opens to a scan shows it under way from its first frame, so 偵測
 * does not flash before 偵測中…; the development build's second start of the effect does not scan again. */
function useScan() {
  const { view, blocked, settled = true } = useRunner();
  const busy = isRunning(view) || blocked === "saving"; // a run, or a start's save and launch
  const [scan, setScan] = useState<Scan>(() => (busy ? { state: "none" } : { state: "scanning" }));
  const find = () => {
    setScan({ state: "scanning" });
    api.scanDevices().then((devices) => setScan({ state: "found", devices }), (e) => setScan({ state: "failed", error: String(e) }));
  };
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current || !settled) return;
    asked.current = true;
    if (busy) setScan({ state: "none" });
    else find();
  }, [settled]);
  return { scan, find };
}

/** A MuMu instance at its address, as the pick list names it. */
const mumuName = (t: (k: Key) => string, index: number, address: string) => fill(t("emu.device_mumu"), { index, address });

/** A device of a scan as its pick list names it: a MuMu one by its instance. */
const deviceName = (t: (k: Key) => string, d: Device) =>
  d.mumu ? mumuName(t, d.mumu.index, d.address) : fill(t("emu.device"), { name: d.name, address: d.address });

/** What a pick of a scanned device writes: its address, and its MuMu instance and MuMuManager.exe (none for another). */
const pickOf = (d: Device): Settings["emulator"] => ({ address: d.address, mumu_index: d.mumu?.index ?? null, mumu_manager: d.mumu?.manager ?? null });

/** The pick list's entry for the emulator the settings name, while it lists no device that is that one: the MuMu instance at
 * its address, the address alone, or none set. */
const currentLabel = (t: (k: Key) => string, e: Settings["emulator"]) => e.address === null ? t("emu.unset")
  : fill(t("emu.current"), { device: e.mumu_index === null ? e.address : mumuName(t, e.mumu_index, e.address) });

/** The emulator the runner connects to (4A, spec 04 section 14): one pick list of the emulators the scan found, MuMu first,
 * 偵測 beside it; before a scan's devices come, the list holds what the settings name. A pick fills in the three values,
 * saved with the rest. A scan under way says so on its button, not on a line of its own (it moved the log 26 px at each
 * open of the tab), and what it found is the list itself: only finding none, or failing, takes a line under them. The three
 * values' own fields fold under 手動設定 (`manual`, open or not). During a run the whole frame is locked. */
function EmulatorFields({ scan: { scan, find }, manual: [open, setOpen] }: {
  scan: ReturnType<typeof useScan>; manual: [boolean, (open: boolean) => void];
}) {
  const { s, update, t, bad } = useEditor();
  const set = (patch: Partial<Settings["emulator"]>) => update((d) => { Object.assign(d.emulator, patch); });
  const text = (v: string) => (v.trim() === "" ? null : v);
  const running = isRunning(useRunner().view);
  const found = scan.state === "found" ? scan.devices : [];
  // The list shows a device only when the fields already hold all that a pick of it writes, and the settings' own entry to
  // pick from otherwise. A select fires no change for the option it shows, so a list that showed the device at the address
  // alone (after MXU's read-back, which keeps no instance or MuMuManager) could not fill the other two (#833).
  const current = s.emulator;
  const at = found.findIndex((d) => {
    const writes = pickOf(d);
    return current.address !== null && sameAddress(d.address, current.address)
      && writes.mumu_index === current.mumu_index && writes.mumu_manager === current.mumu_manager;
  });
  const label = currentLabel(t, current);
  // a scan that found none, or failed, says so on a line under the list, which describes the list to a screen reader too;
  // what to do next after finding none is that line's tooltip, and read after it
  const outcomeId = useId(), nextId = `${outcomeId}-next`;
  const none = scan.state === "found" && !found.length;
  const described = none ? `${outcomeId} ${nextId}` : scan.state === "failed" ? outcomeId : "";
  return (
    <fieldset className="emulator" data-path="emulator">
      <legend>{t("emu.title")}</legend>
      <div className="emu-line">
        <DescribeContext.Provider value={described}>
          <Choice value={at >= 0 ? String(at) : ""} aria-label={t("emu.title")} title={found.length ? t("emu.found_note") : undefined}
            onChange={(e) => { if (e.target.value !== "") set(pickOf(found[Number(e.target.value)])); }}>
            {at < 0 && <option value="">{found.length ? fill(t("emu.pick"), { current: label }) : label}</option>}
            {found.map((d, j) => <option key={j} value={j}>{deviceName(t, d)}</option>)}
          </Choice>
        </DescribeContext.Provider>
        <button type="button" disabled={scan.state === "scanning" || running} onClick={find}>
          {t(scan.state === "scanning" ? "emu.scanning" : scan.state === "none" ? "emu.scan" : "emu.rescan")}
        </button>
      </div>
      {none && <p className="muted" id={outcomeId} title={t("emu.none_found_note")}>{t("emu.none_found")}</p>}
      {none && <span id={nextId} hidden>{t("emu.none_found_note")}</span>}
      {scan.state === "failed" && <p className="caution" id={outcomeId}>{fill(t("emu.scan_failed"), { error: scan.error })}</p>}
      {/* folded, its title turns red when a field inside has a problem; a problem's jump opens it (ui.tsx focusPath) */}
      <details className={"emu-manual" + (bad("emulator") ? " bad" : "")} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary title={t("emu.manual_note")}>{t("emu.manual")}</summary>
        <div className="emu-fields">
          <KeyField path="emulator/address" label={t("emu.address")} help={t("emu.address_note")}>
            <Input type="text" value={current.address ?? ""} spellCheck={false} onChange={(e) => set({ address: text(e.target.value) })} />
          </KeyField>
          <KeyField path="emulator/mumu_index" label={t("emu.mumu_index")} help={t("emu.mumu_index_note")}>
            <Input type="number" min={0} step={1} value={current.mumu_index ?? ""}
              onChange={(e) => set({ mumu_index: e.target.value === "" ? null : Math.max(0, Math.trunc(Number(e.target.value))) })} />
          </KeyField>
          <KeyField path="emulator/mumu_manager" label={t("emu.mumu_manager")}>
            <Input type="text" className="wide" value={current.mumu_manager ?? ""} spellCheck={false}
              onChange={(e) => set({ mumu_manager: text(e.target.value) })} />
          </KeyField>
        </div>
      </details>
    </fieldset>
  );
}
