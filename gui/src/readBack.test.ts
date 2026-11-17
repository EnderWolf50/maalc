// The one-time read-back of a v1.0.0 install's values when the window migrates its settings file to version 23 (#814, spec
// #811 "設定檔（版本 23）"): MXU's config/mxu-maalc.json first, else config/settings.v20.json, else the defaults.
import { describe, expect, test } from "vitest";
import { newSections, parseSettings, type Settings } from "./model";
import { readBack, type ReadBackFiles } from "./readBack";
import { olderFile } from "./settingsCases";

/** A version 22 file (teams a and b) as the window holds it after its migration. */
const migrated = (version: 20 | 21 | 22 = 22, edits: Parameters<typeof olderFile>[1] = []) =>
  parseSettings(JSON.stringify(olderFile(version, edits))).data;
const none: ReadBackFiles = { mxu: null, teamOptions: null, v20: null };

type Option = Record<string, unknown>;
const select = (caseName: string): Option => ({ type: "select", caseName });
const toggle = (value: unknown): Option => ({ type: "switch", value });
const input = (values: Record<string, string>, encryptedValues?: Record<string, string>): Option =>
  ({ type: "input", values, ...(encryptedValues ? { encryptedValues } : {}) });
type Task = { taskName: string; enabled?: boolean; enabledByController?: Record<string, boolean>; optionValues?: Record<string, Option> };
/** MXU v2.7.1's config file (types/config.ts MxuConfig) with these tasks in its last used instance, which a closed one
 * listed before it does not change. */
function mxu(tasks: Task[], globals: Record<string, Option> = {}, device = "127.0.0.1:16416") {
  return JSON.stringify({
    version: "1.0",
    instances: [
      { id: "i0", name: "Old", controllerName: "MuMu", tasks: [{ id: "x", taskName: "ClaimMail", enabled: true, optionValues: {} }] },
      {
        id: "i1", name: "Main", controllerName: "MuMu", resourceName: "base",
        savedDevice: { adbDeviceName: "MuMu", adbDeviceAddress: device },
        tasks: tasks.map((t, i) => ({ id: `t${i}`, enabled: false, optionValues: {}, ...t })),
      },
    ],
    globalOptionValues: globals, settings: {}, lastActiveInstanceId: "i1",
  });
}

