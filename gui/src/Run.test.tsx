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
const remove = (name: string) => list().getByRole("button", { name: fill(zh["tasks.remove"], { name }) });
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
    await r.user.click(within(rows()[1]).getByRole("button", { name: fill(zh["tasks.remove"], { name: "換腦啡肽模組" }) }));
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

  test("the focus stays in the list: after a ✕ on the row that took its place, after an Undo on the row put back, in an empty list on 加入任務", async () => {
    const s = newSettings();
    s.tasks = [{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true }];
    const r = renderEditor(<RunTab />, s);
    remove("領信").focus();
    await r.user.keyboard("{Enter}");
    expect(rows()[0]).toHaveTextContent("鏡牢");
    expect(rows()[0]).toHaveFocus();
    list().getByRole("button", { name: zh.undo }).focus();
    await r.user.keyboard("{Enter}");
    expect(rows()[0]).toHaveTextContent("領信");
    expect(rows()[0]).toHaveFocus();
    remove("鏡牢").focus();
    await r.user.keyboard("{Enter}");
    expect(rows()[0]).toHaveFocus(); // the last row went: the one before it
    remove("領信").focus();
    await r.user.keyboard("{Enter}");
    expect(addButton()).toHaveFocus();
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
    // the focused item shows, whether the menu opened from the pointer or the keyboard
    expect(cssValueOf(css, items[0], "background")).toBe("var(--hov)");
    expect(cssValueOf(css, items[1], "background")).toBe("none");
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
    // the pointer moves the focus too: one item lit, the one Enter picks
    await r.user.hover(items[3]);
    expect(items[3]).toHaveFocus();
    await r.user.keyboard("{Home}");
    expect(items[0]).toHaveFocus();
    // the pointer still on the 4th, the focus on the 1st: the 1st alone is lit
    expect(cssValueOf(css, items[3], "background", items[3])).toBe("none");
    expect(cssValueOf(css, items[0], "background", items[3])).toBe("var(--hov)");
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
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["run.runs"] }), { target: { value: "3" } });
    expect(r.settings().run.runs).toBe(3);
    await r.user.click(limit);
    expect(r.settings().run.runs).toBeNull();
    expect(screen.getByRole("spinbutton", { name: zh["run.runs"] })).toBeDisabled();
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["run.wipe_retries"] }), { target: { value: "5" } });
    expect(r.settings().run.wipe_retries).toBe(5);
    await r.user.click(screen.getByRole("checkbox", { name: zh["run.stop_when_weekly_bonus_out"] }));
    expect(r.settings().run.stop_when_weekly_bonus_out).toBe(true);
  });

  test("the run limit is laid out as the fields beside it: its label on top, the switch and the number on one line under it (#878)", async () => {
    await show(renderEditor(<RunTab />, newSettings()), "鏡牢");
    const limit = screen.getByRole("checkbox", { name: zh["run.runs"] });
    const count = screen.getByRole("spinbutton", { name: zh["run.runs"] });
    expect(limit.parentElement).toBe(count.parentElement); // one line
    const label = screen.getByText(zh["run.runs"], { selector: ".kl" }).closest("[data-path='run/runs'] > *")!;
    expect(label.compareDocumentPosition(limit) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // above them
    expect(label.contains(limit)).toBe(false);
    // the label the size and weight of its neighbours' (the difficulty's, a field's label)
    const beside = screen.getByText(zh["run.difficulty"], { selector: ".kl" }).closest("[data-path='run/difficulty'] > *")!;
    for (const p of ["font-size", "font-weight", "color"]) expect(cssValueOf(css, label, p)).toBe(cssValueOf(css, beside, p));
    expect(cssValueOf(css, limit.parentElement!, "display")).toBe("flex");
    expect(cssValueOf(css, limit.parentElement!, "align-items")).toBe("center");
  });
});

