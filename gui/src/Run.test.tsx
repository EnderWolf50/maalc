// The Run tab (#814, spec #811 「設定視窗」): the task list with its ticks and order, the picked task's options, the global
// options and the emulator's fields, each written to the settings key the runner and the agent read.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import taskOptionsPy from "../../agent/task_options.py?raw";
import { TABS } from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam, type Settings } from "./model";
import { dragOnto, expectLines, queuedTeams, renderEditor } from "./testing";
import { GLOBAL_KEYS } from "./Run";
import { useEditor } from "./ui";

const zh = TEXT.zh_tw;
const RunTab = TABS.find((tab) => tab[0] === "run")![2];
const list = () => within(document.querySelector(".task-list")!);
const rows = () => list().getAllByRole("listitem");
const ids = (s: Settings) => s.tasks.map((x) => x.id);
const tick = (name: string) => screen.getByRole("checkbox", { name: fill(zh["tasks.tick"], { name }) });
/** The tick of a task's nth entry (from 1), a task listed more than once. */
const nthTick = (name: string, n: number) => screen.getByRole("checkbox", { name: fill(zh["tasks.tick_nth"], { name, n }) });
const again = (name: string) => screen.getByRole("button", { name: fill(zh["tasks.again"], { name }) });
/** Show the options of the task named `name`, listed once, as the user clicks its row. */
const show = (r: ReturnType<typeof renderEditor>, name: string) => r.user.click(list().getByText(name));

test("the global options the tab shows are the run keys every task reads in the agent (agent/task_options.py GLOBAL)", () => {
  const tuple = /^GLOBAL = \(([^)]*)\)/m.exec(taskOptionsPy)?.[1] ?? "";
  const agent = [...tuple.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  expect(agent).toEqual([...GLOBAL_KEYS]);
});

