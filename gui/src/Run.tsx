// The Run tab (#814, #815, #816, #875, spec #811 「設定視窗」, spec #871 「版面（L1 B）」, spec 04 sections 5, 12 and 14), in two
// columns with no titles over them, whose first frames start on one line. Left, the task list (ticks, drag or ↑↓: the run
// order; a task listed again, or an extra entry removed, #811) beside the picked task's options, then the global options
// (folded) and the scheduled runs (Schedules.tsx). Right, held in view as the page scrolls, the run console: Start, Stop and
// the run's status, the emulator with the device scan, and the live log, in that order idle and running. A narrow window
// (NARROW) puts the console's Start line on top and its emulator and log under the options. Each control writes the settings
// key the runner or the agent reads at a task's start, and shows that key after its label while the pointer is over the field
// or the field draws a focus ring: the agent's stop lines name an option by it ("run/start_team: team 'x' was deleted ...").
// A team pick lists the settings' teams as they are now. During a run the settings it reads are locked (LockContext): a task
// still shows its options when clicked.
import {
  memo, useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode,
} from "react";
import { fill, type Key } from "./i18n";
import { schema, type LuxOptions, type Settings } from "./model";
import { LOG_LINES, crashed, isRunning, sameAddress, useRunner, type Device, type LogLine, type RunView } from "./runner";
import * as api from "./api";
import { SchedulesSection } from "./Schedules";
import {
  Choice, DescribeContext, Field, Input, LockContext, Mark, Num, ReorderList, Select, ToggleNum, translate, useEditor, usePick,
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
 * and the read-back's notice go by. */
const TASK_ROOTS: Record<string, string[]> = {
  MirrorDungeon: Object.keys(RUN).filter((k) => !isGlobal(k)).map((k) => `run/${k}`),
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
/** The controls inside take settings key `path` as their description, so a screen reader reads the field's label as its name and
 * the key after it, whether or not the key shows. Every field of the tab that shows a key is one of the three below. */
const DescribedByKey = ({ path, children }: { path: string; children: ReactNode }) =>
  <DescribeContext.Provider value={keyId(path)}>{children}</DescribeContext.Provider>;
/** A field of the tab: its label and settings key, the control, a note. */
const KeyField = ({ path, label, note, children }: { path: string; label?: string; note?: string; children: ReactNode }) =>
  <DescribedByKey path={path}><Field label={<KeyLabel path={path} text={label} />} path={path} note={note}>{children}</Field></DescribedByKey>;
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
/** A switch with its number (ToggleNum), its key after the switch's label. */
const KeyToggleNum = ({ path, ...rest }: Omit<ComponentProps<typeof ToggleNum>, "label">) =>
  <DescribedByKey path={path}><ToggleNum label={<KeyLabel path={path} />} path={path} {...rest} /></DescribedByKey>;

/** How many entries of entry j's task come before it (a task may be listed more than once, #811). */
const nthOf = (tasks: { id: string }[], j: number) => tasks.slice(0, j).filter((x) => x.id === tasks[j].id).length;
/** An entry's pick key: its task's id for the task's first entry, `<id>#<n>` for the one after n others, so the pick stays on
 * its entry when the list is reordered; a pick by id alone is the task's first entry. */
export const entryKey = (tasks: { id: string }[], j: number) => {
  const n = nthOf(tasks, j);
  return n ? `${tasks[j].id}#${n}` : tasks[j].id;
};

export function RunTab() {
  const { s, update, t, bad } = useEditor();
  // each entry a row of its own: `nth` is its place among its task's entries (from 0), `of` how many the task has
  const rows = s.tasks.map((x, j) => ({
    ...x, key: entryKey(s.tasks, j), nth: nthOf(s.tasks, j), of: s.tasks.filter((y) => y.id === x.id).length,
  }));
  const [i, setSel] = usePick("tasks", rows.map((x) => ({ id: x.key })));
  const picked = rows[i];
  const { view, reveal, revealed } = useRunner();
  const locked = isRunning(view);
  const narrow = useNarrow();
  // MaaFramework's own output in the log: held here, so the log keeps it when the window crosses NARROW and moves the log
  const raw = useState(false);
  // a scheduled run's window shows its log and Stop (spec #811 「定時執行」): the console, held in view beside the list; a
  // narrow window's log, under the list and the options (Stop stays on the line held at the page's top)
  const shown = useRef<HTMLElement | null>(null);
  const keep = useCallback((el: HTMLElement | null) => { shown.current = el; }, []);
  useEffect(() => {
    if (!reveal) return;
    shown.current?.scrollIntoView?.({ block: "start" });
    revealed?.();
  }, [reveal]);
  // the picked task once more, unticked, right after the picked entry, and picked: a new entry runs only once ticked
  const again = () => {
    const tasks = [...s.tasks.slice(0, i + 1), { id: picked.id, enabled: false }, ...s.tasks.slice(i + 1)];
    update((d) => { d.tasks = tasks; });
    setSel(entryKey(tasks, i + 1));
  };
  // a task's last entry stays (the button is only there while it has another): every task is listed, to be ticked
  const remove = () => {
    update((d) => { d.tasks.splice(i, 1); });
    setSel(picked.id);
  };
  return (
    <div className="run-page"><LockContext.Provider value={locked}>
      <div className={"run-grid" + (narrow ? " narrow" : "")}>
        {/* The run console first in the page's order, so the first Tab reaches Start. Wide, the grid draws it in the right
            column, in one order idle and running: Start, the emulator, the log, which takes the column's remaining height.
            Narrow, Start, Stop and the status are one line held at the page's top, the emulator and the log under the options. */}
        {narrow ? <RunControls /> : (
          <div className="run-console" ref={keep}>
            <RunControls />
            <EmulatorFields />
            <RunLog raw={raw} />
          </div>
        )}
        <div className="run-main">
          {/* no titles over the columns: the list, the options and the console start on one line */}
          <div className="split">
            <aside className="task-list" data-path="tasks" aria-label={t("tasks.title")}>
              {/* a moved list's rows still carry the keys of before the move: the pick's key is counted in the list after it */}
              <ReorderList items={rows} keyOf={(x) => x.key} selected={i} onSelect={(j, list) => setSel(entryKey(list, j))}
                badAt={(j) => bad(`tasks/${j}`) || (TASK_ROOTS[rows[j].id] ?? []).some(bad)}
                onChange={(moved) => update((d) => { d.tasks = moved.map(({ id, enabled }) => ({ id, enabled })); })}
                render={(x, j) => (
                  <span className="task-row">
                    {/* the tick's own hit area, larger than the bare box; a click there ticks and leaves the picked task as it is */}
                    <label className="tick" onClick={(e) => e.stopPropagation()}>
                      <Input type="checkbox" checked={x.enabled}
                        aria-label={fill(t(x.of > 1 ? "tasks.tick_nth" : "tasks.tick"), { name: taskName(t, x.id), n: x.nth + 1 })}
                        onChange={(e) => update((d) => { d.tasks[j].enabled = e.target.checked; })} />
                    </label>
                    <span className={x.enabled ? "" : "muted"}>{taskName(t, x.id)}</span>
                  </span>
                )} />
              {picked && (
                <div className="task-actions">
                  <button type="button" disabled={locked} onClick={again}>
                    <span aria-hidden>+ </span>{fill(t("tasks.again"), { name: taskName(t, picked.id) })}
                  </button>
                  {picked.of > 1 && <button type="button" className="danger" disabled={locked} onClick={remove}>{t("tasks.remove")}</button>}
                </div>
              )}
              {/* under the list, not over the options: the options' frame stays level with the list and the console */}
              {picked && picked.of > 1 && <p className="muted">{fill(t("tasks.entries"), { n: picked.of })}</p>}
              {/* under the list, not over the page: a run moves nothing in the console or the columns' tops */}
              {locked && <p className="run-locked" role="status">{t("runner.locked")}</p>}
            </aside>
            <section className="task-options">{picked && <TaskOptions id={picked.id} />}</section>
          </div>
          {narrow && <><EmulatorFields /><RunLog folded raw={raw} boxRef={keep} /></>}
          <GlobalOptions />
          {/* the run reads no schedule: they stay open to edits during a run (#816) */}
          <LockContext.Provider value={false}><SchedulesSection /></LockContext.Provider>
        </div>
      </div>
    </LockContext.Provider></div>
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
 * when the window saw it start, to now or to its end; it ticks each second while the run runs. "" while idle. */
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
  const from = first ?? seen;
  return view.phase === "idle" || from === null ? "" : clock((ended ?? Date.now()) - from);
}

/** The bot's English names of its tasks, as its lines write them (agent/lux_actions.py LUX), by task id. */
const BOT_NAMES: Record<string, string> = { "EXP Luxcavation": "ExpLuxcavation", "Thread Luxcavation": "ThreadLuxcavation" };
/** A task a line of the runner or the bot names, by its id or the bot's English name, longest first. */
const NAMED = new RegExp(`\\b(${[...Object.keys(BOT_NAMES), ...TASKS].sort((a, b) => b.length - a.length).join("|")})\\b`, "g");
/** A line with each task it names written as the list names it: 「[run] 紐本 status=failed」 for "[run] ThreadLuxcavation
 * status=failed". The runner's log file keeps the line as it came. */
const namesInList = (t: (k: Key) => string, text: string) => text.replace(NAMED, (m) => taskName(t, BOT_NAMES[m] ?? m));
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
 * the line. */
function RunControls() {
  const { t } = useEditor();
  const { view, start, stop, blocked } = useRunner();
  const running = isRunning(view);
  const took = useTook(view);
  const saving = blocked === "saving" && !running;
  return (
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
      {blocked && !saving && !running && <p className="caution">{t(`runner.blocked_${blocked}`)}</p>}
      {view.refused && <p className="caution" role="alert">{fill(t("runner.refused"), { error: view.refused })}</p>}
      {view.killed && <p className="caution" role="alert">{fill(t("runner.killed"), { reason: view.killed })}</p>}
    </div>
  );
}

/** Each posted task's state, while a run shows (#877 writes them on the task list's rows instead): in the log's frame, above
 * the log, so nothing in the console moves as a run starts. */
function RunTasks({ view }: { view: RunView }) {
  const { t } = useEditor();
  if (!view.tasks.length) return null;
  return (
    <div className="run-tasks">
      <h3>{t("runner.tasks")}</h3>
      <ol aria-label={t("runner.tasks")}>
        {view.tasks.map((x, j) => (
          <li key={j} data-state={x.state}>
            <span>{taskName(t, x.entry)}</span>
            <span className="state">{t(`runner.state.${x.state}`)}</span>
            {x.reason && <small>{x.reason}</small>}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** The live log (the last LOG_LINES lines, MaaFramework's own output hidden unless `raw` asks for it), how a run that crashed
 * ended and the run's tasks. In the console's column it takes the column's remaining height, empty but for one faint line
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
  // on the title's line, at its right: a click on it ticks it, and folds no panel
  const rawSwitch = (
    <label className="check" title={t("runner.console_note")}>
      <input type="checkbox" checked={showConsole} onChange={(e) => setShowConsole(e.target.checked)} />{t("runner.console")}
    </label>
  );
  const body = (<>
    {crashed(view) && (
      <div className="crash" role="alert">
        <p>{fill(t("runner.crash"), { code: view.exit!.code ?? "—" })}</p>
        <pre>{view.exit!.tail.join("\n")}</pre>
      </div>
    )}
    <RunTasks view={view} />
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
      <summary><span className="lg-title" id={title} title={note}>{t("runner.log")}</span>{rawSwitch}</summary>
      {body}
    </details>
  );
  return (
    <fieldset className="runner run-log-box" ref={boxRef} aria-labelledby={title}>
      <legend><span className="lg-title" id={title} title={note}>{t("runner.log")}</span>{rawSwitch}</legend>
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
  const body = id === "ExpLuxcavation" ? <LuxFields task="exp" /> : id === "ThreadLuxcavation" ? <LuxFields task="thread" />
    : id === "ChargeEnkephalin" ? <ChargeFields /> : <p className="muted">{t("tasks.none")}</p>;
  return (
    <fieldset className="task-opts">
      <legend>{taskName(t, id)}</legend>
      {body}
    </fieldset>
  );
}

/** The Mirror Dungeon task's options (spec 04 section 5) in three groups by what they decide: the run itself, the weekly
 * bonuses, what happens when something fails. */
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
          <KeyField path="run/start_team" note={t("run.start_team_note")}>
            <TeamPick value={run.start_team} none={t("run.start_team_queue")} markOff onChange={(v) => set({ start_team: v })} />
          </KeyField>
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

/** A team pick (the start team, a Luxcavation task's team): `none` first (null), then the settings' teams as they are now,
 * by name and slot, a disabled one marked when that stops the task (`markOff`). A team deleted since stays the value, shown
 * as deleted with why the task will stop, until another is picked: the agent stops the task at its start over it. */
function TeamPick({ value, none, markOff = false, onChange }: {
  value: string | null; none: string; markOff?: boolean; onChange: (v: string | null) => void;
}) {
  const { s, t } = useEditor();
  const ids = s.teams.map((x) => x.id);
  const team = s.teams.find((x) => x.id === value);
  const gone = value !== null && !team;
  const label = (id: string) => {
    if (id === "") return none;
    const x = s.teams.find((y) => y.id === id);
    if (!x) return fill(t("teamPick.gone"), { id });
    return fill(t(markOff && !x.enabled ? "teamPick.off" : "teamPick"), { name: x.name || "—", slot: x.game_team });
  };
  const warn = gone ? "teamPick.gone_note" : markOff && team && !team.enabled ? "teamPick.off_note" : null;
  return (<>
    <Select value={value ?? ""} options={["", ...ids, ...(gone ? [value] : [])]} label={label} onChange={(v) => onChange(v || null)} />
    {warn && <small className="caution">{t(warn)}</small>}
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

/** A device of a scan as its pick list names it: a MuMu one by its instance. */
const deviceName = (t: (k: Key) => string, d: Device) =>
  d.mumu ? fill(t("emu.device_mumu"), { index: d.mumu.index, address: d.address }) : fill(t("emu.device"), { name: d.name, address: d.address });

/** What a pick of a scanned device writes: its address, and its MuMu instance and MuMuManager.exe (none for another). */
const pickOf = (d: Device): Settings["emulator"] => ({ address: d.address, mumu_index: d.mumu?.index ?? null, mumu_manager: d.mumu?.manager ?? null });

/** The emulator the runner connects to (spec 04 section 14): its adb address, its MuMu instance and MuMuManager.exe; an empty
 * field is none (null). The scan lists the emulators that run, MuMu first; a pick fills in all three, saved with the rest. */
function EmulatorFields() {
  const { s, update, t } = useEditor();
  const set = (patch: Partial<Settings["emulator"]>) => update((d) => { Object.assign(d.emulator, patch); });
  const text = (v: string) => (v.trim() === "" ? null : v);
  const running = isRunning(useRunner().view);
  // the last scan: its devices, or why it found none; null before the first
  const [scan, setScan] = useState<Scan>({ state: "none" });
  const find = () => {
    setScan({ state: "scanning" });
    api.scanDevices().then((devices) => setScan({ state: "found", devices }), (e) => setScan({ state: "failed", error: String(e) }));
  };
  const found = scan.state === "found" ? scan.devices : null;
  // The list shows a device only when the fields already hold all that a pick of it writes, and "pick one" otherwise. A select
  // fires no change for the option it shows, so a list that showed the device at the address alone (after MXU's read-back,
  // which keeps no instance or MuMuManager) could not fill the other two (#833).
  const current = s.emulator;
  const at = found ? found.findIndex((d) => {
    const writes = pickOf(d);
    return current.address !== null && sameAddress(d.address, current.address)
      && writes.mumu_index === current.mumu_index && writes.mumu_manager === current.mumu_manager;
  }) : -1;
  const pick = (d: Device) => set(pickOf(d));
  return (
    <fieldset className="emulator" data-path="emulator">
      <legend>{t("emu.title")}</legend>
      <div className="row scan">
        <button type="button" disabled={scan.state === "scanning" || running} onClick={find}>
          {scan.state === "scanning" ? t("emu.scanning") : t("emu.scan")}
        </button>
        {found && found.length > 0 && (
          <label className="field">
            <span>{t("emu.found")}</span>
            <Choice value={at >= 0 ? String(at) : ""} onChange={(e) => { if (e.target.value !== "") pick(found[Number(e.target.value)]); }}>
              {at < 0 && <option value="">{t("emu.pick")}</option>}
              {found.map((d, j) => <option key={j} value={j}>{deviceName(t, d)}</option>)}
            </Choice>
            <small>{t("emu.found_note")}</small>
          </label>
        )}
        {found && found.length === 0 && <p className="muted">{t("emu.none_found")}</p>}
        {scan.state === "failed" && <p className="caution">{fill(t("emu.scan_failed"), { error: scan.error })}</p>}
      </div>
      <div className="row">
        <KeyField path="emulator/address" label={t("emu.address")}>
          <Input type="text" value={s.emulator.address ?? ""} spellCheck={false} onChange={(e) => set({ address: text(e.target.value) })} />
        </KeyField>
        <KeyField path="emulator/mumu_index" label={t("emu.mumu_index")}>
          <Input type="number" min={0} step={1} value={s.emulator.mumu_index ?? ""}
            onChange={(e) => set({ mumu_index: e.target.value === "" ? null : Math.max(0, Math.trunc(Number(e.target.value))) })} />
        </KeyField>
        <KeyField path="emulator/mumu_manager" label={t("emu.mumu_manager")}>
          <Input type="text" className="wide" value={s.emulator.mumu_manager ?? ""} spellCheck={false}
            onChange={(e) => set({ mumu_manager: text(e.target.value) })} />
        </KeyField>
      </div>
      <p className="muted">{withBreaks(t("emu.note"))}</p>
    </fieldset>
  );
}
