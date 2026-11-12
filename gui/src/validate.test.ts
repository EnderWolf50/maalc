// Runs tests/settings_cases.json, which tests/test_settings.py runs against agent/settings.py too.
import { describe, expect, test } from "vitest";
import cases from "../../tests/settings_cases.json";
import themePacksYaml from "../../assets/resource/base/data/theme_packs.yaml?raw";
import {
  MIGRATIONS, OLDEST_VERSION, SKILL_SWAPS, VERSION, cleanGiftList, newSettings, newTeam, parseSettings, parseThemePacks, schema,
  skillPlan, type GiftList,
} from "./model";
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

test("parseSettings refuses a newer version", () => {
  expect(() => parseSettings('{"version": 21}')).toThrow("newer");
});

test.each(cases.too_old)("parseSettings refuses version $version as too old, in the agent's words (tests/settings_cases.json too_old)", ({ version, error }) => {
  expect(() => parseSettings(JSON.stringify({ ...cases.valid, version }))).toThrow(new Error(error));
});

test("every version from the oldest has its migration", () => {
  expect(Object.keys(MIGRATIONS).map(Number)).toEqual(Array.from({ length: VERSION - OLDEST_VERSION }, (_, i) => OLDEST_VERSION + i));
});

/** A team's skill replacement as a new team has it: no sinner listed, so every deck stays 3/2/1; ID Skill Search off, paid in Cost. */
const DEFAULT_SKILLS = cases.skill_replacement_default;

test("a new team lists no sinner to replace (#454), and the swaps are data/shop.yaml's three", () => {
  expect(newTeam(1, "隊伍 1").skill_replacement).toEqual(DEFAULT_SKILLS);
  expect(newTeam(1, "a").skill_replacement.sinners).not.toBe(newTeam(2, "b").skill_replacement.sinners);
  expect(schema.$defs.skill_sinner.properties.s1_s3_first.default).toBe(true);
  expect(SKILL_SWAPS).toEqual({
    s1_s3: { from: 1, to: 3, shop: 120, id_search: { cost: 240, starlight: 75 } },
    s2_s3: { from: 2, to: 3, shop: 75, id_search: { cost: 150, starlight: 50 } },
    s1_s2: { from: 1, to: 2, shop: 45, id_search: { cost: 90, starlight: 25 } },
  });
});

describe("a skill target (#264's rule: a swap a→b counts only while skill a is above its target and skill b below it)", () => {
  const t = (s1: number, s2: number, s3: number) => ({ s1, s2, s3 });
  test("3/2/1 is the game's deck: nothing to do", () => {
    expect(skillPlan(t(3, 2, 1))).toEqual({ untouched: true, faults: [], need: [] });
  });
  test.each([
    [t(2, 2, 2), [{ key: "s1_s3", n: 1 }]],
    [t(2, 3, 1), [{ key: "s1_s2", n: 1 }]],
    [t(3, 0, 3), [{ key: "s2_s3", n: 2 }]],
    // S2 above 2: S1→S2 for S2, S1→S3 for S3
    [t(1, 3, 2), [{ key: "s1_s2", n: 1 }, { key: "s1_s3", n: 1 }]],
    [t(0, 5, 1), [{ key: "s1_s2", n: 3 }]],
    // S2 at 2 or below: S2→S3 for S2, S1→S3 for S1
    [t(2, 1, 3), [{ key: "s2_s3", n: 1 }, { key: "s1_s3", n: 1 }]],
    [t(0, 0, 6), [{ key: "s2_s3", n: 2 }, { key: "s1_s3", n: 3 }]],
  ])("%o needs %o", (target, need) => {
    expect(skillPlan(target)).toEqual({ untouched: false, faults: [], need });
  });
  test.each([
    [t(3, 2, 2), ["total"]],
    [t(4, 1, 1), ["s1"]],
    [t(3, 3, 0), ["s3"]],
    [t(5, 2, 0), ["total", "s1", "s3"]],
    // the schema rejects these; a hand-edited file still opens in the editor with them
    [t(3, -1, 4), ["range"]],
    [t(2.5, 2, 1.5), ["range"]],
  ])("%o cannot be reached: %o, and needs no swap", (target, faults) => {
    expect(skillPlan(target)).toEqual({ untouched: false, faults, need: [] });
  });
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
  expect(data.packs["Walpurgis Night: Hatred and Despair"]).toEqual({ N: [3, 4], H: [3, 4] });
  // the BokGak re-runs are packs of their own, on HARD floors 4-5 and INFINITY, weighed as their originals
  expect(data.packs["Miracle in District 20 BokGak"]).toEqual({ H: [4, 5], I: true });
  expect(data.packs["Chachihu"]).toEqual({ X: true }); // #387: an EXTREME-only pack
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

test("loading leaves ids below 1 and repeated ids to the schema check", () => {
  const file = structuredClone(cases.valid) as unknown as { gift_lists: { want: number[]; keep: number[]; gorder: Record<string, number[]> }[] };
  file.gift_lists[0].want = [9053, 0];
  file.gift_lists[0].keep = [424242, 424242];
  file.gift_lists[0].gorder = { Burn: [-3] };
  const { data, unknown } = parseSettings(JSON.stringify(file));
  expect(unknown).toBe(0);
  expect(validate(data).map((p) => p.text.split(": ")[0]).sort()).toEqual(["gift_lists/0/gorder/Burn/0", "gift_lists/0/keep", "gift_lists/0/want/1"]);
});
