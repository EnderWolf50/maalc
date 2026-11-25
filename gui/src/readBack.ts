// The one-time read-back of a v1.0.0 install's run values (#814, spec #811 "設定檔（版本 23）"): when the window migrates a
// settings file of version 21 or 22 to the current one, the task options, the task list's ticks and order and the emulator's address come
// from MXU's config file (config/mxu-maalc.json, its last used instance), else the run options from config/settings.v20.json
// (the file as v1.0.0's window found it, #782), else they stay at the defaults. A version 20 file keeps its own run options
// (#813) and takes only the task list and the address from MXU. MXU's file is read, never written. App.tsx lists the report
// once (ReadBackNotice).
// MXU stores a value by the option's and the case's name (MXU v2.7.1 types/interface.ts OptionValue), so the names below are
// v1.0.0's assets/interface.json options: their cases are the schema's values, a team case's name the team's id
// (v1.0.0 gui/src/teamOptions.ts). MFAAvalonia's file is not read: it stores a case's index (spec #811 範圍外).
import schema from "../../agent/settings.schema.json";
import { TASK_ORDER, newSections, type Settings } from "./model";

/** The files of config/ the read-back reads (lib.rs load_read_back allows only these). */
export const READ_BACK_FILES = { mxu: "mxu-maalc.json", teamOptions: "team_options.json", v20: "settings.v20.json" } as const;
type FileKey = keyof typeof READ_BACK_FILES;
/** Each file's text, null when it is not there, or why it could not be read. */
export type ReadBackFiles = Record<FileKey, string | null | { error: string }>;

/** Where the task options came from: MXU's file, settings.v20.json, the defaults, or (a version 20 file) the file's own. */
export type Source = "mxu" | "v20" | "defaults" | "file";
/** A value that did not come back, which the user sets again in the Run tab: MXU's encrypted webhook; a value that is not
 * one the option takes (its text as the file had it); a team deleted since (its label in the team options file, when it
 * has one); a task MXU lists that maalc does not have; a task MXU lists n times with options that differ between its
 * entries, whose first ticked entry's options count (its entries share them, #811). */
export type Missed =
  | { kind: "webhook" }
  | { kind: "value"; path: string; value: string }
  | { kind: "team"; path: string; id: string; label: string | null }
  | { kind: "task"; name: string }
  | { kind: "differ"; task: string; n: number };
export interface Report {
  /** The version the file had. */
  from: number;
  source: Source;
  /** MXU's instance read (its name) and how many it has; null and 0 when its file was not read. */
  instance: string | null;
  instances: number;
  /** A file that is there but could not be read, and why ("mxu-maalc.json: ..."). */
  problems: string[];
  /** Each task option off its default after the read-back, as its settings path and value, in the Run tab's order. */
  read: { path: string; value: unknown }[];
  /** How many values were read back at their default: the notice says so, as it lists only those off it. */
  same: number;
  /** The files of READ_BACK_FILES that are not there, by name. */
  absent: string[];
  /** The task list as MXU had it, each MXU entry with its own tick; null when it stayed at a new file's (every task once, all ticked). */
  tasks: Settings["tasks"] | null;
  /** MXU's last device address; null when none came back. */
  address: string | null;
  missed: Missed[];
}

type Kind = "select" | "switch" | "int" | "team" | "limit" | "secret";
/** An MXU option: the settings path it fed, how its value reads, and its input's name (an input option). */
type MxuOption = { path: string; kind: Kind; input?: string };
const spec = (path: string, kind: Kind, input?: string): MxuOption => ({ path, kind, input });
const lux = (task: "exp" | "thread", prefix: "Exp" | "Thread"): Record<string, MxuOption> => ({
  [`${prefix}Mode`]: spec(`luxcavation/${task}/mode`, "select"),
  [`${prefix}Count`]: spec(`luxcavation/${task}/count`, "int", "count"),
  [`${prefix}Team`]: spec(`luxcavation/${task}/team`, "team"),
  [`${prefix}Retries`]: spec(`luxcavation/${task}/retries`, "int", "retries"),
  [`${prefix}Consecutive`]: spec(`luxcavation/${task}/consecutive`, "switch"),
});
/** v1.0.0's task options by task, in the Run tab's order (the order the report lists them in). MirrorRunsLimit's No is
 * runs null; its Yes takes MirrorRuns. */
