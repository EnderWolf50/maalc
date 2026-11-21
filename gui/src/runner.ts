// The run as the window shows it (#815, spec #811 「執行器」): the messages the backend relays from the runner
// (src-tauri/src/runner.rs Message, runner/protocol.py events) folded into one view: the phase, each posted task's state, the
// connection, the live log (the last LOG_LINES lines) and how the run ended.
import { createContext, useContext } from "react";

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

/** An event of the runner, as the backend relays it under `type: "event"` (an error event has a field named kind). */
export type RunnerEvent =
  | { event: "ready"; pid: number }
  | { event: "log"; t: string; source: Source; line: string }
  | { event: "devices"; devices: Device[] }
  | { event: "connection"; state: LinkState; address: string }
  | { event: "resource"; state: ResourceState }
  | { event: "task"; index: number; entry: string; state: TaskState; reason?: string | null }
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

/** What the page itself adds: a start it asked for (the entries it posts), a start the backend refused, a line of its own
 * for the live log (what came of a scheduled run's start, #816), and the backend's word that the page it loaded took up a
 * run under way, which is running from then on, before the run's messages come (#876). */
export type Action = Message | { type: "begin"; entries: string[] } | { type: "refused"; error: string } | { type: "note"; line: string }
  | { type: "attached" };

/** A line of the live log: `raw` is a line the window got outside the runner's log (its stderr, a line that is not the
 * protocol), `window` one of the window's own. `n` numbers the lines of a run. */
export interface LogLine { n: number; t: string; source: Source | "raw" | "window"; line: string }

/** idle: nothing ran since the window opened; running: the runner runs; stopping: the stop went; ended: it exited. */
export type Phase = "idle" | "running" | "stopping" | "ended";

export interface RunView {
  phase: Phase;
  tasks: { entry: string; state: TaskState; reason?: string | null }[];
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
}

export const IDLE: RunView = { phase: "idle", tasks: [], log: [] };

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
  if (a.type === "begin") return { phase: "running", tasks: a.entries.map((entry) => ({ entry, state: "pending" })), log: [] };
  if (a.type === "refused") return { ...IDLE, refused: a.error };
  if (a.type === "note") return addLine(v, "window", a.line); // the run, or no run, as it was
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

function event(v: RunView, e: RunnerEvent): RunView {
  switch (e.event) {
    case "log": return addLine(v, e.source, e.line, e.t);
    case "task": {
      const tasks = v.tasks.slice();
      while (tasks.length <= e.index) tasks.push({ entry: e.entry, state: "pending" });
      tasks[e.index] = { entry: e.entry, state: e.state, reason: e.reason };
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
   * whether the page took up a run (a page loaded again) and handed out the scheduled starts this window opened for, each
   * begun. The Run tab scans for devices as it opens, unless one is. Absent: known (a page with no backend). */
  settled?: boolean;
}

export const RunnerContext = createContext<Runner>({ view: IDLE, start: () => {}, stop: () => {}, blocked: null });
export const useRunner = () => useContext(RunnerContext);
