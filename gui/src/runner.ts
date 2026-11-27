// The run as the window shows it (#815, spec #811 「執行器」): the messages the backend relays from the runner
// (src-tauri/src/runner.rs Message, runner/protocol.py events) folded into one view: the phase, each posted task's state, the
// connection, the live log (the last LOG_LINES lines) and how the run ended.
import { createContext, useContext } from "react";
import type { Settings } from "./model";
import type { ReasonCode, ReasonParams } from "./reasons";

/** The lines of the live log the window keeps (lib.rs LOG_KEEP keeps as many for a page that attaches later). */
export const LOG_LINES = 2000;

// The values each field of the runner's events takes (runner/protocol.py; runner.test.tsx holds them to the shared cases).
export const TASK_STATES = ["pending", "running", "succeeded", "failed", "stopped", "cancelled"] as const;
export type TaskState = (typeof TASK_STATES)[number];
export const SOURCES = ["runner", "agent", "console"] as const;
export type Source = (typeof SOURCES)[number];
export const RESULTS = ["succeeded", "failed", "stopped"] as const;
export type RunResult = (typeof RESULTS)[number];
export const LINK_STATES = ["launching", "waiting", "connecting", "connected"] as const;
export type LinkState = (typeof LINK_STATES)[number];
export const RESOURCE_STATES = ["loading", "loaded"] as const;
export type ResourceState = (typeof RESOURCE_STATES)[number];

/** A device a scan found (runner.rs Device): `mumu` null for one that is not MuMu. */
export interface Device {
  name: string;
  address: string;
  adb_path: string;
  mumu: { index: number; manager: string; path: string } | null;
}

/** A PC window a scan found (runner.rs PcWindow, #939): its title, its client area's size, whether it is minimized. */
export interface PcWindow { title: string; width: number; height: number; minimized: boolean }

/** An event of the runner, as the backend relays it under `type: "event"` (an error event has a field named kind). */
export type RunnerEvent =
  | { event: "ready"; pid: number }
  | { event: "log"; t: string; source: Source; line: string }
  | { event: "devices"; devices: Device[]; windows?: PcWindow[] }
  | { event: "connection"; state: LinkState; address: string }
  | { event: "resource"; state: ResourceState }
  | { event: "task"; index: number; entry: string; state: TaskState; reason?: string | null; reason_code?: string;
      reason_params?: ReasonParams }
  | { event: "error"; kind: string; message: string; code?: number; tail?: string[] }
  | { event: "end"; result: RunResult };

/** What the backend sends of a run (runner.rs Message), in order; `exit` comes last. */
export type Message =
  | ({ type: "event" } & RunnerEvent)
  | { type: "invalid"; line: string; error: string }
  | { type: "output"; line: string }
  | { type: "stopping" }
  | { type: "killed"; reason: string }
  | { type: "exit"; code: number | null; ended: boolean; tail: string[] };

/** What the page itself adds: a start it asked for (the entries it posts, and the whole list it starts from), a start the
 * backend refused, a line of its own for the live log (what came of a scheduled run's start, #816), the settings' task
 * list each time it changes (App: the run's `list`), with whether a run with none may take it (`adopt`: the backend said
 * the run a page took up is under way), and the backend's word that the page it loaded took up a run under way, which is
 * running from then on, before the run's messages come (#876). */
export type Action = Message | { type: "begin"; entries: string[]; list?: Settings["tasks"] } | { type: "refused"; error: string }
  | { type: "note"; line: string } | { type: "list"; list: Settings["tasks"]; adopt: boolean } | { type: "attached" };

/** A line of the live log: `raw` is a line the window got outside the runner's log (its stderr, a line that is not the
 * protocol), `window` one of the window's own. `n` numbers the lines of a run. */
export interface LogLine { n: number; t: string; source: Source | "raw" | "window"; line: string }

/** idle: nothing ran since the window opened; running: the runner runs; stopping: the stop went; ended: it exited. */
export type Phase = "idle" | "running" | "stopping" | "ended";

export interface RunView {
  phase: Phase;
  /** each task's state, with its reason and the reason's code (#881) when there is one */
  tasks: { entry: string; state: TaskState; reason?: string | null; code?: ReasonCode }[];
  log: LogLine[];
  link?: { state: LinkState; address: string };
  resource?: ResourceState;
  result?: RunResult;
  /** the runner's process ended: `ended` false when it ended before its end event (it crashed or was ended) */
  exit?: { code: number | null; ended: boolean; tail: string[] };
  /** why the window ended the runner's tree */
  killed?: string;
  /** why the backend did not start the run */
  refused?: string;
  /** The tasks the bot started, as its own lines say (`[maalc] task <id> started`, agent/actions.py TaskStart), each with
   * the last stop line it logged since (`[maalc] stop: <reason>`, agent/actions.py stop): a failed task's reason when the
   * runner sends none (it sends one only when the bot stopped the whole list, runner/session.py finish), with the code the
   * bot logged after that line (`[maalc] stop code: <code> <params>`, agent/reasons.py code_line, #881). */
  bot?: { entry: string; stop?: string; code?: ReasonCode }[];
  /** The task list the run's states are written on (the Run tab's rows), its unticked entries too: the one the window
   * started the run from (Start, a scheduled start), or, for a run under way a page loaded again took up, the settings' list
   * as the page first saw it with the run (none for an ended one). Dropped for good once the settings' list is another
   * (`unlisted`): the list was edited, and its rows no longer read with the run. */
  list?: Settings["tasks"];
  unlisted?: boolean;
}