const TASK_OPTIONS: Record<string, Record<string, MxuOption>> = {
  MirrorDungeon: {
    MirrorDifficulty: spec("run/difficulty", "select"),
    MirrorTargetFloor: spec("run/target_floor", "select"),
    MirrorRunsLimit: spec("run/runs", "limit"),
    MirrorRuns: spec("run/runs", "int", "runs"),
    MirrorThemePackRefresh: spec("run/theme_pack_refresh", "select"),
    MirrorWeeklyBonusUse: spec("run/weekly_bonus_use", "select"),
    MirrorWeeklyBonusAmount: spec("run/weekly_bonus_amount", "select"),
    MirrorStopWhenBonusOut: spec("run/stop_when_weekly_bonus_out", "switch"),
    MirrorStarlightUnaffordable: spec("run/starlight_unaffordable", "select"),
    MirrorWipeRetries: spec("run/wipe_retries", "int", "wipe_retries"),
    MirrorAfterRetries: spec("run/after_retries", "select"),
  },
  ExpLuxcavation: lux("exp", "Exp"),
  ThreadLuxcavation: lux("thread", "Thread"),
  ChargeEnkephalin: { ChargeCount: spec("charge_enkephalin/count", "int", "count") },
};
/** v1.0.0's global options: MXU keeps them apart from the tasks (globalOptionValues). The webhook is a password input. */
const GLOBAL_OPTIONS: Record<string, MxuOption> = {
  WebhookUrl: spec("run/webhook_url", "secret", "url"),
  AutoAcceptTerms: spec("run/auto_accept_terms", "switch"),
  AutoDownload: spec("run/auto_download", "switch"),
  KeepDismissedScreens: spec("run/keep_dismissed_screens", "switch"),
};
/** Each task option's settings path once, in the Run tab's order: the report lists the values off their defaults in it. */
export const OPTION_PATHS: string[] = [...new Set([...Object.values(TASK_OPTIONS), GLOBAL_OPTIONS].flatMap((o) => Object.values(o).map((x) => x.path)))];
/** The settings paths that hold a team id (a Luxcavation task's team). */
export const TEAM_PATHS = new Set(Object.values(TASK_OPTIONS).flatMap((o) => Object.values(o)).filter((x) => x.kind === "team").map((x) => x.path));
/** The team options' case 0, which picks no team: 「未選擇」 (v1.0.0 teamOptions.ts NONE). */
const NO_TEAM = "none";
const TASK_IDS: string[] = schema.$defs.task.enum;

type Prop = { enum?: unknown[]; type?: string | string[]; minimum?: number; maximum?: number; minLength?: number };
/** The schema's rule for a task option's settings path. */
function prop(path: string): Prop {
  const [section, key, sub] = path.split("/");
  if (section === "luxcavation") return (schema.$defs.luxcavation.properties as Record<string, Prop>)[sub];
  return ((schema.properties as Record<string, { properties?: Record<string, Prop> }>)[section].properties!)[key];
}
/** Whether a value passes the schema's rule for its key (the simple rules these keys have). */
function fits(p: Prop, v: unknown): boolean {
  if (p.enum) return p.enum.includes(v);
  const typed = [p.type ?? []].flat().some((t) => (t === "null" ? v === null : t === "integer" ? Number.isInteger(v) : typeof v === t));
  if (!typed) return false;
  if (typeof v === "number" && ((p.minimum !== undefined && v < p.minimum) || (p.maximum !== undefined && v > p.maximum))) return false;
  return !(typeof v === "string" && p.minLength !== undefined && v.length < p.minLength);
}

const getAt = (o: unknown, path: string) =>
  path.split("/").reduce<unknown>((node, k) => (node && typeof node === "object" ? (node as Record<string, unknown>)[k] : undefined), o);
function setAt(d: Settings, path: string, v: unknown) {
  const parts = path.split("/");
  const node = parts.slice(0, -1).reduce<Record<string, unknown>>((n, k) => n[k] as Record<string, unknown>, d as unknown as Record<string, unknown>);
  node[parts[parts.length - 1]] = v;
}
const isObject = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const shown = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v) ?? String(v));

/** What reads the values back into the settings: it sets a value, or notes one that did not come back. */
class Reader {
  missed: Missed[] = [];
  /** The paths a value was read back into. */
  read = new Set<string>();
  constructor(readonly data: Settings, readonly labels: Map<string, string>) {}

  put(path: string, v: unknown) {
    setAt(this.data, path, v);
    this.read.add(path);
  }

  /** A team id: none picked, one of the teams, or one deleted since, which is noted and picks none. */
  team(path: string, id: unknown) {
    if (id === null || id === NO_TEAM) return this.put(path, null);
    if (typeof id !== "string") return this.missed.push({ kind: "value", path, value: shown(id) });
    if (this.data.teams.some((t) => t.id === id)) return this.put(path, id);
    this.missed.push({ kind: "team", path, id, label: this.labels.get(id) ?? null });
  }

