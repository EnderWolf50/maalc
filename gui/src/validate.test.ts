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

test("a new file is valid without a team (#364: only MirrorDungeon asks for one), and with new teams", () => {
  const s = newSettings();
  expect(validate(s)).toEqual([]);
  s.teams.push(newTeam(1, "隊伍 1"), newTeam(2, "隊伍 2"));
  expect(validate(s)).toEqual([]);
  expect(s.teams.map((x) => x.game_team)).toEqual([1, 2]);
});

test("parseSettings refuses newer and unmigratable versions", () => {
  expect(() => parseSettings('{"version": 14}')).toThrow("newer");
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

test("version 6 keeps what the shop kept before", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) for (const k of ["keep_keywords", "keywordless", "keep_gifts", "sell_max_tier", "sell_vestiges"]) delete t[k];
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 6 }));
  expect(migrated).toBe(true);
  const kept = [[], "keep", [], 4, false];
  expect(data.teams.map((t) => [t.keep_keywords, t.keywordless, t.keep_gifts, t.sell_max_tier, t.sell_vestiges])).toEqual([kept, kept]);
  expect(validate(data)).toEqual([]);
});

test("version 11 gets both Luxcavations with no team picked", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown>;
  delete old.luxcavation;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 11 }));
  expect(migrated).toBe(true);
  expect(data.luxcavation).toEqual({ exp: { count: 1, team: null, retries: 0 }, thread: { count: 1, team: null, retries: 0 } });
  expect(validate(data)).toEqual([]);
});

test("version 12 gets Thread Luxcavation and keeps EXP", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { luxcavation: Record<string, unknown> };
  old.luxcavation = { exp: { count: 3, team: "a", retries: 1 } };
  const { data } = parseSettings(JSON.stringify({ ...old, version: 12 }));
  expect(data.luxcavation).toEqual({ exp: { count: 3, team: "a", retries: 1 }, thread: { count: 1, team: null, retries: 0 } });
  expect(validate(data)).toEqual([]);
});

test("version 13 gets no Lunacy charges and keeps the rest", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown>;
  delete old.charge_enkephalin;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 13 }));
  expect(migrated).toBe(true);
  expect(data.charge_enkephalin).toEqual({ count: 0 });
  expect(data.luxcavation).toEqual(cases.valid.luxcavation);
  expect(validate(data)).toEqual([]);
});

test("version 10 keeps the dismissed screens", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { run: Record<string, unknown> };
  delete old.run.keep_dismissed_screens;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 10 }));
  expect(migrated).toBe(true);
  expect(data.run.keep_dismissed_screens).toBe(true);
  expect(validate(data)).toEqual([]);
});

test("version 9 fuses as before", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.fusion_condition;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 9 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.fusion_condition)).toEqual(["any", "any"]);
  expect(validate(data)).toEqual([]);
});

test("version 7 accepts the User Agreement and downloads", () => {
  const old = structuredClone(cases.valid) as Record<string, unknown> & { run: Record<string, unknown> };
  delete old.run.auto_accept_terms;
  delete old.run.auto_download;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 7 }));
  expect(migrated).toBe(true);
  expect([data.run.auto_accept_terms, data.run.auto_download]).toEqual([true, true]);
  expect(validate(data)).toEqual([]);
});

test("version 8 theme pack marks become weights that pick as before", () => {
  // #240: prefer / neutral / avoid -> 5 / 0 / -5, threshold 0, unlisted 0, event packs by weight.
  const old = structuredClone(cases.valid) as Record<string, unknown> & { theme_pack_plans: Record<string, unknown>[] };
  old.theme_pack_plans = [{ id: "p1", name: "Mine", marks: { "Automated Factory": "avoid", "The Forgotten": "prefer", "Lake World": "neutral" } }];
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 8 }));
  expect(migrated).toBe(true);
  expect(data.theme_pack_plans).toEqual([{
    id: "p1", name: "Mine", weights: { "Automated Factory": -5, "The Forgotten": 5, "Lake World": 0 },
    threshold: 0, unlisted: 0, event_packs: "weight",
  }]);
  expect(validate(data)).toEqual([]);
});

test("parseThemePacks reads the season's data file", () => {
  const data = parseThemePacks(themePacksYaml);
  expect(data.packs["Walpurgis Night: Hatred and Despair"]).toBe("N34 H34");
  // the BokGak re-runs are packs of their own, on HARD floors 4-5, weighed as their originals
  expect(data.packs["Miracle in District 20 BokGak"]).toBe("H45");
  expect(data.default_plan.weights["Timekilling Time BokGak"]).toBe(data.default_plan.weights["Timekilling Time"]);
  // #240: AALC's weights, threshold 0, unlisted 0.
  expect(data.default_plan).toMatchObject({ threshold: 0, unlisted: 0, event_packs: "weight" });
  expect(data.default_plan.weights["The B.E."]).toBe(10);
  expect(Object.keys(data.default_plan.weights).every((p) => p in data.packs)).toBe(true);
  expect(parseThemePacks("")).toEqual({ packs: {}, default_plan: { weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" } });
});
