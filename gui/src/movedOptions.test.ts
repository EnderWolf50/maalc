// What a version 20 file's moved values are once they sit in the client (#782): the shared cases' list
// (tests/settings_cases.json migrate_v20 moved), then how the window says each one.
import { describe, expect, test } from "vitest";
import cases from "../../tests/settings_cases.json";
import { movedOptions, sayMoved } from "./movedOptions";
import { newTeam, type Team } from "./model";

type Edit = { set: string; value: unknown } | { delete: string };

/** The edit format of tests/settings_cases.json (validate.test.ts reads it the same way). */
function applyEdits(data: unknown, edits: Edit[]) {
  const out = structuredClone(data) as Record<string, unknown>;
  for (const edit of edits) {
    const parts = ("set" in edit ? edit.set : edit.delete).split("/");
    const last = parts.pop()!;
    let node = out as Record<string, unknown>;
    for (const key of parts) node = node[key] as Record<string, unknown>;
    if (!("set" in edit)) delete node[last];
    else node[last] = edit.value;
  }
  return out;
}

const v20 = (edits: Edit[]) => applyEdits({ ...cases.valid, version: 20, ...cases.v20 }, edits);
const pairs = (old: Record<string, unknown>) => movedOptions(old).map((m) => `${m.option}=${m.value}`);

describe("tests/settings_cases.json migrate_v20: the values off the client's default, as the client option to set", () => {
  for (const c of cases.migrate_v20 as { name: string; edits: Edit[]; moved: string[] }[]) {
    test(c.name, () => expect(pairs(v20(c.edits))).toEqual(c.moved));
  }
});

test("a file with no moved section has nothing to list", () => {
  expect(movedOptions({ ...cases.valid })).toEqual([]);
});

describe("how the window says each one: the client's task, the option's name and the value in the window's language", () => {
  const teams: Team[] = [{ ...newTeam(3, "Alpha"), id: "a" }];
  const say = (option: string, value: string, lang: "zh_tw" | "en_us" = "zh_tw") => sayMoved([{ option, value }], teams, lang)[0];

  test("a select by its case's name, the client's own words", () => {
    expect(say("MirrorTargetFloor", "15")).toEqual({ task: "鏡牢", option: "目標層數", value: "15 層（極限）" });
    expect(say("MirrorTargetFloor", "15", "en_us")).toEqual({ task: "Mirror Dungeon", option: "Target floor", value: "15 floors (EXTREME)" });
  });

  test("a switch as on or off, a nested input under its task", () => {
    expect(say("AutoDownload", "No")).toEqual({ task: "全域選項", option: "自動接受下載與更新", value: "關" });
    expect(say("MirrorRunsLimit", "No", "en_us").value).toBe("Off");
    expect(say("ThreadCount", "5")).toEqual({ task: "紐本", option: "這次要打贏的場數", value: "5" });
  });

  test("the webhook only as set, never its address", () => {
    expect(say("WebhookUrl", "(set)")).toEqual({ task: "全域選項", option: "失敗通知 webhook", value: "有設定" });
    expect(say("WebhookUrl", "(set)", "en_us").value).toBe("set");
  });

  test("a team by its name and slot, as the dropdown shows it; a team since deleted by its id", () => {
    expect(say("ExpTeam", "a")).toEqual({ task: "經驗本", option: "隊伍", value: "Alpha（TEAMS #3）" });
    expect(say("ThreadTeam", "gone", "en_us")).toEqual({ task: "Thread Luxcavation", option: "Team", value: "gone" });
  });
});
