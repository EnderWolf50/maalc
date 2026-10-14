// Runs tests/settings_cases.json, which tests/test_settings.py runs against agent/settings.py too.
import { describe, expect, test } from "vitest";
import cases from "../../tests/settings_cases.json";
import { newSettings, newTeam, parseSettings } from "./model";
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
  expect(() => parseSettings('{"version": 2}')).toThrow("newer");
  expect(() => parseSettings('{"version": 0}')).toThrow("cannot be migrated");
});