describe("from MXU's config file", () => {
  const files = (text: string): ReadBackFiles => ({ ...none, mxu: text });

  test("each option value maps back to its settings key, each team by its id; the ticks, order and address come along", () => {
    const text = mxu([
      { taskName: "ExpLuxcavation", enabled: true, optionValues: {
        ExpMode: select("count"), ExpCount: input({ count: "2" }), ExpTeam: select("a"), ExpRetries: input({ retries: "1" }),
        ExpConsecutive: toggle(false),
      } },
      { taskName: "ClaimMail", enabled: true },
      { taskName: "MirrorDungeon", enabled: true, optionValues: {
        MirrorDifficulty: select("hard"), MirrorTargetFloor: select("10"), MirrorRunsLimit: toggle(false),
        MirrorRuns: input({ runs: "4" }), MirrorThemePackRefresh: select("once"), MirrorWeeklyBonusUse: select("none"),
        MirrorWeeklyBonusAmount: select("one"), MirrorStopWhenBonusOut: toggle(true), MirrorStarlightUnaffordable: select("stop"),
        MirrorWipeRetries: input({ wipe_retries: "3" }), MirrorAfterRetries: select("stop"), MirrorStartTeam: select("b"),
      } },
      { taskName: "AssembleModules", enabled: false },
      { taskName: "ThreadLuxcavation", enabled: true, optionValues: {
        ThreadMode: select("daily"), ThreadTeam: select("none"), ThreadRetries: input({ retries: "0" }), ThreadConsecutive: toggle(true),
      } },
      { taskName: "ChargeEnkephalin", enabled: true, optionValues: { ChargeCount: input({ count: "4" }) } },
    ], {
      WebhookUrl: input({ url: "" }), AutoAcceptTerms: toggle(false), AutoDownload: toggle(true), KeepDismissedScreens: toggle(false),
    });
    const { data, report } = readBack(migrated(), 22, files(text));
    expect(data.run).toEqual({
      difficulty: "hard", target_floor: 10, runs: null, weekly_bonus_use: "none", weekly_bonus_amount: "one",
      stop_when_weekly_bonus_out: true, starlight_unaffordable: "stop", wipe_retries: 3, after_retries: "stop", webhook_url: "",
      theme_pack_refresh: "once", auto_accept_terms: false, auto_download: true, keep_dismissed_screens: false, start_team: "b",
    });
    expect(data.luxcavation).toEqual({
      exp: { mode: "count", count: 2, team: "a", retries: 1, consecutive: false },
      thread: { mode: "daily", count: 3, team: null, retries: 0, consecutive: true },
    });
    expect(data.charge_enkephalin).toEqual({ count: 4 });
    // MXU's order; a task MXU did not list goes last, unticked
    expect(data.tasks).toEqual([
      { id: "ExpLuxcavation", enabled: true }, { id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true },
      { id: "AssembleModules", enabled: false }, { id: "ThreadLuxcavation", enabled: true }, { id: "ChargeEnkephalin", enabled: true },
      { id: "ClaimPassMissions", enabled: false },
    ]);
    expect(data.emulator).toEqual({ address: "127.0.0.1:16416", mumu_index: null, mumu_manager: null });
    expect(report).toMatchObject({ from: 22, source: "mxu", instance: "Main", instances: 2, problems: [], missed: [] });
    expect(report.tasks).toEqual(data.tasks);
    expect(report.address).toBe("127.0.0.1:16416");
    // what the notice lists as read: each value off its default, in the tab's order
    expect(report.read.map((r) => r.path)).toEqual([
      "run/difficulty", "run/target_floor", "run/runs", "run/theme_pack_refresh", "run/start_team", "run/weekly_bonus_use",
      "run/weekly_bonus_amount", "run/stop_when_weekly_bonus_out", "run/starlight_unaffordable", "run/wipe_retries",
      "run/after_retries", "luxcavation/exp/mode", "luxcavation/exp/count", "luxcavation/exp/team", "luxcavation/exp/retries",
      "luxcavation/exp/consecutive", "charge_enkephalin/count", "run/auto_accept_terms", "run/keep_dismissed_screens",
    ]);
    expect(report.read.find((r) => r.path === "run/start_team")!.value).toBe("b");
    // read too, at their defaults: Thread Luxcavation's mode, team, retries and Consecutive Battle, and AutoDownload
    expect(report.same).toBe(5);
    expect(report.absent).toEqual(["team_options.json", "settings.v20.json"]);
  });

  test("a tick MXU keeps for the controller wins over the plain one; the runs come from MirrorRuns while the limit is on", () => {
    const text = mxu([
      { taskName: "MirrorDungeon", enabled: false, enabledByController: { MuMu: true }, optionValues: {
        MirrorRunsLimit: toggle(true), MirrorRuns: input({ runs: "5" }),
      } },
      { taskName: "ClaimMail", enabled: true, enabledByController: { MuMu: false } },
    ]);
    const { data } = readBack(migrated(), 22, files(text));
    expect(data.tasks.slice(0, 2)).toEqual([{ id: "MirrorDungeon", enabled: true }, { id: "ClaimMail", enabled: false }]);
    expect(data.run.runs).toBe(5);
  });

  test("a value the option does not take stays at its default and is listed with what MXU had", () => {
    const text = mxu([
      { taskName: "MirrorDungeon", enabled: true, optionValues: {
        MirrorDifficulty: select("insane"), MirrorTargetFloor: select("20"), MirrorWipeRetries: input({ wipe_retries: "-1" }),
        MirrorRuns: input({ runs: "0" }),
      } },
      { taskName: "ExpLuxcavation", enabled: true, optionValues: { ExpConsecutive: toggle("yes"), ExpMode: input({ mode: "count" }) } },
      { taskName: "ChargeEnkephalin", enabled: true, optionValues: { ChargeCount: input({ count: "11" }) } },
    ]);
    const { data, report } = readBack(migrated(), 22, files(text));
    expect([data.run.difficulty, data.run.target_floor, data.run.wipe_retries, data.run.runs]).toEqual(["auto", 5, 2, 1]);
    expect([data.luxcavation.exp.consecutive, data.luxcavation.exp.mode, data.charge_enkephalin.count]).toEqual([true, "daily", 0]);
    expect(report.missed).toEqual([
      { kind: "value", path: "run/difficulty", value: "insane" },
      { kind: "value", path: "run/target_floor", value: "20" },
      // an input's value as its text; an option of another type than v1.0.0's as what MXU stored
      { kind: "value", path: "run/runs", value: "0" },
      { kind: "value", path: "run/wipe_retries", value: "-1" },
      { kind: "value", path: "luxcavation/exp/mode", value: '{"mode":"count"}' },
      { kind: "value", path: "luxcavation/exp/consecutive", value: "yes" },
      { kind: "value", path: "charge_enkephalin/count", value: "11" },
    ]);
    expect(report.read).toEqual([]);
  });

  test("a team deleted since picks none and is listed by the name the team options file gave it", () => {
    const text = mxu([
      { taskName: "MirrorDungeon", enabled: true, optionValues: { MirrorStartTeam: select("gone") } },
      { taskName: "ExpLuxcavation", enabled: true, optionValues: { ExpTeam: select("lost") } },
      { taskName: "ThreadLuxcavation", enabled: true, optionValues: { ThreadTeam: select("queue") } },
    ]);
    const teamOptions = JSON.stringify({ option: { MirrorStartTeam: { cases: [
      { name: "queue", label: "$MirrorStartTeam_queue" }, { name: "gone", label: "Old team（TEAMS #3）（已刪除）" },
    ] } } });
    const { data, report } = readBack(migrated(), 22, { ...files(text), teamOptions });
    expect([data.run.start_team, data.luxcavation.exp.team, data.luxcavation.thread.team]).toEqual([null, null, null]);
    expect(report.missed).toEqual([
      { kind: "team", path: "run/start_team", id: "gone", label: "Old team（TEAMS #3）" },
      { kind: "team", path: "luxcavation/exp/team", id: "lost", label: null },
    ]);
  });

  test("an encrypted webhook does not come back and is listed; one MXU kept as plain text does", () => {
    const sealed = mxu([], { WebhookUrl: input({ url: "" }, { url: "c2VjcmV0" }) });
    const a = readBack(migrated(), 22, files(sealed));
    expect(a.data.run.webhook_url).toBe("");
    expect(a.report.missed).toEqual([{ kind: "webhook" }]);
    const plain = mxu([], { WebhookUrl: input({ url: "https://hook.invalid/x" }) });
    const b = readBack(migrated(), 22, files(plain));
    expect(b.data.run.webhook_url).toBe("https://hook.invalid/x");
    expect(b.report.missed).toEqual([]);
    expect(b.report.read).toEqual([{ path: "run/webhook_url", value: "https://hook.invalid/x" }]);
  });

  test("each entry of a task MXU lists twice stays an entry with its own tick, in MXU's order; one maalc lacks is listed (#811)", () => {
    const text = mxu([
      { taskName: "AssembleModules", enabled: true },
      { taskName: "ExpLuxcavation", enabled: false },
      { taskName: "Gone", enabled: true },
      { taskName: "AssembleModules", enabled: false },
      { taskName: "ClaimMail", enabled: true },
    ]);
    const { data, report } = readBack(migrated(), 22, files(text));
    // the tasks MXU did not list go last, unticked, once each in a new file's order
    expect(data.tasks).toEqual([
      { id: "AssembleModules", enabled: true }, { id: "ExpLuxcavation", enabled: false }, { id: "AssembleModules", enabled: false },
      { id: "ClaimMail", enabled: true }, { id: "ChargeEnkephalin", enabled: false }, { id: "ThreadLuxcavation", enabled: false },
      { id: "ClaimPassMissions", enabled: false }, { id: "MirrorDungeon", enabled: false },
    ]);
    expect(report.tasks).toEqual(data.tasks);
    expect(report.missed).toEqual([{ kind: "task", name: "Gone" }]); // the two Assemble Modules have no options to differ
  });

  test("a task's options come from its first ticked entry, else its first; copies whose options differ are named", () => {
    const text = mxu([
      { taskName: "ExpLuxcavation", enabled: false, optionValues: { ExpRetries: input({ retries: "4" }) } },
      { taskName: "ExpLuxcavation", enabled: true, optionValues: { ExpRetries: input({ retries: "2" }) } },
      { taskName: "ThreadLuxcavation", enabled: false, optionValues: { ThreadRetries: input({ retries: "3" }) } },
      { taskName: "ThreadLuxcavation", enabled: false, optionValues: { ThreadRetries: input({ retries: "1" }) } },
      // the same values (keys in another order) and an option maalc does not read: nothing to name
      { taskName: "MirrorDungeon", enabled: true, optionValues: { MirrorDifficulty: select("hard"), MirrorRuns: input({ runs: "2" }) } },
      { taskName: "MirrorDungeon", enabled: true, optionValues: {
        MirrorRuns: { values: { runs: "2" }, type: "input" }, MirrorDifficulty: select("hard"), MirrorOld: select("x"),
      } },
    ]);
    const { data, report } = readBack(migrated(), 22, files(text));
    expect([data.luxcavation.exp.retries, data.luxcavation.thread.retries, data.run.difficulty]).toEqual([2, 3, "hard"]);
    expect(data.tasks.slice(0, 6).map((x) => x.enabled)).toEqual([false, true, false, false, true, true]);
    expect(report.missed).toEqual([
      { kind: "differ", task: "ExpLuxcavation", n: 2 }, { kind: "differ", task: "ThreadLuxcavation", n: 2 },
    ]);
  });

  test("MXU's file is read the same for a version 21 file", () => {
    const text = mxu([{ taskName: "MirrorDungeon", enabled: true, optionValues: { MirrorDifficulty: select("normal") } }]);
    const { data, report } = readBack(migrated(21), 21, files(text));
    expect([data.run.difficulty, report.from, report.source]).toEqual(["normal", 21, "mxu"]);
  });

  test("a file that does not parse, or has no instance, is said so; settings.v20.json comes next", () => {
    const v20 = JSON.stringify(olderFile(20, [{ set: "run/difficulty", value: "hard" }]));
    for (const [text, why] of [["{oops", /^mxu-maalc\.json: .*JSON/], [JSON.stringify({ instances: [] }), /^mxu-maalc\.json: no instance$/]] as const) {
      const { data, report } = readBack(migrated(), 22, { ...none, mxu: text, v20 });
      expect([data.run.difficulty, report.source, report.instance, report.tasks]).toEqual(["hard", "v20", null, null]);
      expect(report.problems).toEqual([expect.stringMatching(why)]);
    }
  });
});