describe("the task list", () => {
  test("a new file lists the README's suggested order, Assemble Modules before and after the Luxcavations, none ticked (#811)", () => {
    renderEditor(<RunTab />, newSettings());
    // README 建議順序: 換腦啡肽模組 → 經驗本 → 紐本 → 換腦啡肽模組 → 領通行證任務 → 領信 → 鏡牢; the Lunacy charge before the first assembly
    expect(rows().map((x) => x.textContent)).toEqual([
      "狂氣換腦啡肽", "換腦啡肽模組", "經驗本", "紐本", "換腦啡肽模組", "領通行證任務", "領信", "鏡牢",
    ].map((name) => expect.stringContaining(name)));
    for (const box of list().getAllByRole("checkbox")) expect(box).not.toBeChecked();
  });

  test("lists the file's tasks in its order with their ticks; a tick is saved", async () => {
    const s = newSettings();
    s.tasks = [{ id: "ClaimMail", enabled: true }, ...s.tasks.filter((x) => x.id !== "ClaimMail")];
    const r = renderEditor(<RunTab />, s);
    expect(rows()[0]).toHaveTextContent("領信");
    expect(tick("領信")).toBeChecked();
    expect(tick("鏡牢")).not.toBeChecked();
    await r.user.click(tick("鏡牢"));
    expect(r.settings().tasks[7]).toEqual({ id: "MirrorDungeon", enabled: true });
    await r.user.click(tick("領信"));
    expect(r.settings().tasks[0]).toEqual({ id: "ClaimMail", enabled: false });
  });

  test("each entry of a task listed twice has its own tick, named by its place among them", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    expect(screen.queryByRole("checkbox", { name: fill(zh["tasks.tick"], { name: "換腦啡肽模組" }) })).toBeNull();
    await r.user.click(nthTick("換腦啡肽模組", 2));
    expect(r.settings().tasks.filter((x) => x.id === "AssembleModules")).toEqual([
      { id: "AssembleModules", enabled: false }, { id: "AssembleModules", enabled: true },
    ]);
    expect(r.settings().tasks[4]).toEqual({ id: "AssembleModules", enabled: true });
    expect(nthTick("換腦啡肽模組", 1)).not.toBeChecked();
  });

  test("a tick's hit area is larger than its box, and a click there leaves the picked task as it is", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    const area = tick("領信").closest("label")!;
    expect(area).toHaveClass("tick");
    await r.user.click(area); // beside the box, inside its area
    expect(r.settings().tasks.find((x) => x.id === "ClaimMail")!.enabled).toBe(true);
    expect(screen.getByRole("heading", { name: /狂氣換腦啡肽.*ChargeEnkephalin/ })).toBeVisible();
    await r.user.click(tick("領信"));
    expect(r.settings().tasks.find((x) => x.id === "ClaimMail")!.enabled).toBe(false);
    expect(rows()[0]).toHaveAttribute("aria-current", "true");
  });

  test("↑↓ and a drag change the run order, ticks moving with their tasks", async () => {
    const s = newSettings();
    s.tasks[0].enabled = true; // ChargeEnkephalin
    const r = renderEditor(<RunTab />, s);
    await r.user.click(within(rows()[0]).getByRole("button", { name: zh.down }));
    expect(ids(r.settings()).slice(0, 2)).toEqual(["AssembleModules", "ChargeEnkephalin"]);
    await r.user.click(within(rows()[7]).getByRole("button", { name: zh.up }));
    expect(ids(r.settings()).slice(6)).toEqual(["MirrorDungeon", "ClaimMail"]);
    dragOnto(rows()[1], rows()[7]);
    expect(r.settings().tasks).toEqual([
      { id: "AssembleModules", enabled: false }, { id: "ExpLuxcavation", enabled: false }, { id: "ThreadLuxcavation", enabled: false },
      { id: "AssembleModules", enabled: false }, { id: "ClaimPassMissions", enabled: false }, { id: "MirrorDungeon", enabled: false },
      { id: "ClaimMail", enabled: false }, { id: "ChargeEnkephalin", enabled: true },
    ]);
  });

  test("a click on a task shows its options with its task id; a task without options says so", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    // the first task shows at the start: the agent's stop lines name a task by its id ("the MirrorDungeon task")
    expect(screen.getByRole("heading", { name: /狂氣換腦啡肽.*ChargeEnkephalin/ })).toBeVisible();
    await r.user.click(within(rows()[6]).getByText("領信"));
    expect(screen.getByRole("heading", { name: /領信.*ClaimMail/ })).toBeVisible();
    expect(screen.getByText(zh["tasks.none"])).toBeVisible();
    expect(rows()[6]).toHaveAttribute("aria-current", "true");
  });

  test("either entry of a task listed twice shows that task's options and stays picked, also when it moves", async () => {
    const s = newSettings();
    s.tasks.push({ id: "MirrorDungeon", enabled: false });
    const r = renderEditor(<RunTab />, s);
    await r.user.click(within(rows()[8]).getByText("鏡牢"));
    expect(rows()[8]).toHaveAttribute("aria-current", "true");
    expect(rows()[7]).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("heading", { name: /鏡牢.*MirrorDungeon/ })).toBeVisible();
    expect(screen.getByText(fill(zh["tasks.entries"], { n: 2 }))).toBeVisible();
    // both entries read the task's one set of options
    await r.user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) }), "hard");
    expect(r.settings().run.difficulty).toBe("hard");
    // the second entry moved above the first stays the one picked
    await r.user.click(within(rows()[8]).getByRole("button", { name: zh.up }));
    expect(rows()[7]).toHaveAttribute("aria-current", "true");
    expect(rows()[8]).not.toHaveAttribute("aria-current");
    await r.user.click(within(rows()[1]).getByText("換腦啡肽模組"));
    expect(screen.getByText(fill(zh["tasks.entries"], { n: 2 }))).toBeVisible();
    await r.user.click(within(rows()[6]).getByText("領信"));
    expect(screen.queryByText(fill(zh["tasks.entries"], { n: 2 }))).toBeNull();
  });

  test("再加一次 lists the picked task once more, unticked, right after it, and picks it; an extra entry can be removed, a task's last one not", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await r.user.click(within(rows()[7]).getByText("鏡牢"));
    expect(screen.queryByRole("button", { name: zh["tasks.remove"] })).toBeNull(); // the task's only entry
    await r.user.click(again("鏡牢"));
    expect(ids(r.settings()).slice(6)).toEqual(["ClaimMail", "MirrorDungeon", "MirrorDungeon"]);
    expect(r.settings().tasks[8]).toEqual({ id: "MirrorDungeon", enabled: false });
    expect(rows()[8]).toHaveAttribute("aria-current", "true");
    await r.user.click(within(rows()[2]).getByText("經驗本"));
    await r.user.click(again("經驗本"));
    expect(ids(r.settings()).slice(2, 5)).toEqual(["ExpLuxcavation", "ExpLuxcavation", "ThreadLuxcavation"]);
    expect(rows()[3]).toHaveAttribute("aria-current", "true");
    // the picked one goes; the pick stays on the task, on its entry left
    await r.user.click(screen.getByRole("button", { name: zh["tasks.remove"] }));
    expect(ids(r.settings()).filter((id) => id === "ExpLuxcavation")).toHaveLength(1);
    expect(rows()[2]).toHaveAttribute("aria-current", "true");
    expect(screen.queryByRole("button", { name: zh["tasks.remove"] })).toBeNull();
    // a ticked first entry: removing it keeps the extra one with its own tick
    await r.user.click(within(rows()[1]).getByText("換腦啡肽模組"));
    await r.user.click(nthTick("換腦啡肽模組", 1));
    await r.user.click(screen.getByRole("button", { name: zh["tasks.remove"] }));
    expect(r.settings().tasks.filter((x) => x.id === "AssembleModules")).toEqual([{ id: "AssembleModules", enabled: false }]);
    expect(tick("換腦啡肽模組")).not.toBeChecked();
  });
});

