// The team options file (#780, ADR 0013): config/team_options.json, which assets/interface.json imports, gives the client's
// ExpTeam and ThreadTeam dropdowns a case per team. MXU replaces an option's whole definition with the imported one,
// MFAAvalonia its cases, so each option here is interface.json's placeholder with its cases and default_case filled in.
// The cases are only ever appended, in the file's own order: MFAAvalonia stores the index of the case picked and MXU its
// name, so a case moved or gone would make a picked team another team or none, silently.
import interfaceText from "../../assets/interface.json?raw";
import type { Settings, Team } from "./model";

/** assets/interface.json as this GUI was built with it: its whole-line // comments dropped, as the clients read them. */
export const PI = JSON.parse(interfaceText.split("\n").filter((line) => !line.trim().startsWith("//")).join("\n")) as {
  import?: string[];
  global_option?: string[];
  setting?: { label: string; option: string[] }[];
  task: { entry: string; label: string; option?: string[] }[];
  option: Record<string, Record<string, unknown>>;
};

/** Each team option and the Luxcavation task of a version 20 settings file (luxcavation.<task>.team) whose team it picks. */
export const TEAM_OPTIONS = { ExpTeam: "exp", ThreadTeam: "thread" } as const;
export type TeamOption = keyof typeof TEAM_OPTIONS;
/** The team each option starts on in a new file (default_case): a teams[] id, null for none. */
export type TeamPicks = Record<TeamOption, string | null>;
export const NO_PICKS: TeamPicks = { ExpTeam: null, ThreadTeam: null };

/** The teams a version 20 file picked for its Luxcavation tasks (#782): what a first team options file starts on. A pick
 * that is not a team id (a file broken by hand) is none. */
export function teamPicks(old: Record<string, unknown>): TeamPicks {
  const of = (o: unknown, key: string) => (o && typeof o === "object" ? (o as Record<string, unknown>)[key] : undefined);
  const pick = (task: string) => {
    const team = of(of(old.luxcavation, task), "team");
    return typeof team === "string" && team !== "" ? team : null;
  };
  return { ExpTeam: pick(TEAM_OPTIONS.ExpTeam), ThreadTeam: pick(TEAM_OPTIONS.ThreadTeam) };
}

/** Case 0, 「未選擇」: it sends nothing, so the task stops at its start and asks for a team. A team id is never "none" in
 * a file this GUI made (newId); a hand-made team of that id gets no case of its own. */
export const NONE = "none";
/** Its label, a text key of interface.json's languages: the client says it in its own. */
export const NONE_LABEL = "$LuxTeam_none";
/** What a deleted team's label ends with, in each language of the GUI: its case stays and still sends its id, which
 * stops the task with a line saying so. */
const DELETED = { zh_tw: "（已刪除）", en_us: " (deleted)" } as const;

interface Case { name: string; label: string; pipeline_override?: Record<string, { attach: { team: string } }> }
interface Option { cases: Case[]; default_case: string }

/** The entry node of the task whose options list key: its cases write team into that node's attach. */
const entryOf = (key: TeamOption) => PI.task.find((t) => t.option?.includes(key))!.entry;

/** A team's label in the dropdown: its name and its in-game slot. The client shows it as it is: a name starting with $
 * would be read as a text key (MXU shows it without the $). */
export const teamLabel = (t: Team, lang: Settings["language"]) =>
  lang === "zh_tw" ? `${t.name}（TEAMS #${t.game_team}）` : `${t.name} (TEAMS #${t.game_team})`;

/** The previous file's cases and default_case of each team option; null when there is none or it does not read as one
 * this GUI wrote (then the file starts over). */
function readPrevious(text: string | null): Partial<Record<TeamOption, Option>> | null {
  if (text === null) return null;
  try {
    const option = (JSON.parse(text) as { option?: Record<string, Partial<Option>> }).option ?? {};
    const out: Partial<Record<TeamOption, Option>> = {};
    for (const key of Object.keys(TEAM_OPTIONS) as TeamOption[]) {
      const o = option[key];
      const named = Array.isArray(o?.cases) && o.cases.every((c) => typeof c?.name === "string" && typeof c?.label === "string");
      if (!named || o!.cases![0]?.name !== NONE || typeof o!.default_case !== "string") return null;
      out[key] = { cases: o!.cases!, default_case: o!.default_case };
    }
    return out;
  } catch {
    return null;
  }
}

/** The team options file's text for these settings, given the file's text as it is now (null: none): null when that
 * already says it, or when there is neither a file nor a team (nothing to write). A file that does not read as one this
 * GUI wrote starts over, as a new one. Each option keeps the file's cases in
 * their order: a team there gets its name and slot of now (a rename changes only the label), a team gone stays,
 * marked deleted, and each new team goes last, in the team queue's order. A new file's default_case is the team picks
 * gives that option, the one a version 20 file picked (teamPicks; MXU starts a task it has no value for on it,
 * MFAAvalonia starts on case 0), else 「未選擇」; an existing file's stays. */
export function teamOptionsText(previous: string | null, s: Settings, picks: TeamPicks = NO_PICKS): string | null {
  const before = readPrevious(previous);
  if (previous === null && !s.teams.length) return null;
  const ids = new Set(s.teams.map((t) => t.id));
  const option: Record<string, Record<string, unknown>> = {};
  for (const key of Object.keys(TEAM_OPTIONS) as TeamOption[]) {
    const node = entryOf(key);
    const send = (id: string) => ({ [node]: { attach: { team: id } } });
    const teamCase = (t: Team): Case => ({ name: t.id, label: teamLabel(t, s.language), pipeline_override: send(t.id) });
    const gone = (c: Case): Case => {
      const base = Object.values(DELETED).reduce((l, mark) => (l.endsWith(mark) ? l.slice(0, -mark.length) : l), c.label);
      return { name: c.name, label: base + DELETED[s.language], pipeline_override: send(c.name) };
    };
    const old = before?.[key];
    const kept = (old?.cases ?? [{ name: NONE, label: "" }]).map((c) => {
      if (c.name === NONE) return { name: NONE, label: NONE_LABEL };
      const team = s.teams.find((t) => t.id === c.name);
      return team ? teamCase(team) : gone(c);
    });
    const added = s.teams.filter((t) => t.id !== NONE && !kept.some((c) => c.name === t.id)).map(teamCase);
    const cases = [...kept, ...added];
    const picked = picks[key];
    const default_case = old ? old.default_case : picked !== null && ids.has(picked) && picked !== NONE ? picked : NONE;
    const { cases: _cases, default_case: _default, ...placeholder } = PI.option[key];
    option[key] = { ...placeholder, default_case, cases };
  }
  const text = JSON.stringify({ option }, null, 2) + "\n";
  return text === previous ? null : text;
}