describe("the team pick lists", () => {
  const two = () => {
    const s = newSettings();
    Object.assign(s, queuedTeams([newTeam(1, "Ta"), newTeam(2, "Tb")]));
    s.teams[1].enabled = false;
    return s;
  };
  const optionsOf = (el: HTMLSelectElement) => [...el.options].map((o) => o.textContent);

  test("a team added or renamed shows at once, in the team queue and in a Luxcavation task's team pick", async () => {
    const s = two();
    const r = renderEditor(<><RunTab /><Rename /></>, s);
    await show(r, "鏡牢");
    await r.user.click(screen.getByRole("button", { name: "rename and add" }));
    const queueRows = within(screen.getByRole("list", { name: zh["queue.title"] })).getAllByRole("listitem");
    expect(queueRows.map((li) => li.textContent!.match(/Renamed|T\w/)![0])).toEqual(["Renamed", "Tb", "Tc"]);
    await show(r, "經驗本");
    const team = screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) }) as HTMLSelectElement;
    expect(optionsOf(team)).toEqual(["未選擇", "Renamed（TEAMS #1）", "Tb（TEAMS #2）", "Tc（TEAMS #3）"]);
  });

  test("a Luxcavation task's team deleted since shows as deleted, with why the task will stop", async () => {
    const s = two();
    s.luxcavation.exp.team = "gone";
    await show(renderEditor(<RunTab />, s), "經驗本");
    const team = screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) }) as HTMLSelectElement;
    expect(team.value).toBe("gone");
    expect(team.selectedOptions[0].textContent).toBe(fill(zh["teamPick.gone"], { id: "gone" }));
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
    await r.user.selectOptions(screen.getByRole("combobox", { name: zh["lux.mode"] }), "count");
    fireEvent.change(count, { target: { value: "6" } });
    await r.user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) }), s.teams[0].id);
    fireEvent.change(screen.getByRole("spinbutton", { name: new RegExp(zh["lux.retries"]) }), { target: { value: "2" } });
    await r.user.click(screen.getByRole("checkbox", { name: zh["lux.consecutive"] }));
    expect(r.settings().luxcavation[task]).toEqual({ mode: "count", count: 6, team: s.teams[0].id, retries: 2, consecutive: false });
  });

  test("Charge Enkephalin's count, with Lunacy's cost first on the page", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "狂氣換腦啡肽");
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["charge.count"] }), { target: { value: "4" } });
    expect(r.settings().charge_enkephalin.count).toBe(4);
    expect(zh["charge.cost"].split("\n")[0]).toContain("Lunacy");
    expectLines(zh["charge.cost"]);
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

  test("a long tooltip keeps one topic to a line", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await r.user.click(screen.getByText(zh["globals.title"]));
    const tip = tipOf(screen.getByRole("checkbox", { name: zh["run.keep_dismissed_screens"] }));
    expect(tip).toBe(zh["run.keep_dismissed_screens_note"]);
    expect(tip!.split("\n")).toHaveLength(2);
  });

  test("手動設定 is a panel folded at first that holds the three fields; its title's tooltip names them (#876)", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    const fields = [screen.getByRole("textbox", { name: zh["emu.address"] }), screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }),
      screen.getByRole("textbox", { name: zh["emu.mumu_manager"] })];
    for (const field of fields) expect(field).not.toBeVisible();
    const title = screen.getByText(zh["emu.manual"]);
    expect(title).toHaveAttribute("title", zh["emu.manual_note"]);
    await r.user.click(title);
    for (const field of fields) expect(field).toBeVisible();
  });

  test("how the address and the MuMu instance work is their tooltip and their description, not a line on the page (#876)", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await r.user.click(screen.getByText(zh["emu.manual"]));
    for (const [control, note] of [
      [screen.getByRole("textbox", { name: zh["emu.address"] }), zh["emu.address_note"]],
      [screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }), zh["emu.mumu_index_note"]],
    ] as const) {
      expect(control.closest("label")).toHaveAttribute("title", note);
      expect(control).toHaveAccessibleDescription(new RegExp(`${note}$`));
      for (const shown of screen.queryAllByText(note)) expect(shown).not.toBeVisible();
    }
  });
});