export const IDLE: RunView = { phase: "idle", tasks: [], log: [] };

/** The bot's lines that tell the reason a task failed (agent/actions.py TaskStart and stop). */
const BOT_START = /^\[maalc\] task (\S+) started$/;
const STOP_LINE = "[maalc] stop: ";
const CODE_LINE = "[maalc] stop code: ";

/** Whether two task lists are one: the same entries, ticked the same, in one order. */
export const sameList = (a: Settings["tasks"], b: Settings["tasks"]) =>
  a.length === b.length && a.every((x, j) => x.id === b[j].id && x.enabled === b[j].enabled);

/** Whether the run has its tasks and still waits for a list (App hands it the settings' list again when this changes). */
export const wantsList = (v: RunView) => v.tasks.length > 0 && !v.list && !v.unlisted;

/** The run's list after the settings' list changed to `list`: a run with none takes it when `adopt` says it may (a run under
 * way a page took up: the lock keeps the list then as the run read it), the same list keeps it, and another drops it for
 * good. Nothing before a run's tasks are known; an ended run a page took up takes none, as the list may have changed since
 * it ran. */
function listed(v: RunView, list: Settings["tasks"], adopt: boolean): RunView {
  if (!v.tasks.length || v.unlisted) return v;
  if (!v.list) return adopt && isRunning(v) ? { ...v, list } : v;
  return sameList(v.list, list) ? v : { ...v, list: undefined, unlisted: true };
}

/** HH:MM:SS.mmm now, the runner's log time (runner/runlog.py clock). */
const now = (d = new Date()) => d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");

const addLine = (v: RunView, source: LogLine["source"], line: string, t = now()): RunView => {
  const n = (v.log.length ? v.log[v.log.length - 1].n : 0) + 1;
  const log = v.log.length >= LOG_LINES ? v.log.slice(v.log.length - LOG_LINES + 1) : v.log.slice();
  log.push({ n, t, source, line });
  return { ...v, log };
};

/** The view after one more action. A message with no start before it (a page that attached to a run under way) starts the
 * view as running. */
export function reduce(v: RunView, a: Action): RunView {
  if (a.type === "begin") {
    return { phase: "running", tasks: a.entries.map((entry) => ({ entry, state: "pending" })), log: [], ...(a.list ? { list: a.list } : {}) };
  }
  if (a.type === "refused") return { ...IDLE, refused: a.error };
  if (a.type === "note") return addLine(v, "window", a.line); // the run, or no run, as it was
  if (a.type === "list") return listed(v, a.list, a.adopt);
  if (a.type === "attached") return v.phase === "idle" ? { ...IDLE, phase: "running" } : v; // its messages may be in already
  if (v.phase === "idle" || (v.phase === "ended" && a.type !== "exit")) v = { ...IDLE, phase: "running" };
  switch (a.type) {
    case "invalid": return addLine(v, "raw", a.line);
    case "output": return addLine(v, "raw", a.line);
    case "stopping": return v.phase === "running" ? { ...v, phase: "stopping" } : v;
    case "killed": return { ...v, killed: a.reason };
    case "exit": return { ...v, phase: "ended", exit: { code: a.code, ended: a.ended, tail: a.tail }, tasks: a.ended ? v.tasks : unfinished(v) };
    case "event": return event(v, a);
    default: return v; // a message this page does not know (a newer backend's)
  }
}

/** The tasks of a run that ended before its end event (the runner crashed, or the window ended its tree): no state of the
 * runner's comes for them any more, so the window ends them as the runner would have: the running task failed (stopped
 * when a stop was under way) and the rest cancelled. The run is a failure (spec #811 「執行器」). */
const unfinished = (v: RunView) => v.tasks.map((x) =>
  x.state === "running" ? { ...x, state: v.phase === "stopping" ? "stopped" as const : "failed" as const }
    : x.state === "pending" ? { ...x, state: "cancelled" as const } : x);

/** A code line's code and params, its prefix off (agent/reasons.py code_line); undefined for one that does not read. */
function codeOf(text: string): ReasonCode | undefined {
  const space = text.indexOf(" ");
  const code = space < 0 ? text : text.slice(0, space);
  let params: unknown = {};
  try {
    if (space >= 0) params = JSON.parse(text.slice(space + 1));
  } catch {
    return undefined;
  }
  const ok = typeof params === "object" && params !== null && !Array.isArray(params)
    && Object.values(params).every((x) => typeof x === "string" || Number.isInteger(x));
  return code && ok ? { code, params: params as ReasonParams } : undefined;
}

