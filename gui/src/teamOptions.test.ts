// The team options file's generator (#780, #805): teams only appended, a deleted team kept and marked, a rename only its
// label, the order of the team list and of the team queue left alone, a first file's default_case from the settings file,
// the start team's option added to a file that has none, and nothing to write when nothing changed.
import { expect, test } from "vitest";
import fixture from "../../tests/team_options.json";
import libRs from "../src-tauri/src/lib.rs?raw";
import { newSettings, newTeam, type Settings, type Team } from "./model";
import { cases } from "./settingsCases";
import { FILE_OPTIONS, NONE, NONE_LABEL, PI, QUEUE, QUEUE_LABEL, teamOptionsText, type FileOption } from "./teamOptions";

const team = (id: string, name: string, slot: number): Team => ({ ...newTeam(slot, name), id });
const A = team("a", "Alpha", 1), B = team("b", "Beta", 2), C = team("c", "Gamma", 3);
const settings = (teams: Team[], language: Settings["language"] = "zh_tw"): Settings => ({ ...newSettings(), language, teams });
type Case = { name: string; label: string; pipeline_override?: Record<string, { attach: Record<string, string> }> };
const option = (text: string, key: FileOption = "ExpTeam") =>
  (JSON.parse(text) as { option: Record<string, { cases: Case[]; default_case: string }> }).option[key];
const names = (text: string, key: FileOption = "ExpTeam") => option(text, key).cases.map((c) => c.name);
const caseOf = (text: string, name: string, key: FileOption = "ExpTeam") =>
  option(text, key).cases.find((c) => c.name === name)!;
const KEYS = Object.keys(FILE_OPTIONS) as FileOption[];

test("a new team goes last, after the teams the file has, wherever it is in the team list", () => {
  const first = teamOptionsText(null, settings([A, B]))!;
  const next = teamOptionsText(first, settings([C, A, B]))!;
  expect(names(next)).toEqual([NONE, "a", "b", "c"]);
  expect(names(next, "ThreadTeam")).toEqual([NONE, "a", "b", "c"]);
  expect(names(next, "MirrorStartTeam")).toEqual([QUEUE, "a", "b", "c"]);
  expect(caseOf(next, "c")).toEqual({ name: "c", label: "Gamma（TEAMS #3）", pipeline_override: { ExpLuxcavation: { attach: { team: "c" } } } });
  expect(caseOf(next, "c", "ThreadTeam").pipeline_override).toEqual({ ThreadLuxcavation: { attach: { team: "c" } } });
  expect(caseOf(next, "c", "MirrorStartTeam").pipeline_override).toEqual({ MirrorDungeon: { attach: { start_team: "c" } } });
});

test("a deleted team keeps its case, marked deleted, and the case still sends its id", () => {
  // MFAAvalonia stores the case's index: a case gone would shift every pick after it to another team
  const first = teamOptionsText(null, settings([A, B]))!;
  const next = teamOptionsText(first, settings([B]))!;
  expect(names(next)).toEqual([NONE, "a", "b"]);
  expect(caseOf(next, "a")).toEqual({ name: "a", label: "Alpha（TEAMS #1）（已刪除）", pipeline_override: { ExpLuxcavation: { attach: { team: "a" } } } });
  expect(caseOf(next, "a", "MirrorStartTeam")).toEqual({ ...caseOf(next, "a"), pipeline_override: { MirrorDungeon: { attach: { start_team: "a" } } } });
  expect(teamOptionsText(next, settings([B]))).toBeNull(); // marked once, not again at the next save
  expect(caseOf(teamOptionsText(next, settings([B], "en_us"))!, "a").label).toBe("Alpha（TEAMS #1） (deleted)");
});

test("a rename changes only the team's label", () => {
  const first = teamOptionsText(null, settings([A, B]))!;
  const next = teamOptionsText(first, settings([A, { ...B, name: "Beta 2", game_team: 7 }]))!;
  expect(names(next)).toEqual(names(first));
  expect(caseOf(next, "b")).toEqual({ ...caseOf(first, "b"), label: "Beta 2（TEAMS #7）" });
});

