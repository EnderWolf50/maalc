// The scheduled runs (#816, spec #811 「定時執行」, spec 04 section 14): the settings' schedules, each one Windows Task
// Scheduler task that starts `maalc-gui.exe --run <id>` (src-tauri/src/schedule.rs), and what the window says of them: how
// the last sync with the Task Scheduler went and what came of the last scheduled run's start.
import { createContext, useContext } from "react";
import type { Synced } from "./api";
import { schema, type Settings } from "./model";

export type Schedule = Settings["schedules"][number];

/** The weekdays, Monday first (agent/settings.schema.json schedules.days): a schedule keeps its days in this order. */
export const DAYS: string[] = schema.properties.schedules.items.properties.days.items.enum;
/** A new schedule's time: just after the game's daily reset (05:00 UTC+8, GLOSSARY 每日重置), when the day's tasks are there
 * to run. */
export const NEW_TIME = "05:10";

/** A new schedule: every day at NEW_TIME, waking the PC, its id the first of s1, s2, … that `list` does not use. */
export function newSchedule(list: Schedule[]): Schedule {
  const taken = new Set(list.map((x) => x.id));
  let n = 1;
  while (taken.has(`s${n}`)) n++;
  return { id: `s${n}`, days: [...DAYS], time: NEW_TIME, wake: true };
}

/** What came of a scheduled run's start: it started; skipped, a run under way, or an update being applied or cut short
 * (cache/update/apply.json says `applying`, #817: the folder may hold half the new version); not run, its schedule is not in
 * the settings, the settings did not load, or the start was refused (why: a runner.blocked_* reason, the save, the backend's
 * error); the run it started ended, and the window it opened stayed open over unsaved changes or after the runner crashed
 * (exit code `code`), or closes. */
export type Outcome =
  | { kind: "started" } | { kind: "busy" } | { kind: "updating" } | { kind: "unknown" } | { kind: "unread" }
  | { kind: "refused"; why: "problems" | "no_task" | "save" | { error: string } }
  | { kind: "kept_open" } | { kind: "crashed"; code: number | null } | { kind: "closed" };

/** The line logs/schedule.log and the live log get: English, as the runner's own lines are. */
export function logLine(id: string, o: Outcome): string {
  const why = o.kind === "refused"
    ? typeof o.why === "object" ? o.why.error
      : { problems: "the settings have problems", no_task: "no task is ticked", save: "the save was refused" }[o.why]
    : "";
  const said = {
    started: "started the task list", busy: "skipped: a run is under way",
    updating: "skipped: an update is being applied or did not finish", unknown: `not run: the settings have no schedule ${id}`,
    unread: "not run: the settings did not load", refused: `not run: ${why}`,
    kept_open: "the run ended; the window stays open: it has unsaved changes",
    crashed: `the runner ended unexpectedly (exit code ${o.kind === "crashed" ? o.code ?? "none" : ""}); the window stays open`,
    closed: "the run ended; the window closes",
  }[o.kind];
  return `[schedule] ${id}: ${said}`;
}

/** YYYY-MM-DD HH:MM:SS, local time, as logs/schedule.log dates a line. */
export const stamp = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${d.toTimeString().slice(0, 8)}`;

/** What the schedules' section shows besides the settings: the last sync (what it did, or why it failed; null before the first),
 * the schedules as the file holds them (an edit not saved yet is not in the Task Scheduler), and the last scheduled run's start
 * the window took. */
export interface ScheduleView {
  synced: null | { done: Synced } | { error: string };
  saved: string;
  last: null | { id: string; at: string; outcome: Outcome };
}

export const ScheduleContext = createContext<ScheduleView>({ synced: null, saved: "[]", last: null });
export const useSchedules = () => useContext(ScheduleContext);