describe("each field's settings key, as the agent's stop lines name it", () => {
  /** The settings key `path` the tab shows after its field's label. */
  const keyOf = (path: string) => screen.getByText(path, { selector: "code" });
  /** Whether the stylesheet shows that key, with the pointer over an element, the keyboard focus on one, or neither. */
  const shown = (path: string, at?: Element | { focus: Element }) => cssValueOf(css, keyOf(path), "visibility", at) !== "hidden";
  // a field of each kind: a task option's choice, the run limit (a switch with its number), a task's switch, a global option's
  // text and switch, the emulator's fields
  const MIRROR = ["run/difficulty", "run/target_floor", "run/runs", "run/stop_when_weekly_bonus_out"];
  const EVERY_TASK = ["run/webhook_url", "run/auto_download", "emulator/address", "emulator/mumu_index", "emulator/mumu_manager"];

  test("stays in the page after its label, shown only while the pointer is over that field, its label included", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    for (const path of [...MIRROR, ...EVERY_TASK]) {
      expect(keyOf(path).closest(".keyed")).toHaveTextContent(path);
      expect(shown(path)).toBe(false);
    }
    // over a label, and over a field's control: that field's key shows, no other
    const label = keyOf("run/target_floor").closest(".keyed")!;
    expect(shown("run/target_floor", label)).toBe(true);
    expect(shown("run/difficulty", label)).toBe(false);
    const runs = screen.getByRole("checkbox", { name: zh["run.runs"] });
    expect(shown("run/runs", runs)).toBe(true);
    expect(shown("run/runs", screen.getByRole("spinbutton", { name: zh["run.runs"] }))).toBe(true);
    expect(shown("run/target_floor", runs)).toBe(false);
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
    expect(shown("run/runs", { focus: screen.getByRole("spinbutton", { name: zh["run.runs"] }) })).toBe(true);
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
      [screen.getByRole("combobox", { name: new RegExp(`^${zh["run.target_floor"]}`) }), "run/target_floor"],
      [screen.getByRole("checkbox", { name: zh["run.runs"] }), "run/runs", zh["run.runs_note"]],
      [screen.getByRole("spinbutton", { name: zh["run.runs"] }), "run/runs", zh["run.runs_note"]],
      [screen.getByRole("checkbox", { name: zh["run.stop_when_weekly_bonus_out"] }), "run/stop_when_weekly_bonus_out"],
      [screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) }), "run/webhook_url", zh["run.webhook_url_note"]],
      [screen.getByRole("checkbox", { name: zh["run.auto_download"] }), "run/auto_download", zh["run.auto_download_note"]],
      [screen.getByRole("textbox", { name: zh["emu.address"] }), "emulator/address", zh["emu.address_note"]],
      [screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }), "emulator/mumu_index", zh["emu.mumu_index_note"]],
      [screen.getByRole("textbox", { name: zh["emu.mumu_manager"] }), "emulator/mumu_manager"],
    ] as const;
    // the key first, then how the field works where its tooltip says it (#876, #879)
    for (const [control, path, help] of fields) {
      expect(control).not.toHaveAccessibleName(new RegExp(path));
      expect(control).toHaveAccessibleDescription(help ? `${path} ${help}` : path);
    }
    await show(r, "經驗本");
    expect(screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) }))
      .toHaveAccessibleDescription(described("luxcavation/exp/team", zh["lux.team_note"]));
    expect(screen.getByRole("checkbox", { name: zh["lux.consecutive"] }))
      .toHaveAccessibleDescription(described("luxcavation/exp/consecutive", zh["lux.consecutive_note"]));
  });
});

