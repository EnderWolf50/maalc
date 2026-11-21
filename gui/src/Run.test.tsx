// The Run tab (#814, spec #811 「設定視窗」): the task list with its ticks and order, the picked task's options, the global
// options and the emulator's fields, each written to the settings key the runner and the agent read.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import taskOptionsPy from "../../agent/task_options.py?raw";
import { TABS } from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam, type Settings } from "./model";
import css from "./index.css?raw";
import { altMove, cssRules, cssValueOf, dragOnto, expectLines, queuedTeams, renderEditor } from "./testing";
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
/** The copy and the ✕ of the row of a task listed once. */
const copy = (name: string) => list().getByRole("button", { name: fill(zh["tasks.copy"], { name }) });
const remove = (name: string) => list().getByRole("button", { name: fill(zh["tasks.delete"], { name }) });
const addButton = () => list().getByRole("button", { name: zh["tasks.add"] });
/** Settings whose task list has Assemble Modules before and after the Luxcavations, a task listed twice, none ticked. */
function assembleTwice() {
  const s = newSettings();
  s.tasks = ["ChargeEnkephalin", "AssembleModules", "ExpLuxcavation", "ThreadLuxcavation", "AssembleModules", "ClaimPassMissions",
    "ClaimMail", "MirrorDungeon"].map((id) => ({ id, enabled: false }));
  return s;
}
/** Show the options of the task named `name`, listed once, as the user clicks its row. */
const show = (r: ReturnType<typeof renderEditor>, name: string) => r.user.click(list().getByText(name));

test("the global options the tab shows are the run keys every task reads in the agent (agent/task_options.py GLOBAL)", () => {
  const tuple = /^GLOBAL = \(([^)]*)\)/m.exec(taskOptionsPy)?.[1] ?? "";
  const agent = [...tuple.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  expect(agent).toEqual([...GLOBAL_KEYS]);
});

describe("the page's layout (#875)", () => {
  test("the run console comes first in the page's order: the first Tab reaches Start", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await r.user.tab();
    expect(screen.getByRole("button", { name: zh["runner.start"] })).toHaveFocus();
  });

  test("no title over the columns: neither the task list's title and note nor a heading over the options", () => {
    renderEditor(<RunTab />, newSettings());
    expect(screen.queryByRole("heading", { name: zh["tasks.title"] })).toBeNull();
    expect(screen.queryByText("勾選的任務由上往下依序執行", { exact: false })).toBeNull(); // the note the list had
    expect(screen.queryByRole("heading", { name: /經驗本/ })).toBeNull(); // the task picked at the start
  });

  test("a task's options sit in a frame titled with its name, no id; the Mirror Dungeon's groups carry their own titles", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    // the first task shows at the start
    expect(within(screen.getByRole("group", { name: "經驗本" })).getByRole("combobox", { name: zh["lux.mode"] })).toBeVisible();
    expect(screen.queryByText("ExpLuxcavation")).toBeNull();
    await show(r, "領信");
    expect(within(screen.getByRole("group", { name: "領信" })).getByText(zh["tasks.none"])).toBeVisible();
    expect(screen.queryByText("ClaimMail")).toBeNull();
    await show(r, "鏡牢");
    expect(screen.queryByRole("group", { name: "鏡牢" })).toBeNull();
    expect(screen.getByRole("group", { name: zh["run.group_run"] })).toBeVisible();
  });

  test("the global options are a panel, folded at first", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    const webhook = screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) });
    expect(webhook).not.toBeVisible();
    await r.user.click(screen.getByText(zh["globals.title"]));
    expect(webhook).toBeVisible();
  });
});

