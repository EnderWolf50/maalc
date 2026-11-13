// The editor shell (App.tsx) around the tabs: what a tab switch keeps, the problems it marks and lists while editing, and Ctrl+S.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import capability from "../src-tauri/capabilities/default.json";
import App from "./App";
import { TEXT, fill, type Key } from "./i18n";
import { GIFT_KEYWORDS, defaultGorder, defaultStarlight, newPackPlan, newSettings, newTeam, SINNERS, type Settings } from "./model";

const file = vi.hoisted(() => ({ text: "", saved: [] as string[], keepOpen: undefined as (() => boolean) | undefined, closed: 0, reloaded: 0 }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: (text: string) => { file.saved.push(text); file.text = text; return Promise.resolve(); },
  rootDir: () => Promise.resolve("root"),
  onCloseRequested: (keepOpen: () => boolean) => { file.keepOpen = keepOpen; return () => {}; },
  closeWindow: () => { file.closed++; return Promise.resolve(); },
  reloadPage: () => { file.reloaded++; },
}));
beforeEach(() => { file.saved = []; file.keepOpen = undefined; file.closed = 0; file.reloaded = 0; });

const zh = TEXT.zh_tw;
const two = (prefix: string) => [1, 2].map((n) => ({ id: `${prefix}${n}`, name: `${prefix.toUpperCase()}${n}` }));
const settings = (): Settings => ({
  ...newSettings(), language: "zh_tw",
  teams: [{ ...newTeam(1, "Ta"), id: "a" }, { ...newTeam(2, "Tb"), id: "b" }],
  deployment_order_plans: two("d").map((p) => ({ ...p, order: [...SINNERS] })),
  starlight_plans: two("s").map((p) => ({ ...p, ...defaultStarlight() })),
  theme_pack_plans: two("p").map((p) => ({ ...p, ...newPackPlan() })),
});

const tab = (name: string) => screen.getByRole("tab", { name });
const nameBox = () => screen.getByRole("textbox", { name: zh.name });
const pickInList = async (user: ReturnType<typeof userEvent.setup>, name: string) =>
  user.click(within(document.querySelector("aside")!).getByText(name));

describe("a tab switch", () => {
  beforeEach(() => { file.text = JSON.stringify(settings()); });

  test("keeps the team the user picked", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    await pickInList(user, "Tb");
    expect(nameBox()).toHaveValue("Tb");
    await user.click(tab(zh["tab.run"]));
    await user.click(tab(zh["tab.teams"]));
    expect(nameBox()).toHaveValue("Tb");
  });

  test.each([
    ["tab.deployment", "D2"],
    ["tab.starlight", "S2"],
    ["tab.themepacks", "P2"],
  ] as const)("keeps the plan the user picked in %s", async (label, plan) => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    await user.click(tab(zh[label]));
    await pickInList(user, plan);
    expect(nameBox()).toHaveValue(plan);
    await user.click(tab(zh["tab.teams"]));
    await user.click(tab(zh[label]));
    expect(nameBox()).toHaveValue(plan);
  });
});

/** The editor on `s` with the tab `start` open, no save tried: the problems the file has show from the start. */
async function openOn(s: Settings, start: string) {
  file.text = JSON.stringify(s);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("tab", { name: start }));
  return user;
}
const problem = (text: string | RegExp) => within(screen.getByRole("alert")).getByRole("button", { name: text });
const plate = () => document.querySelector(".status")!;
/** Press Ctrl+S on the focused element; true when the editor kept the browser from its own Save page. */
const ctrlS = (more: KeyboardEventInit = {}) => {
  const e = new KeyboardEvent("keydown", { key: "s", code: "KeyS", ctrlKey: true, bubbles: true, cancelable: true, ...more });
  act(() => { (document.activeElement ?? document.body).dispatchEvent(e); });
  return e.defaultPrevented;
};