  /** A value of the settings' own type (settings.v20.json): kept when it passes the schema's rule, noted when not. */
  value(path: string, v: unknown) {
    if (fits(prop(path), v)) this.put(path, v);
    else this.missed.push({ kind: "value", path, value: shown(v) });
  }

  /** An MXU option value (OptionValue): by its kind, a select by its case's name, a switch's true the case Yes. */
  mxu(s: MxuOption, o: unknown) {
    if (!isObject(o)) return;
    const text = isObject(o.values) && typeof o.values[s.input!] === "string" ? (o.values[s.input!] as string) : null;
    // what MXU had, as the user typed or picked it: an input's text, a case's name, a switch's value
    const bad = () => this.missed.push({ kind: "value", path: s.path, value: shown(text ?? o.caseName ?? o.value ?? o.values) });
    if (s.kind === "team") return o.type === "select" ? this.team(s.path, o.caseName) : bad();
    if (s.kind === "select") {
      const v = prop(s.path).enum!.find((x) => String(x) === o.caseName);
      return o.type === "select" && v !== undefined ? this.put(s.path, v) : bad();
    }
    if (s.kind === "switch" || s.kind === "limit") {
      if (o.type !== "switch" || typeof o.value !== "boolean") return bad();
      if (s.kind === "switch") return this.put(s.path, o.value);
      if (!o.value) this.put(s.path, null); // Yes leaves the runs to MirrorRuns
      return;
    }
    if (s.kind === "int") {
      const v = text !== null && /^\d+$/.test(text.trim()) ? Number(text.trim()) : NaN;
      return o.type === "input" && fits(prop(s.path), v) ? this.put(s.path, v) : bad();
    }
    // the webhook: MXU keeps a password input encrypted (encryptedValues); an older one kept it as plain text (values)
    if (text) return this.put(s.path, text);
    const sealed = isObject(o.encryptedValues) ? o.encryptedValues[s.input!] : undefined;
    if (typeof sealed === "string" && sealed !== "") this.missed.push({ kind: "webhook" });
  }
}

type MxuTask = { taskName?: unknown; enabled?: unknown; enabledByController?: unknown; optionValues?: unknown };
type Instance = { name?: unknown; controllerName?: unknown; savedDevice?: unknown; tasks?: unknown };
/** MXU's file as read: its instance to read (the last used, else the first), how many it has, and its global values. */
function mxuFile(text: string): { instance: Instance; instances: number; globals: Record<string, unknown> } {
  const raw: unknown = JSON.parse(text);
  const list = isObject(raw) && Array.isArray(raw.instances) ? raw.instances.filter(isObject) : [];
  if (!list.length) throw new Error("no instance");
  const root = raw as Record<string, unknown>;
  const instance = list.find((i) => i.id === root.lastActiveInstanceId) ?? list[0];
  return { instance, instances: list.length, globals: isObject(root.globalOptionValues) ? root.globalOptionValues : {} };
}

/** The deleted teams' labels the team options file still has: its cases' labels by team id, the deleted mark dropped. */
function teamLabels(text: string | null): Map<string, string> {
  const out = new Map<string, string>();
  try {
    const option = text === null ? {} : (JSON.parse(text) as { option?: Record<string, { cases?: { name?: unknown; label?: unknown }[] }> }).option ?? {};
    for (const o of Object.values(option)) for (const c of o?.cases ?? []) {
      if (typeof c?.name === "string" && typeof c.label === "string") out.set(c.name, c.label.replace(/（已刪除）$| \(deleted\)$/, ""));
    }
  } catch {
    // a file that does not read names no team: the report gives the id
  }
  return out;
}

/** The settings with the read-back done, and what it read and missed. `data` is the migrated file, `version` the version
 * it had (20, 21 or 22), `files` config/'s files as read. */
