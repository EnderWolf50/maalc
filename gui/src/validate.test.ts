// Runs tests/settings_cases.json, which tests/test_settings.py runs against agent/settings.py too.
import { describe, expect, test } from "vitest";
import cases from "../../tests/settings_cases.json";
import themePacksYaml from "../../assets/resource/base/data/theme_packs.yaml?raw";
import { cleanGiftList, defaultGorder, newSettings, newTeam, parseSettings, parseThemePacks, type GiftList } from "./model";
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
  expect(() => parseSettings('{"version": 12}')).toThrow("newer");
  expect(() => parseSettings('{"version": 0}')).toThrow("cannot be migrated");
});

test("version 1 gets guard turns off", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.guard_turns;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 1 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.guard_turns)).toEqual([0, 0]);
  expect(validate(data)).toEqual([]);
});

test("version 2 gets gift search off", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.gift_search;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 2 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.gift_search)).toEqual([{ enabled: false, gifts: [] }, { enabled: false, gifts: [] }]);
  expect(validate(data)).toEqual([]);
});

test("version 3 refreshes all-avoid theme pack pages as before", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { run: Record<string, unknown> };
  delete old.run.theme_pack_refresh;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 3 }));
  expect(migrated).toBe(true);
  expect(data.run.theme_pack_refresh).toBe("all");
  expect(validate(data)).toEqual([]);
});

test("version 4 teams may hold White Gossypium as before", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.allow_white_gossypium;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 4 }));
  expect(migrated).toBe(true);
  expect(data.teams.map((t) => t.allow_white_gossypium)).toEqual([true, true]);
  expect(validate(data)).toEqual([]);
});

test("version 5 zeros become switches", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { run: Record<string, unknown>; teams: Record<string, unknown>[] };
  old.run.runs = 0;
  old.teams[0].hard_from_floor = 0;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 5 }));
  expect(migrated).toBe(true);
  expect(data.run.runs).toBe(null); // no run limit
  expect(data.teams.map((t) => t.hard_from_floor)).toEqual([1, 3]); // 0 was the whole run HARD: from floor 1
  expect(validate(data)).toEqual([]);
});

test("version 6 keeps what the shop kept before", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) for (const k of ["keep_keywords", "keywordless", "keep_gifts", "sell_max_tier", "sell_vestiges"]) delete t[k];
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 6 }));
  expect(migrated).toBe(true);
  // Nothing else kept: the lists want the main keyword's gifts and keep the rest of it and the keywordless gifts (#291).
  expect(data.teams.map((t) => [t.sell_max_tier, t.sell_vestiges])).toEqual([[4, false], [4, false]]);
  expect(data.gift_lists.map((l) => l.order[0])).toEqual(["Burn", "Bleed"]);
  expect(data.gift_lists.map((l) => l.keep.includes(9273))).toEqual([true, true]); // a keywordless gift
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
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { teams: Record<string, unknown>[] };
  for (const t of old.teams) delete t.fusion_condition;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 9 }));
  expect(migrated).toBe(true);
  expect(data.gift_lists.map((l) => l.fusion_condition)).toEqual(["any", "any"]);
  expect(validate(data)).toEqual([]);
});

test("version 7 accepts the User Agreement and downloads", () => {
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { run: Record<string, unknown> };
  delete old.run.auto_accept_terms;
  delete old.run.auto_download;
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 7 }));
  expect(migrated).toBe(true);
  expect([data.run.auto_accept_terms, data.run.auto_download]).toEqual([true, true]);
  expect(validate(data)).toEqual([]);
});

test("version 8 theme pack marks become weights that pick as before", () => {
  // #240: prefer / neutral / avoid -> 5 / 0 / -5, threshold 0, unlisted 0, event packs by weight.
  const old = structuredClone(cases.valid10) as Record<string, unknown> & { theme_pack_plans: Record<string, unknown>[] };
  old.theme_pack_plans = [{ id: "p1", name: "Mine", marks: { "Automated Factory": "avoid", "The Forgotten": "prefer", "Lake World": "neutral" } }];
  const { data, migrated } = parseSettings(JSON.stringify({ ...old, version: 8 }));
  expect(migrated).toBe(true);
  expect(data.theme_pack_plans).toEqual([{
    id: "p1", name: "Mine", weights: { "Automated Factory": -5, "The Forgotten": 5, "Lake World": 0 },
    threshold: 0, unlisted: 0, event_packs: "weight",
  }]);
  expect(validate(data)).toEqual([]);
});

const sum = (ids: number[]) => ids.reduce((a, b) => a + b, 0);

type MigrationCase = {
  name: string; edits: Edit[]; teams: string[]; dropped: number;
  lists: { id: string; name: string; order_first: string; fusion_condition: string; want_count: number; keep_count: number;
    want_sum: number; keep_sum: number; want_has: number[]; keep_has: number[]; keep_lacks: number[] }[];
};

