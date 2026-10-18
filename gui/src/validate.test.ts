// Runs tests/settings_cases.json, which tests/test_settings.py runs against agent/settings.py too.
import { describe, expect, test } from "vitest";
import cases from "../../tests/settings_cases.json";
import themePacksYaml from "../../assets/resource/base/data/theme_packs.yaml?raw";
import { newSettings, newTeam, parseSettings, parseThemePacks } from "./model";
import { pyRepr, validate } from "./validate";

type Edit = { set: string; value: unknown } | { delete: string };

function applyEdits(data: unknown, edits: Edit[]) {
  const out = structuredClone(data) as Record<string, unknown>;
  for (const edit of edits) {
    const parts = ("set" in edit ? edit.set : edit.delete).split("/");
    const last = parts.pop()!;
    let node = out as Record<string, unknown>;
    for (const key of parts) node = node[key] as Record<string, unknown>;
    if (!("set" in edit)) delete node[last];
    else if (last === "-") (node as unknown as unknown[]).push(edit.value);
    else node[last] = edit.value;
  }
  return out;
}

describe("tests/settings_cases.json", () => {
  test("valid file passes", () => expect(validate(cases.valid)).toEqual([]));

  for (const c of cases.cases as { name: string; edits: Edit[]; schema?: string[]; cross?: string[] }[]) {
    test(c.name, () => {
      const problems = validate(applyEdits(cases.valid, c.edits));
      if (c.cross) {
        expect(problems.map((p) => p.text)).toEqual(c.cross);
      } else {
        const paths = new Set(problems.map((p) => p.text.split(": ")[0]));
        for (const s of c.schema!) expect(paths).toContain(s);
        for (const p of paths) expect(c.schema!.some((s) => p === s || p.startsWith(s + "/"))).toBe(true);
      }
    });
  }
});

test("pyRepr matches Python repr", () => {
  expect(pyRepr("a")).toBe("'a'");
  expect(pyRepr("Don't")).toBe(`"Don't"`);
  expect(pyRepr(`'"`)).toBe(`'\\'"'`);
  expect(pyRepr("a\\b")).toBe("'a\\\\b'");
});

test("a new file asks for a team, and new teams make it valid", () => {
  const s = newSettings();
  expect(validate(s).map((p) => p.text)).toEqual(["No enabled team: set up a team in the settings GUI first."]);
  s.teams.push(newTeam(1, "隊伍 1"), newTeam(2, "隊伍 2"));
  expect(validate(s)).toEqual([]);
  expect(s.teams.map((x) => x.game_team)).toEqual([1, 2]);
});

test("parseSettings refuses newer and unmigratable versions", () => {
  expect(() => parseSettings('{"version": 7}')).toThrow("newer");
  expect(() => parseSettings('{"version": 0}')).toThrow("cannot be migrated");
});

test("version 1 gets guard turns off", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.guard_turns;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 1 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.guard_turns)).toEqual([0, 0]);
  expect(validate(data)).toEqual([]);
});

test("version 2 gets gift search off", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.gift_search;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 2 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.gift_search)).toEqual([{ enabled: false, gifts: [] }, { enabled: false, gifts: [] }]);
  expect(validate(data)).toEqual([]);
});

test("version 3 refreshes all-avoid theme pack pages as before", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { run: Record<string, unknown> };
  delete old.run.theme_pack_refresh;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 3 }));
  expect(migrated).toBe(true);
  expect(data.run.theme_pack_refresh).toBe("all");
  expect(validate(data)).toEqual([]);
});

test("version 4 teams may hold White Gossypium as before", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.allow_white_gossypium;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 4 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.allow_white_gossypium)).toEqual([true, true]);
  expect(validate(data)).toEqual([]);
});

test("version 5 zeros become switches", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { run: Record<string, unknown>; teams: Record<string, unknown>[] };
  old.run.runs = 0;
  old.teams[0].hard_from_floor = 0;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 5 }));
  expect(migrated).toBe(true);
  expect(data.run.runs).toBe(null); // no run limit
  expect(data.teams.map((t) => t.hard_from_floor)).toEqual([1, 3]); // 0 was the whole run HARD: from floor 1
  expect(validate(data)).toEqual([]);
});

test("parseThemePacks reads the season's data file", () => {
  const data = parseThemePacks(themePacksYaml);
  expect(data.packs).toContain("Walpurgis Night: Hatred and Despair");
  expect(data.default_plan["The B.E."]).toBe("prefer"); // #89: the default plan has content
  expect(Object.keys(data.default_plan).every((p) => data.packs.includes(p))).toBe(true);
  expect(parseThemePacks("packs: [A]\ndefault_plan:\n  A: avoid\n")).toEqual({ packs: ["A"], default_plan: { A: "avoid" } });
  expect(parseThemePacks("")).toEqual({ packs: [], default_plan: {} });
});