export function readBack(data: Settings, version: number, files: ReadBackFiles): { data: Settings; report: Report } {
  const out = structuredClone(data);
  const problems: string[] = [];
  const text = (key: FileKey) => {
    const f = files[key];
    if (f !== null && typeof f === "object") problems.push(`${READ_BACK_FILES[key]}: ${f.error}`);
    return typeof f === "string" ? f : null;
  };
  const reader = new Reader(out, teamLabels(text("teamOptions")));
  let mxu: ReturnType<typeof mxuFile> | null = null;
  const mxuText = text("mxu");
  if (mxuText !== null) {
    try {
      mxu = mxuFile(mxuText);
    } catch (e) {
      problems.push(`${READ_BACK_FILES.mxu}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  // the file's own values (version 20), else MXU's, else settings.v20.json's: each starts from the defaults
  let source: Source = version === 20 ? "file" : mxu ? "mxu" : "defaults";
  if (source !== "file") Object.assign(out, pickSections(newSections()));
  const v20Text = source === "defaults" ? text("v20") : null;
  if (v20Text !== null) {
    try {
      const old: unknown = JSON.parse(v20Text);
      if (!isObject(old)) throw new Error("not a settings file");
      source = "v20";
      for (const path of OPTION_PATHS) {
        const v = getAt(old, path);
        if (v === undefined) continue;
        if (TEAM_PATHS.has(path)) reader.team(path, v);
        else reader.value(path, v);
      }
    } catch (e) {
      problems.push(`${READ_BACK_FILES.v20}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  let tasks: Settings["tasks"] | null = null;
  let address: string | null = null;
  if (mxu) {
    const { instance, globals } = mxu;
    const ctrl = typeof instance.controllerName === "string" ? instance.controllerName : "";
    const ticked = (t: MxuTask) => {
      const by = isObject(t.enabledByController) ? t.enabledByController[ctrl] : undefined;
      return typeof by === "boolean" ? by : t.enabled === true;
    };
    // each MXU entry an entry of the task list, with its own tick, in MXU's order (#811: a task may be listed twice)
    const entries: { id: string; task: MxuTask }[] = [];
    for (const t of (Array.isArray(instance.tasks) ? instance.tasks : []).filter(isObject) as MxuTask[]) {
      const name = String(t.taskName);
      if (!TASK_IDS.includes(name)) {
        if (!reader.missed.some((m) => m.kind === "task" && m.name === name)) reader.missed.push({ kind: "task", name });
        continue;
      }
      entries.push({ id: name, task: t });
    }
    tasks = entries.map(({ id, task }) => ({ id, enabled: ticked(task) }));
    // a task v1's list did not have goes last, unticked, once each in a new file's order: this one-time import puts it back,
    // a load does not (#874)
    tasks.push(...TASK_ORDER.filter((id) => !entries.some((e) => e.id === id)).map((id) => ({ id, enabled: false })));
    out.tasks = structuredClone(tasks);
    const device = isObject(instance.savedDevice) ? instance.savedDevice.adbDeviceAddress : undefined;
    if (typeof device === "string" && device.trim() !== "") out.emulator.address = address = device.trim();
    if (source === "mxu") {
      for (const id of new Set(entries.map((e) => e.id))) {
        const list = entries.filter((e) => e.id === id).map((e) => e.task);
        const specs = Object.entries(TASK_OPTIONS[id] ?? {});
        const paths = [...new Set(specs.map(([, s]) => s.path))];
        const readInto = (r: Reader, t: MxuTask) => {
          const values = isObject(t.optionValues) ? t.optionValues : {};
          // the runs' switch before the runs: its No wins over a count MXU still holds
          const limitOff = isObject(values.MirrorRunsLimit) && values.MirrorRunsLimit.value === false;
          for (const [name, s] of specs) if (name in values && !(limitOff && name === "MirrorRuns")) r.mxu(s, values[name]);
        };
        // the task's entries share its options: the first ticked one's count, and copies that read as other values are named
        const readAs = (t: MxuTask) => {
          const r = new Reader(structuredClone(out), reader.labels);
          readInto(r, t);
          return JSON.stringify(paths.map((path) => getAt(r.data, path)));
        };
        if (new Set(list.map(readAs)).size > 1) reader.missed.push({ kind: "differ", task: id, n: list.length });
        readInto(reader, list.find(ticked) ?? list[0]);
      }
      for (const [name, s] of Object.entries(GLOBAL_OPTIONS)) if (name in globals) reader.mxu(s, globals[name]);
    }
  }
  const defaults = newSections() as unknown as Settings;
  const read = OPTION_PATHS.flatMap((path) => {
    const v = getAt(out, path);
    return JSON.stringify(v) === JSON.stringify(getAt(defaults, path)) ? [] : [{ path, value: v }];
  });
  const same = [...reader.read].filter((path) => !read.some((r) => r.path === path)).length;
  const absent = (Object.keys(READ_BACK_FILES) as FileKey[]).filter((k) => files[k] === null).map((k) => READ_BACK_FILES[k]);
  const instance = mxu && typeof mxu.instance.name === "string" ? mxu.instance.name : null;
  return {
    data: out,
    report: { from: version, source, instance, instances: mxu?.instances ?? 0, problems, read, same, absent, tasks, address, missed: reader.missed },
  };
}

/** The sections the read-back sets: the task options. The task list and the emulator stay as the migration made them
 * unless MXU's file has them. */
const pickSections = (s: ReturnType<typeof newSections>) => ({ run: s.run, luxcavation: s.luxcavation, charge_enkephalin: s.charge_enkephalin });