describe("a problem shows while editing, before any save", () => {
  /** What shows of a problem: the field marked and described by the problem's words, its tab marked, and the problems block. */
  const marked = (field: HTMLElement, tabName: string) => {
    expect(field).toHaveAttribute("aria-invalid", "true");
    const block = screen.getByRole("alert");
    expect(block).toHaveTextContent(zh.saveBlocked);
    expect(block).toHaveTextContent(field.getAttribute("aria-describedby")!.split(" ")
      .map((id) => document.getElementById(id)!.textContent).join(""));
    expect(tab(tabName)).toHaveClass("bad");
  };
  const unmarked = (field: HTMLElement, tabName: string) => {
    expect(field).not.toHaveAttribute("aria-invalid");
    expect(tab(tabName)).not.toHaveClass("bad");
    expect(screen.queryByRole("alert")).toBeNull();
  };
  const slot = () => screen.getByRole("spinbutton", { name: zh["team.game_team"] });
  /** Which rows of the team list are marked wrong, top to bottom. */
  const bad = () => [...document.querySelectorAll("aside li")].map((r) => r.classList.contains("bad"));

  test("one the file has, as it opens", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    await openOn(s, zh["tab.teams"]);
    marked(slot(), zh["tab.teams"]);
    expect(problem(/隊伍「Ta」、「Tb」都啟用，也都用 TEAMS #1/)).toBeInTheDocument();
    expect(file.saved).toEqual([]);
  });

  test("a choice made wrong, at once; put right, every mark goes at once", async () => {
    const s = settings();
    s.run.target_floor = 10;
    s.run.difficulty = "hard";
    s.teams.forEach((x) => { x.hard_from_floor = 1; });
    const user = await openOn(s, zh["tab.run"]);
    const difficulty = screen.getByRole("combobox", { name: zh["run.difficulty"] });
    unmarked(difficulty, zh["tab.run"]);
    await user.selectOptions(difficulty, "normal");
    marked(difficulty, zh["tab.run"]);
    expect(problem(/但難度是普通/)).toBeInTheDocument();
    expect(plate()).toHaveTextContent(fill(zh["saveState.toFix"], { n: 1 }));
    await user.selectOptions(difficulty, "hard");
    unmarked(difficulty, zh["tab.run"]);
  });

  test("a text field is marked once it loses focus, not while it is typed in; a letter typed back clears it at once", async () => {
    const user = await openOn(settings(), zh["tab.teams"]);
    await user.clear(nameBox()); // the team's name emptied
    expect(nameBox()).toHaveFocus();
    unmarked(nameBox(), zh["tab.teams"]);
    expect(plate()).toHaveAttribute("data-state", "dirty"); // the save plate waits too: nothing turns red while typing
    await user.tab();
    marked(nameBox(), zh["tab.teams"]);
    expect(plate()).toHaveAttribute("data-state", "blocked");
    await user.type(nameBox(), "x");
    unmarked(nameBox(), zh["tab.teams"]);
  });

  test("a number typed into a clash with another team is marked once the field loses focus", async () => {
    const s = settings();
    s.teams[1].game_team = 12;
    const user = await openOn(s, zh["tab.teams"]);
    await user.type(slot(), "2"); // TEAMS #1 becomes #12, the second team's
    expect(slot()).toHaveValue(12);
    unmarked(slot(), zh["tab.teams"]);
    await user.tab();
    marked(slot(), zh["tab.teams"]);
    expect(problem(/隊伍「Ta」、「Tb」都啟用，也都用 TEAMS #12/)).toBeInTheDocument();
  });

  test("what another writer puts in the file shows at once, also while a field is typed in", async () => {
    const user = await openOn(settings(), zh["tab.teams"]);
    await user.clear(nameBox());
    unmarked(nameBox(), zh["tab.teams"]);
    const other = settings();
    other.teams[0].hard_from_floor = 3; // the Agent's change, away from the name
    file.text = JSON.stringify(other);
    act(() => { window.dispatchEvent(new Event("focus")); }); // the editor reads the file again
    await waitFor(() => marked(nameBox(), zh["tab.teams"]));
    expect(nameBox()).toHaveFocus();
  });

  test("a field gone with the focus in it holds nothing back: a gift list renamed with Enter, then a team switched on", async () => {
    const s = settings();
    s.gift_lists = [{ id: "g1", name: "G1", order: [...GIFT_KEYWORDS], want: [], keep: [], gorder: defaultGorder(), fusion_condition: "any" }];
    s.teams[0].game_team = 2;
    s.teams[0].enabled = false;
    const user = await openOn(s, zh["tab.gifts"]);
    await user.selectOptions(screen.getByRole("combobox", { name: zh["gl.list"] }), "g1");
    await user.click(screen.getByRole("button", { name: new RegExp("^" + zh["gl.opts"]) }));
    await user.click(screen.getByRole("menuitem", { name: new RegExp("^" + zh["gl.opt_rename"]) }));
    await user.type(screen.getByRole("textbox", { name: zh["gl.opt_rename"] }), "x{Enter}");
    expect(screen.queryByRole("textbox", { name: zh["gl.opt_rename"] })).toBeNull(); // gone, and no blur said so
    await user.click(tab(zh["tab.teams"])); // the focus goes to the tab bar, outside the editor's panel: no blur there either
    // a change that moves no focus: Ta switched on, now on Tb's TEAMS #2
    fireEvent.click(screen.getByRole("checkbox", { name: zh["team.enabled"] }));
    marked(slot(), zh["tab.teams"]);
  });

  test("a problem already shown keeps its marks while typing brings the typed field into it; the field is marked once left", async () => {
    const s = settings();
    s.teams[1].game_team = 1; // Ta and Tb share TEAMS #1
    s.teams.push({ ...newTeam(3, "Tc"), id: "c", game_team: 12 });
    const user = await openOn(s, zh["tab.teams"]);
    await pickInList(user, "Tc");
    await user.type(slot(), "{Backspace}"); // Tc's TEAMS #12 becomes #1
    expect(slot()).toHaveValue(1);
    expect(bad()).toEqual([true, true, false]);
    expect(slot()).not.toHaveAttribute("aria-invalid");
    await user.tab();
    expect(bad()).toEqual([true, true, true]);
    marked(slot(), zh["tab.teams"]);
  });

  test("typing a field out of one clash into another: the first goes at once, the second waits until the field is left", async () => {
    const s = settings();
    s.teams[1].game_team = 1; // Ta and Tb share TEAMS #1
    s.teams.push({ ...newTeam(3, "Tc"), id: "c", game_team: 12 });
    const user = await openOn(s, zh["tab.teams"]);
    await pickInList(user, "Tb");
    await user.type(slot(), "2"); // Tb's TEAMS #1 becomes #12, Tc's
    expect(bad()).toEqual([false, false, false]);
    unmarked(slot(), zh["tab.teams"]);
    await user.tab();
    expect(bad()).toEqual([false, true, true]);
    marked(slot(), zh["tab.teams"]);
  });

  test("typing a field from one shown clash into another: the first goes at once, the field joins the second once left", async () => {
    const s = settings();
    s.teams[1].game_team = 1; // Ta and Tb share TEAMS #1
    s.teams.push({ ...newTeam(3, "Tc"), id: "c", game_team: 12 }, { ...newTeam(4, "Td"), id: "d", game_team: 12 }); // Tc, Td #12
    const user = await openOn(s, zh["tab.teams"]);
    await pickInList(user, "Tb");
    await user.type(slot(), "2"); // Tb's TEAMS #1 becomes #12
    expect(bad()).toEqual([false, false, true, true]);
    expect(slot()).not.toHaveAttribute("aria-invalid");
    await user.tab();
    expect(bad()).toEqual([false, true, true, true]);
    marked(slot(), zh["tab.teams"]);
  });

  test("a schema error typed in stops the checks across teams: a shown clash goes, and once the error is typed away it is "
    + "new like any mark the typing makes, shown when the field is left", async () => {
    const s = settings();
    s.teams[1].game_team = 1; // Ta and Tb share TEAMS #1
    s.teams.push({ ...newTeam(3, "Tc"), id: "c", game_team: 4 });
    const user = await openOn(s, zh["tab.teams"]);
    await pickInList(user, "Tc");
    await user.type(slot(), "5"); // #45: above the game's 40
    expect(bad()).toEqual([false, false, false]);
    await user.keyboard("{Backspace}"); // #4 again
    expect(bad()).toEqual([false, false, false]);
    await user.tab();
    expect(bad()).toEqual([true, true, false]);
    expect(problem(/隊伍「Ta」、「Tb」都啟用，也都用 TEAMS #1/)).toBeInTheDocument();
  });

  test("a problem already shown stays while typing takes one of its fields out of it", async () => {
    const s = settings();
    s.teams.push({ ...newTeam(3, "Tc"), id: "c" });
    s.teams.forEach((x) => { x.game_team = 1; });
    const user = await openOn(s, zh["tab.teams"]);
    await user.type(slot(), "2"); // the first team leaves TEAMS #1 for #12; the other two still share #1
    expect(bad()).toEqual([false, true, true]);
    expect(problem(/隊伍「Tb」、「Tc」都啟用，也都用 TEAMS #1/)).toBeInTheDocument();
  });

  test("a problem the field already showed stays while it is typed in", async () => {
    const s = settings();
    s.teams[0].name = "";
    const user = await openOn(s, zh["tab.teams"]);
    marked(nameBox(), zh["tab.teams"]);
    await user.click(nameBox());
    await user.keyboard("{Backspace}");
    marked(nameBox(), zh["tab.teams"]);
  });

  test("a save refuses a problem still being typed, writes nothing and shows it", async () => {
    const user = await openOn(settings(), zh["tab.teams"]);
    await user.clear(nameBox());
    expect(ctrlS()).toBe(true);
    await waitFor(() => expect(plate()).toHaveTextContent(fill(zh["saveState.refused"], { n: 1 })));
    marked(nameBox(), zh["tab.teams"]);
    expect(file.saved).toEqual([]);
  });
});

describe("the problems block", () => {
  test("sits inside the tab panel, below the tab bar", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    await openOn(s, zh["tab.run"]);
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("alert"));
  });

  test("says each problem in the editor's language, with the teams' names; the bot's own words stay on hover", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    await openOn(s, zh["tab.run"]);
    const item = problem(/隊伍「Ta」、「Tb」都啟用，也都用 TEAMS #1/).closest("li")!;
    expect(item).not.toHaveTextContent("teams:");
    expect(item).toHaveAttribute("title", "teams: enabled teams 'Ta', 'Tb' all use TEAMS #1");
  });
});

describe("a field marked red", () => {
  const box = (role: "combobox" | "checkbox" | "textbox", label: Key) => () => screen.getByRole(role, { name: zh[label] });
  test.each([
    ["a choice of a team", (s: Settings) => { s.teams[0].theme_pack_plan = "gone"; }, "tab.teams", /隊伍「Ta」用的主題包方案已經不在了/,
      box("combobox", "team.theme_pack_plan")],
    ["a choice of the run options", (s: Settings) => { s.run.target_floor = 10; s.run.difficulty = "normal"; s.teams.forEach((x) => { x.hard_from_floor = 1; }); },
      "tab.run", /但難度是普通/, box("combobox", "run.difficulty")],
    ["a team's switch", (s: Settings) => { s.teams[0].guard_turns = 9; }, "tab.teams", /teams\/0\/guard_turns/, box("checkbox", "team.guard_turns")],
    ["a switch of the run options", (s: Settings) => { (s.run as Record<string, unknown>).auto_download = "yes"; }, "tab.run",
      /run\/auto_download/, box("checkbox", "run.auto_download")],
    ["a cell of an override table", (s: Settings) => { s.event_overrides = [{ question: "q", option: "a" }, { question: "q", option: "b" }]; },
      "tab.events", /事件覆寫有 2 列是同一個問題「q」/, () => screen.getAllByDisplayValue("q")[1]],
    ["a team's on switch", (s: Settings) => { Object.assign(s.teams[0], { enabled: "yes" }); }, "tab.teams", /teams\/0\/enabled/,
      box("checkbox", "team.enabled")],
    ["the gift search switch", (s: Settings) => { Object.assign(s.teams[0].gift_search, { enabled: "yes" }); }, "tab.teams",
      /teams\/0\/gift_search\/enabled/, box("checkbox", "gift.enabled")],
    ["a starlight plan's leftover switch", (s: Settings) => { Object.assign(s.starlight_plans[0], { convert_leftover: "yes" }); },
      "tab.starlight", /starlight_plans\/0\/convert_leftover/, box("checkbox", "starlight.convert_leftover")],
  ] as const)("%s is invalid to a screen reader, which reads the problem", async (_, change, start, text, control) => {
    const s = settings();
    change(s);
    await openOn(s, zh[start]);
    expect(control()).toHaveAttribute("aria-invalid", "true");
    expect(control()).toHaveAccessibleDescription(problem(text).textContent!);
  });

  test("a wrong team row says so without its colour: a cross, and words a screen reader reads, also while picked", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    await openOn(s, zh["tab.run"]);
    await userEvent.setup().click(tab(zh["tab.teams"]));
    const rows = [...document.querySelectorAll("aside li")] as HTMLElement[];
    expect(rows[0]).toHaveClass("selected");
    for (const row of rows) {
      expect(row.querySelector(".badmark")).toHaveTextContent("✕");
      expect(row).toHaveTextContent(zh.hasProblem);
    }
  });

  test("a field the checks pass is not", async () => {
    const s = settings();
    s.teams[0].theme_pack_plan = "gone";
    await openOn(s, zh["tab.teams"]);
    expect(nameBox()).not.toHaveAttribute("aria-invalid");
    expect(nameBox()).not.toHaveAttribute("aria-describedby");
  });
});

describe("clicking a problem", () => {
  test("opens its team on the teams tab and focuses the field", async () => {
    const s = settings();
    s.teams[1].theme_pack_plan = "gone";
    const user = await openOn(s, zh["tab.run"]);
    await user.click(problem(/隊伍「Tb」用的主題包方案已經不在了/));
    expect(tab(zh["tab.teams"])).toHaveAttribute("aria-selected", "true");
    expect(nameBox()).toHaveValue("Tb");
    expect(screen.getByRole("combobox", { name: zh["team.theme_pack_plan"] })).toHaveFocus();
  });

  test("focuses the plan choice of a team's deployment order", async () => {
    const s = settings();
    s.teams[1].deployment_order = { plan: "gone" };
    const user = await openOn(s, zh["tab.run"]);
    await user.click(problem(/隊伍「Tb」用的出戰順序方案已經不在了/));
    expect(nameBox()).toHaveValue("Tb");
    expect(document.activeElement).toHaveValue("gone");
  });

  test("opens the closed panel that holds it", async () => {
    const s = settings();
    s.teams[0].skill_replacement.sinners = [{ sinner: "Yi Sang", target: { s1: 3, s2: 2, s3: 2 }, s1_s3_first: true }];
    const user = await openOn(s, zh["tab.run"]);
    await user.click(problem(/Yi Sang：三個技能的目標合計 7/));
    expect(screen.getByText(new RegExp(zh["skill.title"]), { selector: "summary" }).closest("details")).toHaveAttribute("open");
    // the row itself: its first enabled control is its delete button, which Space would press
    expect(document.activeElement).toHaveAttribute("data-sinner", "Yi Sang");
  });

  test("with no field of its own, focuses its team's first field, not the list beside it", async () => {
    const s = settings();
    s.teams[1].id = "a"; // two teams with one id
    const user = await openOn(s, zh["tab.run"]);
    await user.click(problem(/隊伍裡有 2 個用同一個 id「a」/));
    expect(nameBox()).toHaveValue("Ta");
    expect(nameBox()).toHaveFocus();
  });

  test.each([
    ["a team's switch", (s: Settings) => { s.teams[0].guard_turns = 9; }, /teams\/0\/guard_turns/, "team.guard_turns"],
    ["a switch of the run options", (s: Settings) => { (s.run as Record<string, unknown>).auto_download = "yes"; },
      /run\/auto_download/, "run.auto_download"],
  ] as const)("focuses %s", async (_, change, text, label) => {
    const s = settings();
    change(s);
    const user = await openOn(s, zh["tab.daily"]);
    await user.click(problem(text));
    expect(screen.getByRole("checkbox", { name: zh[label] })).toHaveFocus();
  });

  test("opens its plan on the plan's tab and focuses the field", async () => {
    const s = settings();
    s.deployment_order_plans.push({ id: "d3", name: "D2", order: [...SINNERS] });
    const user = await openOn(s, zh["tab.teams"]);
    await user.click(problem(/出戰順序方案裡有 2 個都叫「D2」/));
    expect(tab(zh["tab.deployment"])).toHaveAttribute("aria-selected", "true");
    expect(nameBox()).toHaveValue("D2");
    expect(nameBox()).toHaveFocus();
  });

  test("focuses a field of the run options", async () => {
    const s = settings();
    s.run.target_floor = 10;
    s.run.difficulty = "normal";
    s.teams.forEach((x) => { x.hard_from_floor = 1; });
    const user = await openOn(s, zh["tab.teams"]);
    await user.click(problem(/但難度是普通/));
    expect(tab(zh["tab.run"])).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: zh["run.difficulty"] })).toHaveFocus();
  });

  test("shows its list on the gift list tab", async () => {
    const s = settings();
    s.gift_lists = [{ id: "g1", name: "G1", order: [...GIFT_KEYWORDS], want: [9780], keep: [9780], gorder: defaultGorder(), fusion_condition: "any" }];
    const user = await openOn(s, zh["tab.teams"]);
    await user.click(problem(/飾品清單「G1」/));
    expect(tab(zh["tab.gifts"])).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("g1");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveFocus();
  });
});

/** The user closes the window (its ✕, Alt+F4); true when the editor keeps it open. */
const requestClose = () => {
  let kept = false;
  act(() => { kept = file.keepOpen!(); });
  return kept;
};
/** The editor with the first team's name changed and not saved. */
const edited = async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
  return user;
};

