// The editor shell (App.tsx) around the tabs: what a tab switch keeps, the problems a refused save lists, and Ctrl+S.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, defaultGorder, defaultStarlight, newPackPlan, newSettings, newTeam, SINNERS, type Settings } from "./model";

const file = vi.hoisted(() => ({ text: "", saved: [] as string[] }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: (text: string) => { file.saved.push(text); file.text = text; return Promise.resolve(); },
  rootDir: () => Promise.resolve("root"),
}));
beforeEach(() => { file.saved = []; });

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

/** The editor on `s`, the tab `start` open, Save clicked: the problems show. */
async function blocked(s: Settings, start: string) {
  file.text = JSON.stringify(s);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("tab", { name: start }));
  await user.click(screen.getByRole("button", { name: zh.save }));
  return user;
}
const problem = (text: string | RegExp) => within(screen.getByRole("alert")).getByRole("button", { name: text });

describe("the problems block", () => {
  test("sits inside the tab panel, below the tab bar", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    await blocked(s, zh["tab.run"]);
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("alert"));
  });
});

describe("clicking a problem", () => {
  test("opens its team on the teams tab and focuses the field", async () => {
    const s = settings();
    s.teams[1].theme_pack_plan = "gone";
    const user = await blocked(s, zh["tab.run"]);
    await user.click(problem(/teams\/1\/theme_pack_plan/));
    expect(tab(zh["tab.teams"])).toHaveAttribute("aria-selected", "true");
    expect(nameBox()).toHaveValue("Tb");
    expect(screen.getByRole("combobox", { name: zh["team.theme_pack_plan"] })).toHaveFocus();
  });

  test("focuses the plan choice of a team's deployment order", async () => {
    const s = settings();
    s.teams[1].deployment_order = { plan: "gone" };
    const user = await blocked(s, zh["tab.run"]);
    await user.click(problem(/teams\/1\/deployment_order/));
    expect(nameBox()).toHaveValue("Tb");
    expect(document.activeElement).toHaveValue("gone");
  });

  test("opens the closed panel that holds it", async () => {
    const s = settings();
    s.teams[0].skill_replacement.sinners = [{ sinner: "Yi Sang", target: { s1: 3, s2: 2, s3: 2 }, s1_s3_first: true }];
    const user = await blocked(s, zh["tab.run"]);
    await user.click(problem(/skill_replacement\/sinners\/0\/target/));
    expect(screen.getByText(new RegExp(zh["skill.title"]), { selector: "summary" }).closest("details")).toHaveAttribute("open");
    // the row itself: its first enabled control is its delete button, which Space would press
    expect(document.activeElement).toHaveAttribute("data-sinner", "Yi Sang");
  });

  test("with no field of its own, focuses its team's first field, not the list beside it", async () => {
    const s = settings();
    s.teams[1].id = "a"; // two teams with one id
    const user = await blocked(s, zh["tab.run"]);
    await user.click(problem(/teams: id 'a'/));
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
    const user = await blocked(s, zh["tab.daily"]);
    await user.click(problem(text));
    expect(screen.getByRole("checkbox", { name: zh[label] })).toHaveFocus();
  });

  test("opens its plan on the plan's tab and focuses the field", async () => {
    const s = settings();
    s.deployment_order_plans.push({ id: "d3", name: "D2", order: [...SINNERS] });
    const user = await blocked(s, zh["tab.teams"]);
    await user.click(problem(/deployment_order_plans: name 'D2'/));
    expect(tab(zh["tab.deployment"])).toHaveAttribute("aria-selected", "true");
    expect(nameBox()).toHaveValue("D2");
    expect(nameBox()).toHaveFocus();
  });

  test("focuses a field of the run options", async () => {
    const s = settings();
    s.run.target_floor = 10;
    s.run.difficulty = "normal";
    s.teams.forEach((x) => { x.hard_from_floor = 1; });
    const user = await blocked(s, zh["tab.teams"]);
    await user.click(problem(/run\/difficulty/));
    expect(tab(zh["tab.run"])).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: zh["run.difficulty"] })).toHaveFocus();
  });

  test("shows its list on the gift list tab", async () => {
    const s = settings();
    s.gift_lists = [{ id: "g1", name: "G1", order: [...GIFT_KEYWORDS], want: [9780], keep: [9780], gorder: defaultGorder(), fusion_condition: "any" }];
    const user = await blocked(s, zh["tab.teams"]);
    await user.click(problem(/gift_lists\/0/));
    expect(tab(zh["tab.gifts"])).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("g1");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveFocus();
  });
});

describe("Ctrl+S", () => {
  /** Press Ctrl+S on the focused element; true when the editor kept the browser from its own Save page. */
  const ctrlS = () => {
    const e = new KeyboardEvent("keydown", { key: "s", code: "KeyS", ctrlKey: true, bubbles: true, cancelable: true });
    act(() => { (document.activeElement ?? document.body).dispatchEvent(e); });
    return e.defaultPrevented;
  };

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

  test("shows the problems when saving is blocked, and writes nothing", async () => {
    const s = settings();
    s.teams[1].game_team = 1;
    file.text = JSON.stringify(s);
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    expect(ctrlS()).toBe(true);
    expect(await screen.findByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect(file.saved).toEqual([]);
  });
});
