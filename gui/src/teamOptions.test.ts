// The team options file's generator (#780): teams only appended, a deleted team kept and marked, a rename only its label,
// the queue's order left alone, a first file's default_case from the settings file, and nothing to write when nothing
// changed.
import { expect, test } from "vitest";
import cases from "../../tests/settings_cases.json";
import fixture from "../../tests/team_options.json";
import libRs from "../src-tauri/src/lib.rs?raw";
import { newSettings, newTeam, type Settings, type Team } from "./model";
import { NONE, NONE_LABEL, PI, TEAM_OPTIONS, teamOptionsText } from "./teamOptions";

const team = (id: string, name: string, slot: number): Team => ({ ...newTeam(slot, name), id });
const A = team("a", "Alpha", 1), B = team("b", "Beta", 2), C = team("c", "Gamma", 3);
const settings = (teams: Team[], language: Settings["language"] = "zh_tw"): Settings => ({ ...newSettings(), language, teams });
type Case = { name: string; label: string; pipeline_override?: Record<string, { attach: { team: string } }> };
const option = (text: string, key: keyof typeof TEAM_OPTIONS = "ExpTeam") =>
  (JSON.parse(text) as { option: Record<string, { cases: Case[]; default_case: string }> }).option[key];
const names = (text: string, key: keyof typeof TEAM_OPTIONS = "ExpTeam") => option(text, key).cases.map((c) => c.name);
const caseOf = (text: string, name: string, key: keyof typeof TEAM_OPTIONS = "ExpTeam") =>
  option(text, key).cases.find((c) => c.name === name)!;

test("a new team goes last, after the teams the file has, wherever it is in the queue", () => {
  const first = teamOptionsText(null, settings([A, B]))!;
  const next = teamOptionsText(first, settings([C, A, B]))!;
  expect(names(next)).toEqual([NONE, "a", "b", "c"]);
  expect(names(next, "ThreadTeam")).toEqual([NONE, "a", "b", "c"]);
  expect(caseOf(next, "c")).toEqual({ name: "c", label: "Gamma（TEAMS #3）", pipeline_override: { ExpLuxcavation: { attach: { team: "c" } } } });
  expect(caseOf(next, "c", "ThreadTeam").pipeline_override).toEqual({ ThreadLuxcavation: { attach: { team: "c" } } });
});

test("a deleted team keeps its case, marked deleted, and the case still sends its id", () => {
  // MFAAvalonia stores the case's index: a case gone would shift every pick after it to another team
  const first = teamOptionsText(null, settings([A, B]))!;
  const next = teamOptionsText(first, settings([B]))!;
  expect(names(next)).toEqual([NONE, "a", "b"]);
  expect(caseOf(next, "a")).toEqual({ name: "a", label: "Alpha（TEAMS #1）（已刪除）", pipeline_override: { ExpLuxcavation: { attach: { team: "a" } } } });
  expect(teamOptionsText(next, settings([B]))).toBeNull(); // marked once, not again at the next save
  expect(caseOf(teamOptionsText(next, settings([B], "en_us"))!, "a").label).toBe("Alpha（TEAMS #1） (deleted)");
});

test("a rename changes only the team's label", () => {
  const first = teamOptionsText(null, settings([A, B]))!;
  const next = teamOptionsText(first, settings([A, { ...B, name: "Beta 2", game_team: 7 }]))!;
  expect(names(next)).toEqual(names(first));
  expect(caseOf(next, "b")).toEqual({ ...caseOf(first, "b"), label: "Beta 2（TEAMS #7）" });
});

test("a new order of the team queue leaves the cases where they are: nothing to write", () => {
  // the agent moves a team to the end of the queue after each claim (ADR 0011)
  const first = teamOptionsText(null, settings([A, B, C]))!;
  expect(teamOptionsText(first, settings([C, A, B]))).toBeNull();
  expect(teamOptionsText(first, settings([B, C, A], "zh_tw"))).toBeNull();
});

test("a first file's default_case is the team the settings file picks for that task; a later file keeps its own", () => {
  const s = settings([A, B]);
  s.luxcavation.exp.team = "b";
  const first = teamOptionsText(null, s)!;
  expect([option(first).default_case, option(first, "ThreadTeam").default_case]).toEqual(["b", NONE]);
  s.luxcavation.exp.team = "a";
  s.luxcavation.thread.team = "b";
  expect(teamOptionsText(first, s)).toBeNull();
  s.luxcavation.exp.team = "gone"; // a pick the teams lack: 「未選擇」
  expect(option(teamOptionsText(null, s)!).default_case).toBe(NONE);
});

test("nothing changed, or neither a file nor a team: nothing to write", () => {
  const first = teamOptionsText(null, settings([A]))!;
  expect(teamOptionsText(first, settings([A]))).toBeNull();
  expect(teamOptionsText(null, settings([]))).toBeNull();
  expect(names(teamOptionsText(first, settings([]))!)).toEqual([NONE, "a"]); // every team deleted: still a file
});

test("a file that does not read as one the GUI wrote starts over", () => {
  expect(names(teamOptionsText("{ oops", settings([B, A]))!)).toEqual([NONE, "b", "a"]);
  expect(names(teamOptionsText(JSON.stringify({ option: {} }), settings([A]))!)).toEqual([NONE, "a"]);
});

test("case 0 is 「未選擇」, which sends nothing, named by a text key of interface.json's languages", () => {
  const text = teamOptionsText(null, settings([A]))!;
  for (const key of Object.keys(TEAM_OPTIONS) as (keyof typeof TEAM_OPTIONS)[]) {
    expect(option(text, key).cases[0]).toEqual({ name: NONE, label: NONE_LABEL });
  }
});

test("tests/team_options.json is what the GUI writes for settings_cases.json's valid teams once a team was deleted", () => {
  // the agent's tests post the client's override from this file (tests/client_options.py)
  const valid = cases.valid as unknown as Settings;
  const first = teamOptionsText(null, { ...valid, teams: [...valid.teams, team("gone", "Team gone", 5)] })!;
  expect(JSON.parse(teamOptionsText(first, valid)!)).toEqual(fixture);
});

test("each option is interface.json's placeholder, its cases and default_case filled in", () => {
  // MXU replaces an option's whole definition with the imported one: the file carries all of it
  const text = teamOptionsText(null, settings([A]))!;
  const rest = ({ cases: _c, default_case: _d, ...o }: Record<string, unknown>) => o;
  for (const key of Object.keys(TEAM_OPTIONS) as (keyof typeof TEAM_OPTIONS)[]) {
    expect(PI.option[key].cases).toEqual([]);
    expect(rest(option(text, key) as unknown as Record<string, unknown>)).toEqual(rest(PI.option[key]));
  }
});

test("interface.json imports the file the GUI writes (src-tauri lib.rs team_options_path)", () => {
  expect(PI.import).toEqual(["config/team_options.json"]);
  const joined = PI.import![0].split("/").map((part) => `.join("${part}")`).join("");
  expect(libRs.replace(/\r\n/g, "\n")).toContain(`fn team_options_path() -> Result<PathBuf, String> {\n    Ok(root()?${joined})`);
});