/** The tooltip the pointer gets over a control: the title of the nearest element around it that has one. */
const tipOf = (control: Element) => control.closest("[title]")?.getAttribute("title") ?? null;
/** Text with its spaces and line breaks taken out: a note's lines are drawn with <br>, a tooltip's with "\n". */
const flat = (text: string | null | undefined) => (text ?? "").replace(/\s+/g, "");
/** The elements the page shows `text` in, the innermost ones: a field's hidden description is not shown. */
const onPage = (text: string) => screen.queryAllByText((_, el) => !!el && flat(el.textContent).includes(flat(text))
  && ![...el.children].some((c) => flat(c.textContent).includes(flat(text)))).filter((el) => !el.closest("[hidden]"));
/** A field's description as a screen reader gets it: its settings key, then how it works (its tooltip). */
const described = (path: string, help: string) => `${path} ${help}`;

// spec #871 「說明文字：頁面上只留花費與風險」, #879's table: what warns of a cost or a risk stays on the page, under the field it
// belongs to; how a field works is its tooltip (the element's title), which a screen reader reads as its description
describe("on the page only a cost or a risk, how a field works its tooltip (#879)", () => {
  test.each([["經驗本", "exp"], ["紐本", "thread"]] as const)("%s: the task's note is the mode's tooltip, each field's its own", async (name, task) => {
    const s = newSettings();
    Object.assign(s, queuedTeams([newTeam(1, "Ta")]));
    const r = renderEditor(<RunTab />, s);
    await show(r, name);
    const path = `luxcavation/${task}`;
    const mode = screen.getByRole("combobox", { name: zh["lux.mode"] });
    const count = screen.getByRole("spinbutton", { name: new RegExp(zh["lux.count"]) });
    const team = screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.team"]}`) });
    const consecutive = screen.getByRole("checkbox", { name: zh["lux.consecutive"] });
    const retries = screen.getByRole("spinbutton", { name: new RegExp(zh["lux.retries"]) });
    for (const [control, key, help] of [
      [mode, "mode", zh[`lux.${task}_note`]], [count, "count", zh["lux.count_unused"]], [team, "team", zh["lux.team_note"]],
      [consecutive, "consecutive", zh["lux.consecutive_note"]], [retries, "retries", zh["lux.retries_note"]],
    ] as const) {
      expect(tipOf(control)).toBe(help);
      expect(control).toHaveAccessibleDescription(described(`${path}/${key}`, help));
    }
    // how the task plays and each field works is on no line of the page
    for (const line of zh[`lux.${task}_note`].split("\n")) expect(onPage(line)).toEqual([]);
    for (const help of [zh["lux.count_unused"], zh["lux.team_note"], zh["lux.retries_note"], "超過 10 場時，先打 ×10，再打剩下的。"]) {
      expect(onPage(help)).toEqual([]);
    }
    // what Consecutive Battle costs stays under it; no team picked stops the task, said as a caution while none is
    expect(onPage(zh["lux.consecutive_cost"])).toEqual([expect.objectContaining({ tagName: "SMALL" })]);
    expect(onPage(zh["lux.team_none_note"])).toEqual([expect.objectContaining({ className: "caution" })]);
    // the count's tooltip only in daily mode, where it is greyed out; a team picked, the caution goes
    await r.user.selectOptions(mode, "count");
    expect(tipOf(count)).toBeNull();
    expect(count).toHaveAccessibleDescription(`${path}/count`);
    await r.user.selectOptions(team, s.teams[0].id);
    expect(onPage(zh["lux.team_none_note"])).toEqual([]);
  });

  test("a Luxcavation task's deleted team says so as before, not that none is picked", async () => {
    const s = newSettings();
    s.luxcavation.exp.team = "gone";
    await show(renderEditor(<RunTab />, s), "經驗本");
    expect(onPage(zh["teamPick.gone_note"])).toHaveLength(1);
    expect(onPage(zh["lux.team_none_note"])).toEqual([]);
  });

  test("Charge Enkephalin: its cost and prices on the page, its whole note the count's tooltip", async () => {
    await show(renderEditor(<RunTab />, newSettings()), "狂氣換腦啡肽");
    const count = screen.getByRole("spinbutton", { name: zh["charge.count"] });
    expect(tipOf(count)).toBe(zh["charge.note"]);
    expect(count).toHaveAccessibleDescription(described("charge_enkephalin/count", zh["charge.note"]));
    expect(onPage(zh["charge.cost"])).toEqual([expect.objectContaining({ className: "caution" })]);
    for (const moved of ["0 就什麼都不做", "手動換過的也算", "每次按確認前", "遊戲一天最多換 10 次"]) expect(onPage(moved)).toEqual([]);
  });

  test("Mirror Dungeon: the run limit, the theme pack refreshes and what to do when retries run out work in their tooltips", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    await show(r, "鏡牢");
    const limit = screen.getByRole("checkbox", { name: zh["run.runs"] });
    const refresh = screen.getByRole("combobox", { name: new RegExp(`^${zh["run.theme_pack_refresh"]}`) });
    const after = screen.getByRole("combobox", { name: new RegExp(`^${zh["run.after_retries"]}`) });
    for (const [control, key, help] of [
      [limit, "runs", zh["run.runs_note"]], [screen.getByRole("spinbutton", { name: zh["run.runs"] }), "runs", zh["run.runs_note"]],
      [refresh, "theme_pack_refresh", zh["run.theme_pack_refresh_note"]], [after, "after_retries", zh["run.after_retries_note"]],
    ] as const) {
      expect(tipOf(control)).toBe(help);
      expect(control).toHaveAccessibleDescription(described(`run/${key}`, help));
    }
    for (const moved of [zh["run.runs_note"], zh["run.theme_pack_refresh_note"], "全滅重打用完，或隊伍的存活門檻成立時，照這裡處理。"]) {
      expect(onPage(moved)).toEqual([]);
    }
    // what forfeiting costs, only while it is picked
    expect(r.settings().run.after_retries).toBe("forfeit");
    expect(onPage(zh["run.after_retries_forfeit"])).toEqual([expect.objectContaining({ tagName: "SMALL" })]);
    await r.user.selectOptions(after, "stop");
    expect(onPage(zh["run.after_retries_forfeit"])).toEqual([]);
  });

  test("the global options: their title's tooltip says what they are, each field's how it works; the screenshots' risk stays", async () => {
    const r = renderEditor(<RunTab />, newSettings());
    const title = screen.getByText(zh["globals.title"]);
    expect(title).toHaveAttribute("title", zh["globals.note"]);
    expect(title).toHaveAccessibleDescription(zh["globals.note"]);
    await r.user.click(title);
    expect(onPage(zh["globals.note"])).toEqual([]);
    for (const key of GLOBAL_KEYS) {
      const control = key === "webhook_url" ? screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) })
        : screen.getByRole("checkbox", { name: zh[`run.${key}`] });
      expect(tipOf(control)).toBe(zh[`run.${key}_note`]);
      expect(control).toHaveAccessibleDescription(described(`run/${key}`, zh[`run.${key}_note`]));
      for (const line of zh[`run.${key}_note`].split("\n")) expect(onPage(line)).toEqual([]);
    }
    expect(onPage(zh["run.keep_dismissed_screens_risk"])).toEqual([expect.objectContaining({ tagName: "SMALL" })]);
  });

  test("where a whole note is the tooltip, what stays on the page is cut from it word for word, in both languages", () => {
    for (const text of [TEXT.zh_tw, TEXT.en_us]) {
      expect(text["lux.consecutive_note"]).toContain(text["lux.consecutive_cost"]);
      expect(text["run.after_retries_note"]).toContain(text["run.after_retries_forfeit"]);
      for (const line of text["charge.cost"].split("\n")) expect(text["charge.note"]).toContain(line);
      expect(text["sched.note"]).toContain(text["sched.logged_on_only"]);
    }
  });

  test("notes wrap with no last line of a word alone", () => {
    renderEditor(<RunTab />, newSettings());
    for (const note of [onPage(zh["lux.consecutive_cost"])[0], onPage(zh["lux.team_none_note"])[0]]) {
      expect(cssValueOf(css, note, "text-wrap")).toBe("pretty");
    }
  });
});