/** The bot's tasks after one more line of its own: a start adds one, a stop line goes to the last one (its code goes, a
 * stop line with none leaves it uncoded), a code line to that stop line. */
function botLine(bot: RunView["bot"] = [], line: string): RunView["bot"] {
  const started = BOT_START.exec(line);
  if (started) return [...bot, { entry: started[1] }];
  if (!bot.length) return bot;
  const last = bot[bot.length - 1];
  if (line.startsWith(STOP_LINE)) return [...bot.slice(0, -1), { entry: last.entry, stop: line.slice(STOP_LINE.length) }];
  if (line.startsWith(CODE_LINE) && last.stop !== undefined) {
    return [...bot.slice(0, -1), { ...last, code: codeOf(line.slice(CODE_LINE.length)) }];
  }
  return bot;
}

/** Why task `index` failed when the runner sends no reason: the last stop line the bot logged in it. The bot's nth start of a
 * task is the run's nth entry of it, so the line stays with its task when the bot started the next one before the runner,
 * which looks every half second, ended this one, and the task before's line never becomes this one's. */
function stopLineOf(v: RunView, index: number, entry: string) {
  const nth = v.tasks.slice(0, index).filter((x) => x.entry === entry).length;
  return v.bot?.filter((x) => x.entry === entry)[nth];
}

function event(v: RunView, e: RunnerEvent): RunView {
  switch (e.event) {
    case "log": {
      const next = addLine(v, e.source, e.line, e.t);
      return e.source === "agent" ? { ...next, bot: botLine(v.bot, e.line) } : next;
    }
    case "task": {
      const tasks = v.tasks.slice();
      while (tasks.length <= e.index) tasks.push({ entry: e.entry, state: "pending" });
      // a cancelled task never ran in the bot, and a stopped one was the user's stop: only a failed one takes the bot's line
      const bot = e.reason == null && e.state === "failed" ? stopLineOf(v, e.index, e.entry) : undefined;
      const reason = e.reason ?? bot?.stop;
      const code = e.reason ? (e.reason_code ? { code: e.reason_code, params: e.reason_params ?? {} } : undefined) : bot?.code;
      tasks[e.index] = { entry: e.entry, state: e.state, reason, ...(code ? { code } : {}) };
      return { ...v, tasks };
    }
    case "connection": return { ...v, link: { state: e.state, address: e.address } };
    case "resource": return { ...v, resource: e.state };
    case "end": return { ...v, result: e.result };
    default: return v; // ready; devices (a scan's); error, which the runner logs too
  }
}

const LOOPBACK = ["127.0.0.1", "localhost"];

/** Whether two adb addresses name one device, as the runner picks it (runner/devices.py same_address): the same text, or
 * the same port on the loopback host. */
export function sameAddress(a: string, b: string): boolean {
  if (a === b) return true;
  const split = (x: string) => { const i = x.lastIndexOf(":"); return i < 0 ? ["", ""] : [x.slice(0, i), x.slice(i + 1)]; };
  const [ha, pa] = split(a), [hb, pb] = split(b);
  return pa !== "" && pa === pb && LOOPBACK.includes(ha) && LOOPBACK.includes(hb);
}

/** Whether the run ended because the runner crashed: its process ended before its end event, and the window did not end
 * it (after a stop that did not stop, `killed` says why). The run failed (spec #811 「執行器」). */
export const crashed = (v: RunView) => !!v.exit && !v.exit.ended && !v.killed;

/** Whether a run holds the settings it reads: the task list, the task options, the global options and the emulator can be
 * neither changed nor saved until it ends (#815). */
export const isRunning = (v: RunView) => v.phase === "running" || v.phase === "stopping";

/** The runner as the Run tab reaches it (App holds it): the view, Start (which saves first) and Stop. `blocked` says why
 * Start is off, null when it can start. */
export interface Runner {
  view: RunView;
  start: () => void;
  stop: () => void;
  blocked: null | "problems" | "no_task" | "saving";
  /** a scheduled run started (#816): the Run tab brings its log and Stop into view, then calls revealed */
  reveal?: boolean;
  revealed?: () => void;
  /** whether the window knows yet if a run is under way or starting as it opens (#876): false until the backend answered
   * whether the page took up a run (a page loaded again) and handed out the scheduled starts this window opened for, the
   * first of them begun. The Run tab scans for devices as it opens, unless one is. Absent: known (a page with no backend). */
  settled?: boolean;
}

export const RunnerContext = createContext<Runner>({ view: IDLE, start: () => {}, stop: () => {}, blocked: null });
export const useRunner = () => useContext(RunnerContext);