describe("without MXU's file", () => {
  test("settings.v20.json's run options come back, a team deleted since and a value broken by hand listed", () => {
    const v20 = JSON.stringify(olderFile(20, [
      { set: "run/difficulty", value: "hard" }, { set: "run/runs", value: null }, { set: "run/wipe_retries", value: -1 },
      { set: "run/webhook_url", value: "https://hook.invalid/y" },
      { set: "luxcavation/exp/team", value: "a" }, { set: "luxcavation/thread/team", value: "gone" },
      { set: "charge_enkephalin/count", value: 2 },
    ]));
    const { data, report } = readBack(migrated(), 22, { ...none, v20 });
    expect([data.run.difficulty, data.run.runs, data.run.wipe_retries, data.run.webhook_url, data.run.start_team])
      .toEqual(["hard", null, 2, "https://hook.invalid/y", null]);
    expect([data.luxcavation.exp.team, data.luxcavation.thread.team, data.charge_enkephalin.count]).toEqual(["a", null, 2]);
    expect(data.tasks).toEqual(newSections().tasks); // v1.0.0's task list was MXU's: every task, none ticked
    expect(data.emulator.address).toBeNull();
    expect(report).toMatchObject({ source: "v20", instance: null, tasks: null, address: null, problems: [] });
    expect(report.missed).toEqual([
      { kind: "value", path: "run/wipe_retries", value: "-1" },
      { kind: "team", path: "luxcavation/thread/team", id: "gone", label: null },
    ]);
    expect(report.read.map((r) => r.path)).toEqual([
      "run/difficulty", "run/runs", "luxcavation/exp/team", "charge_enkephalin/count", "run/webhook_url",
    ]);
  });

  test("with neither file the task options stay at their defaults and nothing is listed", () => {
    const { data, report } = readBack(migrated(), 22, none);
    expect(data.run).toEqual(newSections().run);
    expect(report).toEqual({
      from: 22, source: "defaults", instance: null, instances: 0, problems: [], read: [], same: 0,
      absent: ["mxu-maalc.json", "team_options.json", "settings.v20.json"], tasks: null, address: null, missed: [],
    });
  });

  test("a file that cannot be read is said so, and the next one is tried", () => {
    const v20 = JSON.stringify(olderFile(20, [{ set: "run/target_floor", value: 15 }]));
    const { data, report } = readBack(migrated(), 22, { ...none, mxu: { error: "access denied" }, v20 });
    expect([data.run.target_floor, report.source, report.problems]).toEqual([15, "v20", ["mxu-maalc.json: access denied"]]);
  });
});