describe("closing the window", () => {
  beforeEach(() => { file.text = JSON.stringify(settings()); });

  test("with unsaved changes, asks first and keeps the window open", async () => {
    await edited();
    expect(requestClose()).toBe(true);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(zh.closeAsk);
    expect(file.closed).toBe(0);
  });

  test("with nothing unsaved, closes without asking, also after a save", async () => {
    const user = await edited();
    await user.click(screen.getByRole("button", { name: zh.save }));
    await screen.findByText(zh.saved);
    expect(requestClose()).toBe(false);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("Close without saving closes it and writes nothing", async () => {
    const user = await edited();
    requestClose();
    await user.click(screen.getByRole("button", { name: zh.closeDiscard }));
    expect(file.closed).toBe(1);
    expect(file.saved).toEqual([]);
  });

  test.each([
    ["Cancel", (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole("button", { name: zh.cancel }))],
    ["Esc", (user: ReturnType<typeof userEvent.setup>) => user.keyboard("{Escape}")],
  ])("%s keeps the window open, the edits and the field the user was typing in", async (_, dismiss) => {
    const user = await edited();
    requestClose();
    await dismiss(user);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(file.closed).toBe(0);
    expect(nameBox()).toHaveValue("Ta!");
    await waitFor(() => expect(nameBox()).toHaveFocus());
  });

  test("starts on Save and close, and the page behind it takes no click or key", async () => {
    await edited();
    requestClose();
    expect(screen.getByRole("button", { name: zh.closeSave })).toHaveFocus();
    const behind = document.querySelectorAll("header, nav[role=tablist], main"); // the section index is a nav inside main
    expect(behind).toHaveLength(3);
    for (const el of behind) expect(el).toHaveAttribute("inert");
  });

  test("the window may destroy itself: without the permission no close goes through, with unsaved changes or none", () => {
    // Tauri 2 lets the page close the window once it listens to the close (manager/window.rs); core:default lacks destroy
    expect(capability.permissions).toContain("core:window:allow-destroy");
  });

  test("Save and close saves, then closes", async () => {
    const user = await edited();
    requestClose();
    await user.click(screen.getByRole("button", { name: zh.closeSave }));
    await waitFor(() => expect(file.closed).toBe(1));
    expect(JSON.parse(file.saved[0]).teams[0].name).toBe("Ta!");
  });

  test("Save and close with a save the checks refuse stays open and shows the problems", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    file.text = JSON.stringify(s);
    const user = await edited();
    requestClose();
    await user.click(screen.getByRole("button", { name: zh.closeSave }));
    expect(await screen.findByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(file.closed).toBe(0);
    expect(file.saved).toEqual([]);
  });

  test("the gift list tab's keys wait while it asks: a number picks no state, Esc closes only the prompt", async () => {
    const user = await edited();
    await user.click(tab(zh["tab.gifts"]));
    await user.type(screen.getByRole("searchbox", { name: zh["gl.search"] }), "Burn");
    const states = () => screen.getAllByRole("radio").map((r) => r.getAttribute("aria-checked"));
    const before = states();
    requestClose();
    await user.keyboard("2");
    expect(states()).toEqual(before);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("searchbox", { name: zh["gl.search"] })).toHaveValue("Burn");
  });
});

describe("reloading the page (F5, Ctrl+R)", () => {
  beforeEach(() => { file.text = JSON.stringify(settings()); });
  type Reload = [string, KeyboardEventInit];
  const KEYS: Reload[] = [
    ["F5", { key: "F5", code: "F5" }],
    ["Ctrl+R", { key: "r", code: "KeyR", ctrlKey: true }],
    ["Ctrl+F5", { key: "F5", code: "F5", ctrlKey: true }],
    ["Ctrl+Shift+R", { key: "R", code: "KeyR", ctrlKey: true, shiftKey: true }],
    ["the browser's Refresh key", { key: "BrowserRefresh", code: "BrowserRefresh" }],
    ["Ctrl+R on a Russian keyboard, where the R key types к", { key: "к", code: "KeyR", ctrlKey: true }],
  ];
  /** Press a reload key on the focused element; true when the editor kept the browser from reloading. */
  const press = (init: KeyboardEventInit) => {
    const e = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
    act(() => { (document.activeElement ?? document.body).dispatchEvent(e); });
    return e.defaultPrevented;
  };

  test.each(KEYS)("%s with unsaved changes reloads nothing and asks first", async (_, init) => {
    await edited();
    expect(press(init)).toBe(true);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(zh.reloadAsk);
    expect(file.reloaded).toBe(0);
  });

  test.each(KEYS)("%s with nothing unsaved is left to the browser, which reloads", async (_, init) => {
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    expect(press(init)).toBe(false);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("also after a save: nothing is unsaved then", async () => {
    const user = await edited();
    await user.click(screen.getByRole("button", { name: zh.save }));
    await screen.findByText(zh.saved);
    expect(press(KEYS[0][1])).toBe(false);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("other keys are not reloads: Ctrl+Alt+R, Alt+F5, Ctrl+E, and on Dvorak the key that types P", async () => {
    await edited();
    expect(press({ key: "r", code: "KeyR", ctrlKey: true, altKey: true })).toBe(false);
    expect(press({ key: "F5", code: "F5", altKey: true })).toBe(false);
    expect(press({ key: "e", code: "KeyE", ctrlKey: true })).toBe(false);
    expect(press({ key: "p", code: "KeyR", ctrlKey: true })).toBe(false); // KeyR is where Dvorak puts P
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("Reload without saving reloads and writes nothing", async () => {
    const user = await edited();
    press(KEYS[0][1]);
    await user.click(screen.getByRole("button", { name: zh.reloadDiscard }));
    expect(file.reloaded).toBe(1);
    expect(file.saved).toEqual([]);
  });

  test("Save and reload saves, then reloads", async () => {
    const user = await edited();
    press(KEYS[1][1]);
    await user.click(screen.getByRole("button", { name: zh.reloadSave }));
    await waitFor(() => expect(file.reloaded).toBe(1));
    expect(JSON.parse(file.saved[0]).teams[0].name).toBe("Ta!");
  });

  test("Save and reload with a save the checks refuse stays, shows the problems and does not reload", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    file.text = JSON.stringify(s);
    const user = await edited();
    press(KEYS[0][1]);
    await user.click(screen.getByRole("button", { name: zh.reloadSave }));
    expect(await screen.findByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(file.reloaded).toBe(0);
    expect(file.saved).toEqual([]);
  });

  test.each([
    ["Cancel", (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole("button", { name: zh.cancel }))],
    ["Esc", (user: ReturnType<typeof userEvent.setup>) => user.keyboard("{Escape}")],
  ])("%s keeps the page, the edits and the field the user was typing in", async (_, dismiss) => {
    const user = await edited();
    press(KEYS[0][1]);
    await dismiss(user);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(file.reloaded).toBe(0);
    expect(nameBox()).toHaveValue("Ta!");
    await waitFor(() => expect(nameBox()).toHaveFocus());
  });

  test("starts on Save and reload; a second press while it asks reloads nothing and keeps the one prompt", async () => {
    await edited();
    press(KEYS[0][1]);
    expect(screen.getByRole("button", { name: zh.reloadSave })).toHaveFocus();
    expect(press(KEYS[0][1])).toBe(true);
    expect(press(KEYS[1][1])).toBe(true);
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
    expect(file.reloaded).toBe(0);
  });

  test("closing the window while the reload prompt asks turns it into the close prompt", async () => {
    await edited();
    press(KEYS[0][1]);
    expect(requestClose()).toBe(true);
    expect(screen.getByRole("alertdialog")).toHaveTextContent(zh.closeAsk);
  });

  test("the english prompt names the reload too", () => {
    expect(TEXT.en_us.reloadAsk).toMatch(/reload/i);
    expect(TEXT.en_us.reloadSave).toMatch(/reload/i);
    expect(TEXT.en_us.reloadDiscard).toMatch(/reload/i);
  });
});

describe("Ctrl+S", () => {
  test("saves as the Save button does, also while typing in a field", async () => {
    file.text = JSON.stringify(settings());
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
    expect(ctrlS()).toBe(true);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).teams[0].name).toBe("Ta!");
    expect(await screen.findByText(zh.saved)).toBeInTheDocument();
  });

  test("is refused while a problem stands, and writes nothing", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    file.text = JSON.stringify(s);
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    expect(ctrlS()).toBe(true);
    await waitFor(() => expect(plate()).toHaveTextContent(fill(zh["saveState.refused"], { n: 1 })));
    expect(screen.getByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect(file.saved).toEqual([]);
  });

  test("held down, saves once: the key's repeats save nothing more", async () => {
    file.text = JSON.stringify(settings());
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
    ctrlS();
    expect([1, 2, 3].map(() => ctrlS({ repeat: true }))).toEqual([true, true, true]); // still not the browser's Save page
    await waitFor(() => expect(file.saved).toHaveLength(1));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(file.saved).toHaveLength(1);
  });

  test("while the close prompt asks, saves nothing: its buttons decide", async () => {
    file.text = JSON.stringify(settings());
    await edited();
    requestClose();
    expect(ctrlS()).toBe(true); // still not the browser's Save page
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(file.saved).toEqual([]);
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  test("on a Dvorak keyboard, the key that types O does not save", async () => {
    file.text = JSON.stringify(settings());
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    expect(ctrlS({ key: "o" })).toBe(false); // KeyS is where Dvorak puts O
  });
});