describe("the task list", () => {
  test("a new file lists every task once, all ticked, in the user's order (#874)", () => {
    renderEditor(<RunTab />, newSettings());
    // README 建議順序: 經驗本 → 紐本 → 領信 → 狂氣換腦啡肽 → 換腦啡肽模組 → 領通行證任務 → 鏡牢
    expect(rows().map((x) => x.textContent)).toEqual([
      "經驗本", "紐本", "領信", "狂氣換腦啡肽", "換腦啡肽模組", "領通行證任務", "鏡牢",
    ].map((name) => expect.stringContaining(name)));
    const boxes = list().getAllByRole("checkbox");
    expect(boxes).toHaveLength(7);
    for (const box of boxes) expect(box).toBeChecked();
  });

  test("lists the file's tasks in its order with their ticks; a tick is saved", async () => {
    const s = assembleTwice();
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
    const r = renderEditor(<RunTab />, assembleTwice());
    expect(screen.queryByRole("checkbox", { name: fill(zh["tasks.tick"], { name: "換腦啡肽模組" }) })).toBeNull();
    await r.user.click(nthTick("換腦啡肽模組", 2));
    expect(r.settings().tasks.filter((x) => x.id === "AssembleModules")).toEqual([
      { id: "AssembleModules", enabled: false }, { id: "AssembleModules", enabled: true },
    ]);
    expect(r.settings().tasks[4]).toEqual({ id: "AssembleModules", enabled: true });
    expect(nthTick("換腦啡肽模組", 1)).not.toBeChecked();
  });

  test("a tick's hit area is larger than its box, and a click there leaves the picked task as it is", async () => {
    const r = renderEditor(<RunTab />, assembleTwice());
    const area = tick("領信").closest("label")!;
    expect(area).toHaveClass("tick");
    await r.user.click(area); // beside the box, inside its area
    expect(r.settings().tasks.find((x) => x.id === "ClaimMail")!.enabled).toBe(true);
    expect(screen.getByRole("group", { name: "狂氣換腦啡肽" })).toBeVisible();
    await r.user.click(tick("領信"));
    expect(r.settings().tasks.find((x) => x.id === "ClaimMail")!.enabled).toBe(false);
    expect(rows()[0]).toHaveAttribute("aria-current", "true");
  });

  test("Alt with an arrow and a drag change the run order, ticks moving with their tasks", async () => {
    const s = assembleTwice();
    s.tasks[0].enabled = true; // ChargeEnkephalin
    const r = renderEditor(<RunTab />, s);
    expect(screen.getByRole("list", { name: zh["tasks.title"] })).toBe(document.querySelector(".task-list ol"));
    await altMove(r.user, rows()[0], "ArrowDown");
    expect(ids(r.settings()).slice(0, 2)).toEqual(["AssembleModules", "ChargeEnkephalin"]);
    await altMove(r.user, rows()[7], "ArrowUp");
    expect(ids(r.settings()).slice(6)).toEqual(["MirrorDungeon", "ClaimMail"]);
    dragOnto(rows()[1], rows()[7]);
    expect(r.settings().tasks).toEqual([
      { id: "AssembleModules", enabled: false }, { id: "ExpLuxcavation", enabled: false }, { id: "ThreadLuxcavation", enabled: false },
      { id: "AssembleModules", enabled: false }, { id: "ClaimPassMissions", enabled: false }, { id: "MirrorDungeon", enabled: false },
      { id: "ClaimMail", enabled: false }, { id: "ChargeEnkephalin", enabled: true },
    ]);
  });

  test("a click on a task shows its options; a task without options says so", async () => {
    const r = renderEditor(<RunTab />, assembleTwice());
    // the first task shows at the start
    expect(screen.getByRole("group", { name: "狂氣換腦啡肽" })).toBeVisible();
    await r.user.click(within(rows()[6]).getByText("領信"));
    expect(screen.getByRole("group", { name: "領信" })).toBeVisible();
    expect(screen.getByText(zh["tasks.none"])).toBeVisible();
    expect(rows()[6]).toHaveAttribute("aria-current", "true");
  });

  test("either entry of a task listed twice shows that task's options and stays picked, also when it moves", async () => {
    const s = assembleTwice();
    s.tasks.push({ id: "MirrorDungeon", enabled: false });
    const r = renderEditor(<RunTab />, s);
    await r.user.click(within(rows()[8]).getByText("鏡牢"));
    expect(rows()[8]).toHaveAttribute("aria-current", "true");
    expect(rows()[7]).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("group", { name: zh["run.group_run"] })).toBeVisible();
    // both entries read the task's one set of options
    await r.user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) }), "hard");
    expect(r.settings().run.difficulty).toBe("hard");
    // the second entry moved above the first stays the one picked
    await altMove(r.user, rows()[8], "ArrowUp");
    expect(rows()[7]).toHaveAttribute("aria-current", "true");
    expect(rows()[8]).not.toHaveAttribute("aria-current");
  });

  test("a task listed more than once tags each entry #n, its tooltip which entry and that they share the options; one listed once, none", () => {
    renderEditor(<RunTab />, assembleTwice());
    const tags = list().getAllByText(/^#\d$/);
    expect(tags.map((x) => [x.textContent, x.closest("li"), x.getAttribute("title")])).toEqual([
      ["#1", rows()[1], fill(zh["tasks.entry_tip"], { n: 1, name: "換腦啡肽模組", of: 2 })],
      ["#2", rows()[4], fill(zh["tasks.entry_tip"], { n: 2, name: "換腦啡肽模組", of: 2 })],
    ]);
    // the old notes under the list are gone: what the tag's tooltip says now
    expect(document.querySelector(".task-list")!.textContent).not.toContain("列了");
  });

  test("a row's tooltip is its name and id, the one place the id shows (the agent's stop lines name a task by it)", () => {
    renderEditor(<RunTab />, newSettings());
    expect(rows().map((x) => x.querySelector("[title]")!.getAttribute("title"))).toEqual(
      ["ExpLuxcavation", "ThreadLuxcavation", "ClaimMail", "ChargeEnkephalin", "AssembleModules", "ClaimPassMissions", "MirrorDungeon"]
        .map((id) => fill(zh["tasks.row_tip"], { name: zh[`task.${id}` as keyof typeof zh], id })));
    expect(screen.queryByText("ExpLuxcavation")).toBeNull();
  });

  test("a row's copy lists its task once more right under it, unticked, and picks the copy; the two read #1 and #2", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "領通行證任務");
    await r.user.click(copy("領信"));
    expect(r.settings().tasks.slice(2, 4)).toEqual([{ id: "ClaimMail", enabled: true }, { id: "ClaimMail", enabled: false }]);
    expect(rows()[3]).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("group", { name: "領信" })).toBeVisible();
    expect(nthTick("領信", 1)).toBeChecked();
    expect(nthTick("領信", 2)).not.toBeChecked();
    expect([rows()[2], rows()[3]].map((x) => within(x).getByText(/^#\d$/).textContent)).toEqual(["#1", "#2"]);
    // the copy's own buttons name its entry's task: a copy of the copy goes under it
    await r.user.click(within(rows()[3]).getByRole("button", { name: fill(zh["tasks.copy"], { name: "領信" }) }));
    expect(ids(r.settings()).slice(2, 6)).toEqual(["ClaimMail", "ClaimMail", "ClaimMail", "ChargeEnkephalin"]);
    expect(rows()[4]).toHaveAttribute("aria-current", "true");
  });

  test("a row's ✕ takes it out, a task's only entry too, with Undo under the list, which puts it back and picks it", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "領通行證任務");
    await r.user.click(remove("領信"));
    expect(ids(r.settings())).not.toContain("ClaimMail");
    // the pick stays on its entry, now a row up
    expect(rows()[4]).toHaveAttribute("aria-current", "true");
    expect(rows()[4]).toHaveTextContent("領通行證任務");
    const note = list().getByRole("status");
    expect(note).toHaveTextContent(fill(zh["undo.deleted"], { name: "領信" }));
    await r.user.click(within(note).getByRole("button", { name: zh.undo }));
    expect(r.settings().tasks).toEqual(newSettings().tasks);
    expect(rows()[2]).toHaveAttribute("aria-current", "true");
    expect(list().queryByRole("status")).toBeNull();
  });

  test("the picked row's ✕ picks the row that takes its place, the row before when it was the last", async () => {
    const r = renderEditor(<RunTab />, assembleTwice());
    // the second entry of a task listed twice: the first one's removal leaves the pick on it, its tag gone
    await r.user.click(within(rows()[4]).getByText("換腦啡肽模組"));
    await r.user.click(within(rows()[1]).getByRole("button", { name: fill(zh["tasks.delete"], { name: "換腦啡肽模組" }) }));
    expect(rows()[3]).toHaveAttribute("aria-current", "true");
    expect(rows()[3]).toHaveTextContent("換腦啡肽模組");
    expect(list().queryByText(/^#\d$/)).toBeNull();
    await r.user.click(remove("換腦啡肽模組"));
    expect(rows()[3]).toHaveAttribute("aria-current", "true");
    expect(rows()[3]).toHaveTextContent("領通行證任務");
    await show(r, "鏡牢");
    await r.user.click(remove("鏡牢"));
    expect(rows()[rows().length - 1]).toHaveAttribute("aria-current", "true");
    expect(rows()[rows().length - 1]).toHaveTextContent("領信");
  });

  test("an empty list says how to add a task, and no options show", async () => {
    const s = newSettings();
    s.tasks = [{ id: "ClaimMail", enabled: true }];
    const r = renderEditor(<RunTab />, s);
    expect(screen.queryByText(zh["tasks.empty"])).toBeNull();
    await r.user.click(remove("領信"));
    expect(r.settings().tasks).toEqual([]);
    expect(list().getByText(zh["tasks.empty"])).toBeVisible();
    expect(document.querySelector(".task-options")).toBeEmptyDOMElement();
  });

  test("the copy and the ✕ show over the row's end only under the pointer, or the keyboard's focus on the row or on them", () => {
    renderEditor(<RunTab />, newSettings());
    const row = rows()[2];
    const acts = copy("領信").parentElement!;
    expect(acts).toContainElement(remove("領信"));
    const shown = (at?: Element | { focus: Element }) =>
      [cssValueOf(css, acts, "opacity", at), cssValueOf(css, acts, "pointer-events", at)];
    expect(shown()).toEqual(["0", "none"]); // no room of their own, and no click lands on them unseen
    expect(cssValueOf(css, acts, "position")).toBe("absolute");
    expect(shown(row)).toEqual(["1", "auto"]);
    expect(shown({ focus: row })).toEqual(["1", "auto"]);
    expect(shown({ focus: remove("領信") })).toEqual(["1", "auto"]);
    expect(cssValueOf(css, copy("經驗本").parentElement!, "opacity", row)).toBe("0"); // another row's stay hidden
  });

  test("加入任務 lists each task in a new file's order, how often the list has it where that is not once; a pick adds it last, unticked, picked", async () => {
    const s = assembleTwice().tasks.filter((x) => x.id !== "ClaimMail");
    const r = renderEditor(<RunTab />, { ...newSettings(), tasks: s });
    await r.user.click(addButton());
    const items = within(screen.getByRole("menu", { name: zh["tasks.add"] })).getAllByRole("menuitem");
    // the order a new file lists them in, read from the schema's default
    expect(items.map((x) => x.querySelector("span")!.textContent)).toEqual(newSettings().tasks.map((x) => zh[`task.${x.id}` as keyof typeof zh]));
    const said = Object.fromEntries(items.map((x) => [x.querySelector("span")!.textContent, x.querySelector("small")!.textContent]));
    expect(said).toEqual({ 經驗本: "", 紐本: "", 領信: zh["tasks.absent"], 狂氣換腦啡肽: "", 換腦啡肽模組: fill(zh["tasks.listed"], { n: 2 }),
      領通行證任務: "", 鏡牢: "" });
    await r.user.click(items[2]);
    expect(r.settings().tasks[r.settings().tasks.length - 1]).toEqual({ id: "ClaimMail", enabled: false });
    expect(rows()[rows().length - 1]).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("group", { name: "領信" })).toBeVisible();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(addButton()).toHaveFocus();
  });

  test("the menu opens over the page, taking no room, its first item focused; the arrows, Home and End step; Escape, Tab or a click away close it", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    expect(addButton()).toHaveAttribute("aria-expanded", "false");
    await r.user.click(addButton());
    expect(addButton()).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu");
    expect(cssValueOf(css, menu, "position")).toBe("absolute");
    const items = within(menu).getAllByRole("menuitem");
    expect(items[0]).toHaveFocus();
    await r.user.keyboard("{ArrowDown}");
    expect(items[1]).toHaveFocus();
    await r.user.keyboard("{End}");
    expect(items[6]).toHaveFocus();
    await r.user.keyboard("{ArrowDown}");
    expect(items[0]).toHaveFocus();
    await r.user.keyboard("{ArrowUp}");
    expect(items[6]).toHaveFocus();
    await r.user.keyboard("{Home}");
    expect(items[0]).toHaveFocus();
    await r.user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(addButton()).toHaveFocus();
    await r.user.keyboard("{Enter}");
    expect(within(screen.getByRole("menu")).getAllByRole("menuitem")[0]).toHaveFocus();
    await r.user.tab();
    expect(screen.queryByRole("menu")).toBeNull();
    await r.user.click(addButton());
    await r.user.click(screen.getByRole("group", { name: "經驗本" }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(r.settings().tasks).toEqual(newSettings().tasks); // nothing added
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
    await r.user.click(screen.getByText(zh["globals.title"])); // the panel is folded at first
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

  test("the tab's long notes show one topic to a line", async () => {
    await show(renderEditor(<RunTab />, newSettings()), "鏡牢");
    for (const key of ["run.start_team_note", "emu.note", "run.keep_dismissed_screens_note"] as const) expectLines(zh[key]);
  });
});

describe("each field's settings key, as the agent's stop lines name it", () => {
  /** The settings key `path` the tab shows after its field's label. */
  const keyOf = (path: string) => screen.getByText(path, { selector: "code" });
  /** Whether the stylesheet shows that key, with the pointer over an element, the keyboard focus on one, or neither. */
  const shown = (path: string, at?: Element | { focus: Element }) => cssValueOf(css, keyOf(path), "visibility", at) !== "hidden";
  // a field of each kind: a task option's choice, the run limit (a switch with its number), a task's switch, a global option's
  // text and switch, the emulator's fields
  const MIRROR = ["run/difficulty", "run/start_team", "run/runs", "run/stop_when_weekly_bonus_out"];
  const EVERY_TASK = ["run/webhook_url", "run/auto_download", "emulator/address", "emulator/mumu_index", "emulator/mumu_manager"];

  test("stays in the page after its label, shown only while the pointer is over that field, its label included", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    for (const path of [...MIRROR, ...EVERY_TASK]) {
      expect(keyOf(path).closest(".keyed")).toHaveTextContent(path);
      expect(shown(path)).toBe(false);
    }
    // over a label, and over a field's control: that field's key shows, no other
    const label = keyOf("run/start_team").closest(".keyed")!;
    expect(shown("run/start_team", label)).toBe(true);
    expect(shown("run/difficulty", label)).toBe(false);
    const runs = screen.getByRole("checkbox", { name: zh["run.runs"] });
    expect(shown("run/runs", runs)).toBe(true);
    expect(shown("run/runs", within(runs.closest(".toggle") as HTMLElement).getByRole("spinbutton"))).toBe(true);
    expect(shown("run/start_team", runs)).toBe(false);
    for (const path of EVERY_TASK) expect(shown(path, keyOf(path).closest(".keyed")!)).toBe(true);
    expect(shown("emulator/address", keyOf("emulator/mumu_index"))).toBe(false);
    await show(r, "經驗本");
    const consecutive = screen.getByRole("checkbox", { name: zh["lux.consecutive"] });
    expect(shown("luxcavation/exp/consecutive")).toBe(false);
    expect(shown("luxcavation/exp/consecutive", consecutive)).toBe(true);
    // a switch's label and its key are one item of its flex row: apart, the label wrapped a word to a line in the window
    const box = consecutive.closest("label")!;
    expect([...box.children].map((x) => x.tagName)).toEqual(["INPUT", "SPAN"]);
    expect(box.querySelector(":scope > span")).toHaveTextContent(`${zh["lux.consecutive"]}luxcavation/exp/consecutive`);
  });

  // which focus draws a ring (:focus-visible) is the browser's call: one the keyboard moved, and a text box's either way, not a
  // click on a switch or a choice; the real window's check showed it
  test("shows while the keyboard focus is in its field, on its control or its number", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    const difficulty = screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) });
    expect(shown("run/difficulty", { focus: difficulty })).toBe(true);
    expect(shown("run/target_floor", { focus: difficulty })).toBe(false);
    const runs = screen.getByRole("checkbox", { name: zh["run.runs"] });
    expect(shown("run/runs", { focus: runs })).toBe(true);
    expect(shown("run/runs", { focus: within(runs.closest(".toggle") as HTMLElement).getByRole("spinbutton") })).toBe(true);
    const download = screen.getByRole("checkbox", { name: zh["run.auto_download"] });
    expect(shown("run/auto_download", { focus: download })).toBe(true);
    expect(shown("run/auto_accept_terms", { focus: download })).toBe(false);
    expect(shown("emulator/address", { focus: screen.getByRole("textbox", { name: zh["emu.address"] }) })).toBe(true);
  });

  test("where it does not fit, it is cut short and its label stays whole on one line; its tooltip gives it whole (#875)", async () => {
    await show(renderEditor(<RunTab />, newSettings()), "鏡牢");
    for (const path of ["run/stop_when_weekly_bonus_out", "run/difficulty", "emulator/mumu_manager"]) {
      const key = keyOf(path);
      expect(key).toHaveAttribute("title", path);
      expect(["text-overflow", "white-space", "overflow"].map((p) => cssValueOf(css, key, p))).toEqual(["ellipsis", "nowrap", "hidden"]);
      // the label beside it never shrinks: a fraction of a pixel less wrapped its last character to a second line
      const label = [...key.parentElement!.children].find((x) => x !== key)!;
      expect(label.textContent).not.toBe("");
      expect(cssValueOf(css, label, "flex")).toBe("none");
    }
  });

  test("shown, it moves nothing: hidden, it keeps its room, and showing it changes its visibility alone", () => {
    renderEditor(<RunTab />, newSettings());
    expect(cssValueOf(css, keyOf("emulator/address"), "display")).not.toBe("none");
    const showing = cssRules(css).filter((r) => r.selector.includes("code.key") && /:hover|:focus/.test(r.selector));
    expect(showing).not.toHaveLength(0);
    for (const rule of showing) expect(rule.body.split(";").map((x) => x.split(":")[0].trim()).filter(Boolean)).toEqual(["visibility"]);
  });

  test("a screen reader reads the label as the field's name and its key as the field's description", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    const fields = [
      [screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) }), "run/difficulty"],
      [screen.getByRole("combobox", { name: new RegExp(`^${zh["run.start_team"]}`) }), "run/start_team"],
      [screen.getByRole("checkbox", { name: zh["run.runs"] }), "run/runs"],
      [screen.getByRole("checkbox", { name: zh["run.stop_when_weekly_bonus_out"] }), "run/stop_when_weekly_bonus_out"],
      [screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) }), "run/webhook_url"],
      [screen.getByRole("checkbox", { name: zh["run.auto_download"] }), "run/auto_download"],
      [screen.getByRole("textbox", { name: zh["emu.address"] }), "emulator/address"],
      [screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }), "emulator/mumu_index"],
      [screen.getByRole("textbox", { name: zh["emu.mumu_manager"] }), "emulator/mumu_manager"],
    ] as const;
    for (const [control, path] of fields) {
      expect(control).not.toHaveAccessibleName(new RegExp(path));
      expect(control).toHaveAccessibleDescription(path);
    }
    await show(r, "經驗本");
    expect(screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) })).toHaveAccessibleDescription("luxcavation/exp/team");
    expect(screen.getByRole("checkbox", { name: zh["lux.consecutive"] })).toHaveAccessibleDescription("luxcavation/exp/consecutive");
  });
});