describe("the Mirror Dungeon task's options", () => {
  test("each select writes its run key", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    const picks = [
      ["run.difficulty", "hard", "difficulty"], ["run.theme_pack_refresh", "once", "theme_pack_refresh"],
      ["run.weekly_bonus_use", "none", "weekly_bonus_use"], ["run.weekly_bonus_amount", "one", "weekly_bonus_amount"],
      ["run.starlight_unaffordable", "stop", "starlight_unaffordable"], ["run.after_retries", "stop", "after_retries"],
    ] as const;
    for (const [label, value, key] of picks) {
      await r.user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh[label]}`) }), value);
      expect(r.settings().run[key]).toBe(value);
    }
    await r.user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh["run.target_floor"]}`) }), "15");
    expect(r.settings().run.target_floor).toBe(15);
    expect(screen.getByText(zh["run.target_floor_note"])).toBeVisible();
    expect(screen.getByText(zh["run.target_floor_entry_note"])).toBeVisible();
  });

  test("the run limit is a switch with its number, off for no limit; the wipe retries a number; the stop a switch", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    const limit = screen.getByRole("checkbox", { name: zh["run.runs"] });
    expect(limit).toBeChecked();
    fireEvent.change(within(limit.closest(".toggle") as HTMLElement).getByRole("spinbutton"), { target: { value: "3" } });
    expect(r.settings().run.runs).toBe(3);
    await r.user.click(limit);
    expect(r.settings().run.runs).toBeNull();
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["run.wipe_retries"] }), { target: { value: "5" } });
    expect(r.settings().run.wipe_retries).toBe(5);
    await r.user.click(screen.getByRole("checkbox", { name: zh["run.stop_when_weekly_bonus_out"] }));
    expect(r.settings().run.stop_when_weekly_bonus_out).toBe(true);
  });
});

describe("the team pick lists", () => {
  const two = () => {
    const s = newSettings();
    Object.assign(s, queuedTeams([newTeam(1, "Ta"), newTeam(2, "Tb")]));
    s.teams[1].enabled = false;
    return s;
  };
  const startTeam = () => screen.getByRole("combobox", { name: new RegExp(`^${zh["run.start_team"]}`) }) as HTMLSelectElement;
  const optionsOf = (el: HTMLSelectElement) => [...el.options].map((o) => o.textContent);

  test("the start team lists the settings' teams after 照隊伍佇列, a disabled one marked; a pick writes its id, 照隊伍佇列 null", async () => {
    const s = two();
    const r = renderEditor(<RunTab />, s);
    await show(r, "鏡牢");
    expect(optionsOf(startTeam())).toEqual(["照隊伍佇列", "Ta（TEAMS #1）", "Tb（TEAMS #2，停用）"]);
    await r.user.selectOptions(startTeam(), s.teams[0].id);
    expect(r.settings().run.start_team).toBe(s.teams[0].id);
    await r.user.selectOptions(startTeam(), "");
    expect(r.settings().run.start_team).toBeNull();
    await r.user.selectOptions(startTeam(), s.teams[1].id);
    expect(screen.getByText(zh["teamPick.off_note"])).toBeVisible();
  });

  test("a team added or renamed shows at once", async () => {
    const s = two();
    const r = renderEditor(<><RunTab /><Rename /></>, s);
    await show(r, "鏡牢");
    await r.user.click(screen.getByRole("button", { name: "rename and add" }));
    expect(optionsOf(startTeam())).toEqual(["照隊伍佇列", "Renamed（TEAMS #1）", "Tb（TEAMS #2，停用）", "Tc（TEAMS #3）"]);
    await show(r, "經驗本");
    const team = screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) }) as HTMLSelectElement;
    expect(optionsOf(team)).toEqual(["未選擇", "Renamed（TEAMS #1）", "Tb（TEAMS #2）", "Tc（TEAMS #3）"]);
  });

  test("a team deleted since shows as deleted, with why the task will stop", async () => {
    const s = two();
    s.run.start_team = "gone";
    await show(renderEditor(<RunTab />, s), "鏡牢");
    expect(startTeam().value).toBe("gone");
    expect(startTeam().selectedOptions[0].textContent).toBe(fill(zh["teamPick.gone"], { id: "gone" }));
    expect(screen.getByText(zh["teamPick.gone_note"])).toBeVisible();
  });
});