describe("version 10 teams become gift lists (tests/settings_cases.json migrations)", () => {
  for (const c of cases.migrations as MigrationCase[]) {
    test(c.name, () => {
      const { data, migrated, dropped } = parseSettings(JSON.stringify(applyEdits(cases.valid10, c.edits)));
      expect(migrated).toBe(true);
      expect(dropped).toBe(c.dropped);
      expect(data.teams.map((t) => t.gift_list)).toEqual(c.teams);
      expect(data.gift_lists.map((l) => l.id)).toEqual(c.lists.map((l) => l.id));
      data.gift_lists.forEach((got, i) => {
        const want = c.lists[i];
        expect([got.id, got.name, got.order[0], got.fusion_condition]).toEqual([want.id, want.name, want.order_first, want.fusion_condition]);
        expect([got.want.length, got.keep.length]).toEqual([want.want_count, want.keep_count]);
        expect([sum(got.want), sum(got.keep)]).toEqual([want.want_sum, want.keep_sum]);
        expect(got.gorder).toEqual(defaultGorder());
        for (const id of want.want_has) expect(got.want).toContain(id);
        for (const id of want.keep_has) expect(got.keep).toContain(id);
        for (const id of want.keep_lacks) expect(got.keep).not.toContain(id);
      });
      for (const t of data.teams) for (const k of ["keyword", "keep_keywords", "keywordless", "keep_gifts", "fusion_condition"]) expect(t).not.toHaveProperty(k);
      expect(validate(data)).toEqual([]);
    });
  }
});

describe("cleanGiftList (tests/settings_cases.json clean_gift_list)", () => {
  type CleanCase = {
    name: string; list: { want: number[]; keep: number[]; gorder: Record<string, number[]> }; want: number[]; keep: number[];
    dropped: number; gorder_head: Record<string, number[]>; gorder_size: Record<string, number>;
  };
  for (const c of cases.clean_gift_list as unknown as CleanCase[]) {
    test(c.name, () => {
      const base: GiftList = { id: "x", name: "x", order: [], fusion_condition: "any", ...c.list };
      const { list, dropped } = cleanGiftList(base);
      expect([list.want, list.keep, dropped]).toEqual([c.want, c.keep, c.dropped]);
      expect(Object.keys(list.gorder)).toHaveLength(11);
      for (const [k, head] of Object.entries(c.gorder_head)) expect(list.gorder[k].slice(0, head.length)).toEqual(head);
      for (const [k, size] of Object.entries(c.gorder_size)) expect(list.gorder[k]).toHaveLength(size);
    });
  }
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
  expect(data.pack_ids["The B.E."]).toBe(3001); // #306: every listed pack has an id
  expect(Object.keys(data.packs).every((p) => p in data.pack_ids)).toBe(true);
  expect(parseThemePacks("")).toEqual({ packs: {}, pack_ids: {}, default_plan: { weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" } });
});

test("loading leaves a gift list with a wrong shape to the schema check", () => {
  const file = structuredClone(cases.valid) as unknown as { gift_lists: Record<string, unknown>[] };
  file.gift_lists[0].want = ["x"];
  file.gift_lists[0].gorder = [];
  const { data, unknown } = parseSettings(JSON.stringify(file));
  expect(unknown).toBe(0);
  expect(validate(data).map((p) => p.text.split(": ")[0]).sort()).toEqual(["gift_lists/0/gorder", "gift_lists/0/want/0"]);
});

test("loading drops gift ids no data file has, fills gorder and counts them", () => {
  const file = structuredClone(cases.valid) as unknown as { gift_lists: { want: number[]; keep: number[]; gorder: Record<string, number[]> }[] };
  file.gift_lists[0].want = [9053, 424242];
  file.gift_lists[0].keep = [9071, 5];
  const { data, migrated, unknown } = parseSettings(JSON.stringify(file));
  expect(migrated).toBe(false);
  expect(unknown).toBe(2);
  expect([data.gift_lists[0].want, data.gift_lists[0].keep]).toEqual([[9053], [9071]]);
  expect(Object.keys(data.gift_lists[0].gorder)).toHaveLength(11); // a keyword the file lacks gets the default order
  expect(validate(data)).toEqual([]);
});

test("version 10 teams that are not objects get no list and stay for the schema check", () => {
  const old = structuredClone(cases.valid10) as unknown as { teams: unknown[] };
  old.teams.unshift([1]);
  const { data } = parseSettings(JSON.stringify(old));
  expect(data.gift_lists).toHaveLength(2); // the two real teams keep different things
  expect(data.teams[0]).toEqual([1]);
  expect(validate(data).some((p) => p.paths[0].startsWith("teams/0"))).toBe(true);
});

test("loading leaves ids below 1 and repeated ids to the schema check", () => {
  const file = structuredClone(cases.valid) as unknown as { gift_lists: { want: number[]; keep: number[]; gorder: Record<string, number[]> }[] };
  file.gift_lists[0].want = [9053, 0];
  file.gift_lists[0].keep = [424242, 424242];
  file.gift_lists[0].gorder = { Burn: [-3] };
  const { data, unknown } = parseSettings(JSON.stringify(file));
  expect(unknown).toBe(0);
  expect(validate(data).map((p) => p.text.split(": ")[0]).sort()).toEqual(["gift_lists/0/gorder/Burn/0", "gift_lists/0/keep", "gift_lists/0/want/1"]);
});
