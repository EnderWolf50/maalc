// The values a version 20 settings file held that the client's task and global options hold now (#782, spec 04 section 2):
// each one off the client's default, as the client option to set and the value to set it to. The window lists them once,
// when it migrates the file (App.tsx). The client's defaults are assets/interface.json's, as this GUI was built with it.
import enUs from "../../assets/locales/en_us.json";
import zhTw from "../../assets/locales/zh_tw.json";
import { TEXT } from "./i18n";
import type { Settings, Team } from "./model";
import { NONE, PI, TEAM_OPTIONS, taskOf, teamLabel, type TeamPicks } from "./teamOptions";

/** A moved value as the client option to set: NAME=VALUE as `tools/live/bot.py run --option` takes it, a select's case
 * name, a switch's Yes or No, an input's text, SET for a password input (the webhook) that has a value. */
export interface Moved { option: string; value: string }
export const SET = "(set)";

type Attach = Record<string, unknown>;
interface Case { name: string; label?: string; option?: string[]; pipeline_override?: Record<string, { attach?: Attach }> }
interface Input { name: string; default?: string; pipeline_type?: string; password?: boolean }
interface Option {
  type?: string; label: string; default_case?: string; cases?: Case[]; inputs?: Input[];
  pipeline_override?: Record<string, { attach?: Attach }>;
}
const OPTIONS = PI.option as unknown as Record<string, Option>;

/** An object member of o, else {} (a section missing or broken by hand). */
const section = (o: unknown, key: string): Attach => {
  const v = o && typeof o === "object" ? (o as Attach)[key] : undefined;
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Attach) : {};
};

/** The attach each node would have had for the version 20 file's values: the keys the agent read there before #779,
 * #780 and #781 moved them (agent/task_options.schema.json). Its run cap of null is the limit switch off. */
function oldAttach(old: Attach): Record<string, Attach> {
  const run = section(old, "run"), lux = section(old, "luxcavation");
  const { webhook_url, auto_accept_terms, auto_download, keep_dismissed_screens, runs, ...mirror } = run;
  return {
    GlobalOptions: { webhook_url, auto_accept_terms, auto_download, keep_dismissed_screens },
    MirrorDungeon: { ...mirror, runs_limited: runs === undefined ? undefined : runs !== null, runs },
    ExpLuxcavation: section(lux, "exp"), ThreadLuxcavation: section(lux, "thread"),
    ChargeEnkephalin: section(old, "charge_enkephalin"),
  };
}

/** The teams a version 20 file picked for its Luxcavation tasks: what a first team options file starts on (teamOptions.ts).
 * A pick that is not a team id (a file broken by hand) is none. */
export function teamPicks(old: Attach): TeamPicks {
  const pick = (task: string) => {
    const team = section(section(old, "luxcavation"), task).team;
    return typeof team === "string" && team !== "" ? team : null;
  };
  return { ExpTeam: pick(TEAM_OPTIONS.ExpTeam), ThreadTeam: pick(TEAM_OPTIONS.ThreadTeam) };
}

/** The node and attach key an override writes, and the value (one each, ADR 0013). */
const writes = (override: Case["pipeline_override"]) => {
  const [node, values] = Object.entries(override ?? {})[0] ?? [];
  const [key, value] = Object.entries(values?.attach ?? {})[0] ?? [];
  return node && key ? { node, key, value } : null;
};

/** Option key's value off its default, then those of the options nested under the case the old values pick: a nested
 * input is the client's only while its case is chosen (a count in count mode alone). */
function collect(key: string, attach: Record<string, Attach>, out: Moved[]) {
  const opt = OPTIONS[key];
  if (!opt) return;
  if (key in TEAM_OPTIONS) { // its cases are the team options file's; 「未選擇」 is its default
    const team = attach[taskOf(key)!.entry]?.team;
    if (typeof team === "string" && team !== "" && team !== NONE) out.push({ option: key, value: team });
    return;
  }
  if (opt.type === "input") {
    const input = opt.inputs![0], to = writes(opt.pipeline_override);
    if (!to) return;
    const value = attach[to.node]?.[to.key];
    const int = input.pipeline_type === "int";
    if (int ? !Number.isInteger(value) : typeof value !== "string") return; // a value the client does not take
    if (value !== (int ? Number(input.default || 0) : input.default ?? "")) {
      out.push({ option: key, value: input.password ? SET : String(value) });
    }
    return;
  }
  const cases = opt.cases ?? [];
  const picked = cases.find((c) => {
    const to = writes(c.pipeline_override);
    return to !== null && attach[to.node]?.[to.key] === to.value;
  });
  if (!picked) return;
  if (picked.name !== (opt.default_case ?? cases[0]?.name)) out.push({ option: key, value: picked.name });
  for (const nested of picked.option ?? []) collect(nested, attach, out);
}

/** The old file's values off the client's default, in the order the client sends them: the global options, then each
 * task's own (interface.json's task order). A value no case or input takes (a file broken by hand) is left out. */
export function movedOptions(old: Attach): Moved[] {
  const attach = oldAttach(old), out: Moved[] = [];
  for (const key of [...(PI.global_option ?? []), ...PI.task.flatMap((t) => t.option ?? [])]) collect(key, attach, out);
  return out;
}

const LOCALES = { zh_tw: zhTw, en_us: enUs } as Record<Settings["language"], Record<string, string>>;

/** One moved value in the window's words: the client's task (its global options' section for one of those), the
 * option's name and the value, as the client shows them. */
export interface MovedRow { task: string; option: string; value: string }

/** The label of the task, or of the global options' section, an option is set in; a nested option's is the one of the
 * option it is under. */
function taskLabel(key: string): string {
  const parent = Object.entries(OPTIONS).find(([, o]) => o.cases?.some((c) => c.option?.includes(key)));
  if (parent) return taskLabel(parent[0]);
  return PI.setting?.find((s) => s.option.includes(key))?.label ?? taskOf(key)?.label ?? key;
}

export function sayMoved(moved: Moved[], teams: Team[], lang: Settings["language"]): MovedRow[] {
  // a label of interface.json: a $ key in the language's locale file, anything else as it is
  const localized = (label: string) => (label.startsWith("$") ? LOCALES[lang][label.slice(1)] ?? label.slice(1) : label);
  const words = TEXT[lang];
  return moved.map(({ option, value }) => {
    const opt = OPTIONS[option];
    let said = value;
    if (option in TEAM_OPTIONS) {
      const team = teams.find((t) => t.id === value);
      said = team ? teamLabel(team, lang) : value;
    } else if (value === SET && opt.inputs?.[0]?.password) {
      said = words["moved.set"];
    } else if (opt.type === "switch") {
      said = words[value === "Yes" ? "moved.on" : "moved.off"];
    } else if (opt.type !== "input") {
      const label = opt.cases?.find((c) => c.name === value)?.label;
      said = label ? localized(label) : value;
    }
    return { task: localized(taskLabel(option)), option: localized(opt.label), value: said };
  });
}