/** Another tab's edit: the first team renamed and a third one added, as the team page does. */
function Rename() {
  const { update } = useEditor();
  return (
    <button type="button" onClick={() => update((d) => {
      d.teams[0].name = "Renamed";
      const team = newTeam(3, "Tc");
      d.teams.push(team);
      d.team_queue.push(team.id);
    })}>rename and add</button>
  );
}

describe("the Luxcavation tasks' and Charge Enkephalin's options", () => {
  test.each([["經驗本", "exp"], ["紐本", "thread"]] as const)("%s's mode, count, team, retries and Consecutive Battle", async (name, task) => {
    const s = newSettings();
    Object.assign(s, queuedTeams([newTeam(1, "Ta")]));
    const r = renderEditor(<RunTab />, s);
    await show(r, name);
    const count = screen.getByRole("spinbutton", { name: new RegExp(zh["lux.count"]) });
    expect(count).toBeDisabled();
    expect(screen.getByText(zh["lux.count_unused"])).toBeVisible();
    await r.user.selectOptions(screen.getByRole("combobox", { name: zh["lux.mode"] }), "count");
    fireEvent.change(count, { target: { value: "6" } });
    await r.user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) }), s.teams[0].id);
    fireEvent.change(screen.getByRole("spinbutton", { name: new RegExp(zh["lux.retries"]) }), { target: { value: "2" } });
    await r.user.click(screen.getByRole("checkbox", { name: zh["lux.consecutive"] }));
    expect(r.settings().luxcavation[task]).toEqual({ mode: "count", count: 6, team: s.teams[0].id, retries: 2, consecutive: false });
    expectLines(zh[`lux.${task}_note`]);
  });

  test("Charge Enkephalin's count, with Lunacy's cost on its note's first line", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "狂氣換腦啡肽");
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["charge.count"] }), { target: { value: "4" } });
    expect(r.settings().charge_enkephalin.count).toBe(4);
    expect(zh["charge.note"].split("\n")[0]).toContain("Lunacy");
    expectLines(zh["charge.note"]);
  });
});

describe("the global options and the emulator", () => {
  test("show whichever task is picked, and write their keys", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "領信");
    await r.user.type(screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) }), "https://hook.invalid/a");
    for (const key of ["auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const) {
      await r.user.click(screen.getByRole("checkbox", { name: zh[`run.${key}`] }));
      expect(r.settings().run[key]).toBe(false);
    }
    expect(r.settings().run.webhook_url).toBe("https://hook.invalid/a");
  });

  test("the address and the MuMu instance, emptied back to none", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    const address = screen.getByRole("textbox", { name: zh["emu.address"] });
    await r.user.type(address, "127.0.0.1:16416");
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }), { target: { value: "1" } });
    expect(r.settings().emulator).toEqual({ address: "127.0.0.1:16416", mumu_index: 1, mumu_manager: null });
    await r.user.clear(address);
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }), { target: { value: "" } });
    expect(r.settings().emulator).toEqual({ address: null, mumu_index: null, mumu_manager: null });
  });

  test("each field shows its settings key beside its label, as the agent's stop lines name it; a screen reader reads the label", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    for (const key of ["run/start_team", "run/difficulty", "run/runs", "run/webhook_url", "emulator/address"]) expect(screen.getByText(key)).toBeVisible();
    expect(screen.getByRole("checkbox", { name: zh["run.auto_download"] })).toBeInTheDocument();
    await show(r, "經驗本");
    for (const key of ["luxcavation/exp/team", "luxcavation/exp/consecutive"]) expect(screen.getByText(key)).toBeVisible();
    // a switch's label and its key are one item of its flex row: apart, the label wrapped a word to a line in the window
    const label = screen.getByRole("checkbox", { name: zh["lux.consecutive"] }).closest("label")!;
    expect([...label.children].map((x) => x.tagName)).toEqual(["INPUT", "SPAN"]);
    expect(label.querySelector(":scope > span")).toHaveTextContent(`${zh["lux.consecutive"]}luxcavation/exp/consecutive`);
  });

  test("the tab's long notes show one topic to a line", async () => {
    await show(renderEditor(<RunTab />, newSettings()), "鏡牢");
    for (const key of ["tasks.note", "run.start_team_note", "emu.note", "run.keep_dismissed_screens_note"] as const) expectLines(zh[key]);
  });
});