test("a version 20 file keeps its own run options; MXU's file gives it the task list and the address alone", () => {
  const file = migrated(20, [{ set: "run/difficulty", value: "hard" }]);
  const text = mxu([{ taskName: "ClaimMail", enabled: true, optionValues: {} }, {
    taskName: "MirrorDungeon", enabled: true, optionValues: { MirrorDifficulty: select("normal"), MirrorTargetFloor: select("10") },
  }]);
  const v20 = JSON.stringify(olderFile(20, [{ set: "run/difficulty", value: "normal" }]));
  const { data, report } = readBack(file, 20, { ...none, mxu: text, v20 });
  expect([data.run.difficulty, data.run.target_floor]).toEqual(["hard", 5]);
  expect(data.tasks.slice(0, 2)).toEqual([{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true }]);
  expect(data.emulator.address).toBe("127.0.0.1:16416");
  expect(report).toMatchObject({ from: 20, source: "file", instance: "Main", missed: [] });
  expect(report.read).toEqual([{ path: "run/difficulty", value: "hard" }]);
});

test("the defaults it starts from are a new file's", () => {
  const { data } = readBack(migrated(), 22, none);
  const fresh: Partial<Settings> = newSections();
  for (const k of ["run", "luxcavation", "charge_enkephalin", "tasks", "emulator"] as const) expect(data[k]).toEqual(fresh[k]);
});
