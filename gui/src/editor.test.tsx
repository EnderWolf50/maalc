// The editor shell (App.tsx) around the tabs: what a tab switch keeps, the problems a refused save lists, and Ctrl+S.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import capability from "../src-tauri/capabilities/default.json";
import App from "./App";
import { TEXT, type Key } from "./i18n";
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

describe("a field marked red", () => {
  const box = (role: "combobox" | "checkbox" | "textbox", label: Key) => () => screen.getByRole(role, { name: zh[label] });
  test.each([
    ["a choice of a team", (s: Settings) => { s.teams[0].theme_pack_plan = "gone"; }, "tab.teams", /teams\/0\/theme_pack_plan/,
      box("combobox", "team.theme_pack_plan")],
    ["a choice of the run options", (s: Settings) => { s.run.target_floor = 10; s.run.difficulty = "normal"; s.teams.forEach((x) => { x.hard_from_floor = 1; }); },
      "tab.run", /run\/difficulty/, box("combobox", "run.difficulty")],
    ["a team's switch", (s: Settings) => { s.teams[0].guard_turns = 9; }, "tab.teams", /teams\/0\/guard_turns/, box("checkbox", "team.guard_turns")],
    ["a switch of the run options", (s: Settings) => { (s.run as Record<string, unknown>).auto_download = "yes"; }, "tab.run",
      /run\/auto_download/, box("checkbox", "run.auto_download")],
    ["a cell of an override table", (s: Settings) => { s.event_overrides = [{ question: "q", option: "a" }, { question: "q", option: "b" }]; },
      "tab.events", /event_overrides: question/, () => screen.getAllByDisplayValue("q")[1]],
    ["a team's on switch", (s: Settings) => { Object.assign(s.teams[0], { enabled: "yes" }); }, "tab.teams", /teams\/0\/enabled/,
      box("checkbox", "team.enabled")],
    ["the gift search switch", (s: Settings) => { Object.assign(s.teams[0].gift_search, { enabled: "yes" }); }, "tab.teams",
      /teams\/0\/gift_search\/enabled/, box("checkbox", "gift.enabled")],
    ["a starlight plan's leftover switch", (s: Settings) => { Object.assign(s.starlight_plans[0], { convert_leftover: "yes" }); },
      "tab.starlight", /starlight_plans\/0\/convert_leftover/, box("checkbox", "starlight.convert_leftover")],
  ] as const)("%s is invalid to a screen reader, which reads the problem", async (_, change, start, text, control) => {
    const s = settings();
    change(s);
    await blocked(s, zh[start]);
    expect(control()).toHaveAttribute("aria-invalid", "true");
    expect(control()).toHaveAccessibleDescription(problem(text).textContent!);
  });

  test("a field the checks pass is not", async () => {
    const s = settings();
    s.teams[0].theme_pack_plan = "gone";
    await blocked(s, zh["tab.teams"]);
    expect(nameBox()).not.toHaveAttribute("aria-invalid");
    expect(nameBox()).not.toHaveAttribute("aria-describedby");
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
    const behind = document.querySelectorAll("header, nav, main");
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

  test("other keys with a modifier are not reloads: Ctrl+Alt+R, Ctrl+E", async () => {
    await edited();
    expect(press({ key: "r", code: "KeyR", ctrlKey: true, altKey: true })).toBe(false);
    expect(press({ key: "e", code: "KeyE", ctrlKey: true })).toBe(false);
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
  /** Press Ctrl+S on the focused element; true when the editor kept the browser from its own Save page. */
  const ctrlS = (more: KeyboardEventInit = {}) => {
    const e = new KeyboardEvent("keydown", { key: "s", code: "KeyS", ctrlKey: true, bubbles: true, cancelable: true, ...more });
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