test("a new order of the team list or of the team queue leaves the cases where they are: nothing to write", () => {
  // the user arranges the team list; the agent moves a team to the end of the queue after each claim, and a start team
  // to its head (ADR 0014)
  const first = teamOptionsText(null, settings([A, B, C]))!;
  expect(teamOptionsText(first, settings([C, A, B]))).toBeNull();
  expect(teamOptionsText(first, settings([B, C, A], "zh_tw"))).toBeNull();
  expect(teamOptionsText(first, { ...settings([A, B, C]), team_queue: ["c", "a", "b"] })).toBeNull();
});

test("a first file's default_case is the team the version 20 file picked for that task; a later file keeps its own", () => {
  const s = settings([A, B]);
  const first = teamOptionsText(null, s, { ExpTeam: "b", ThreadTeam: null })!;
  expect([option(first).default_case, option(first, "ThreadTeam").default_case]).toEqual(["b", NONE]);
  expect(teamOptionsText(first, s, { ExpTeam: "a", ThreadTeam: "b" })).toBeNull();
  expect(option(teamOptionsText(null, s, { ExpTeam: "gone", ThreadTeam: null })!).default_case).toBe(NONE); // not a team
  expect(option(teamOptionsText(null, s)!).default_case).toBe(NONE); // a version 21 file has no pick
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

test("case 0 is 「未選擇」, or the start team's 「照隊伍佇列」, which sends nothing, named by a text key of interface.json's languages", () => {
  const text = teamOptionsText(null, settings([A]))!;
  for (const key of ["ExpTeam", "ThreadTeam"] as const) expect(option(text, key).cases[0]).toEqual({ name: NONE, label: NONE_LABEL });
  expect(option(text, "MirrorStartTeam").cases[0]).toEqual({ name: QUEUE, label: QUEUE_LABEL });
  expect(option(text, "MirrorStartTeam").default_case).toBe(QUEUE);
});

test("a file written before the start team's option gains it at the next save, its other options as they were", () => {
  // #805: the file of #780 had ExpTeam and ThreadTeam only; their cases keep their order, a deleted team's too
  const first = JSON.parse(teamOptionsText(null, settings([A, B, C]), { ExpTeam: "b", ThreadTeam: null })!);
  delete first.option.MirrorStartTeam;
  const old = JSON.stringify(first, null, 2) + "\n";
  const next = teamOptionsText(old, settings([C, B]))!;
  for (const key of ["ExpTeam", "ThreadTeam"] as const) {
    expect(names(next, key)).toEqual([NONE, "a", "b", "c"]);
    expect(option(next, key).default_case).toBe(first.option[key].default_case);
  }
  expect(names(next, "MirrorStartTeam")).toEqual([QUEUE, "c", "b"]); // a new option: today's teams, in list order
  expect(option(next, "MirrorStartTeam").default_case).toBe(QUEUE);
  expect(teamOptionsText(next, settings([C, B]))).toBeNull();
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
  for (const key of KEYS) {
    expect(rest(option(text, key) as unknown as Record<string, unknown>)).toEqual(rest(PI.option[key]));
  }
  // the team options' placeholders have no case; the start team's holds its case 0 and its default, which the file keeps
  for (const key of ["ExpTeam", "ThreadTeam"] as const) expect(PI.option[key].cases).toEqual([]);
  expect(PI.option.MirrorStartTeam.cases).toEqual([option(text, "MirrorStartTeam").cases[0]]);
  expect(PI.option.MirrorStartTeam.default_case).toBe(option(text, "MirrorStartTeam").default_case);
});

test("interface.json imports the file the GUI writes (src-tauri lib.rs team_options_path)", () => {
  expect(PI.import).toEqual(["config/team_options.json"]);
  const joined = PI.import![0].split("/").map((part) => `.join("${part}")`).join("");
  expect(libRs.replace(/\r\n/g, "\n")).toContain(`fn team_options_path() -> Result<PathBuf, String> {\n    Ok(root()?${joined})`);
});
