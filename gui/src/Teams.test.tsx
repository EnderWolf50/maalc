// Component tests of the teams tab's gift list choice (#296, covering #305 as well): the list dropdown, the main keyword the
// list decides, and the button that sends the user to the gift list tab with that list chosen.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { DEFAULT_LIST, mainKeyword } from "./gifts";
import { TEXT, fill } from "./i18n";
import { GIFT_KEYWORDS, defaultGorder, newSettings, newTeam, type GiftList, type Settings } from "./model";
import { expectLines, renderEditor } from "./testing";
import { TeamsTab, nextTeams } from "./Teams";
import { useEditor } from "./ui";

// The editor reads its settings through api.ts, which falls back to the browser's localStorage; the tests give it a file's text.
const file = vi.hoisted(() => ({ text: "" }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: () => Promise.resolve(),
  rootDir: () => Promise.resolve("root"),
}));

const zh = TEXT.zh_tw;
const kw = (k: string) => zh[`kw.${k}` as keyof typeof zh];
const list = (id: string, first: string): GiftList => ({
  id, name: id === "mine" ? "Mine" : "Other", order: [first, ...GIFT_KEYWORDS.filter((k) => k !== first)], want: [], keep: [], gorder: defaultGorder(),
  fusion_condition: "any",
});
const settings = (ref = "mine", language: Settings["language"] = "zh_tw"): Settings => ({
  ...newSettings(), language, gift_lists: [list("mine", "Bleed"), list("other", "Tremor")],
  teams: [{ ...newTeam(1, "T1"), gift_list: ref }],
});
const choice = () => screen.getByRole("combobox", { name: new RegExp(zh["team.gift_list"]) });
const mainOf = () => screen.getByText(zh["team.main_keyword"], { exact: false }).closest("small")!;

describe("the gift list choice", () => {
  test("the dropdown offers the default and the user's lists, with the team's chosen", () => {
    renderEditor(<TeamsTab />, settings());
    expect([...(choice() as HTMLSelectElement).options].map((o) => o.textContent)).toEqual([zh.defaultPlan, "Mine", "Other"]);
    expect(choice()).toHaveValue("mine");
  });

  test("choosing a list is stored on the team", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await r.user.selectOptions(choice(), "other");
    expect(r.settings().teams[0].gift_list).toBe("other");
    await r.user.selectOptions(choice(), "default");
    expect(r.settings().teams[0].gift_list).toBe("default");
  });

  test("the main keyword shown is the one the chosen list decides, and follows the choice", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    expect(mainOf()).toHaveTextContent(kw("Bleed"));
    await r.user.selectOptions(choice(), "other");
    expect(mainOf()).toHaveTextContent(kw("Tremor"));
    await r.user.selectOptions(choice(), "default");
    expect(mainOf()).toHaveTextContent(kw(mainKeyword(DEFAULT_LIST)));
  });

  test("Keywordless first in the list's order is skipped for the main keyword", () => {
    const s = settings();
    s.gift_lists[0].order = ["Keywordless", "Pierce", ...GIFT_KEYWORDS.filter((k) => k !== "Pierce" && k !== "Keywordless")];
    renderEditor(<TeamsTab />, s);
    expect(mainOf()).toHaveTextContent(kw("Pierce"));
  });

  test("the main keyword is a name in the settings' language", () => {
    renderEditor(<TeamsTab />, settings("mine", "en_us"));
    expect(screen.getByText(TEXT.en_us["team.main_keyword"], { exact: false }).closest("small")).toHaveTextContent("Bleed");
  });

  test("there is no main keyword dropdown any more", () => {
    renderEditor(<TeamsTab />, settings());
    expect(screen.queryByRole("combobox", { name: new RegExp("^" + zh["team.main_keyword"]) })).not.toBeInTheDocument();
  });
});

test("a team has no trial risk weight dropdown any more: every trial counts the same (the user, 2026-10-31)", () => {
  renderEditor(<TeamsTab />, settings());
  expect(screen.queryByText("試煉風險權重", { exact: false })).not.toBeInTheDocument();
});

describe("edit this list", () => {
  test("the button asks to show the team's list, which the default is too", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await r.user.click(screen.getByRole("button", { name: zh["team.edit_list"] }));
    await r.user.selectOptions(choice(), "default");
    await r.user.click(screen.getByRole("button", { name: zh["team.edit_list"] }));
    expect(r.opened()).toEqual(["mine", "default"]);
  });
});

describe("in the whole editor", () => {
  beforeEach(() => { file.text = ""; });

  test("the button opens the gift list tab with that list chosen", async () => {
    file.text = JSON.stringify(settings("other"));
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: zh["team.edit_list"] }));
    expect(screen.getByRole("tab", { name: zh["tab.gifts"] })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("other");
    expect(screen.getByRole("tab", { name: zh["tab.teams"] })).toHaveAttribute("aria-selected", "false");
  });

  test("a team on the default list opens the read-only default", async () => {
    file.text = JSON.stringify(settings("default"));
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: zh["team.edit_list"] }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("default"));
    expect(screen.getByText(zh["gl.readonly"])).toBeInTheDocument();
  });

  test("the chosen list stays when the user goes to another tab and comes back", async () => {
    file.text = JSON.stringify(settings("other"));
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: zh["team.edit_list"] }));
    await user.click(screen.getByRole("tab", { name: zh["tab.run"] }));
    await user.click(screen.getByRole("tab", { name: zh["tab.gifts"] }));
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("other");
  });
});

describe("deleting a team", () => {
  test("can be undone: the team comes back in its place, in the editor", async () => {
    const teams = ["a", "b", "c"].map((id, n) => ({ ...newTeam(n + 1, `T${id}`), id }));
    const r = renderEditor(<TeamsTab />, { ...newSettings(), language: "zh_tw", teams });
    await r.user.click(within(document.querySelector("aside")!).getByText("Tb"));
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    expect(r.settings().teams.map((x) => x.id)).toEqual(["a", "c"]);
    expect(screen.getByRole("status")).toHaveTextContent(fill(zh["undo.deleted"], { name: "Tb" }));
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect(r.settings().teams).toEqual(teams);
    expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Tb");
    expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
  });

  test("undone after the Agent moved a team, it goes back before the team that followed it, not to its old index", async () => {
    const teams = ["a", "b", "c"].map((id, n) => ({ ...newTeam(n + 1, `T${id}`), id }));
    function AgentClaimsA() { // what the editor holds once the Agent's requeue of a is read (#501)
      const { update } = useEditor();
      return <button onClick={() => update((s) => { s.teams.push(...s.teams.splice(0, 1)); })}>claim a</button>;
    }
    const r = renderEditor(<><TeamsTab /><AgentClaimsA /></>, { ...newSettings(), language: "zh_tw", teams });
    await r.user.click(within(document.querySelector("aside")!).getByText("Tb"));
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    await r.user.click(screen.getByRole("button", { name: "claim a" }));
    expect(r.settings().teams.map((x) => x.id)).toEqual(["c", "a"]);
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect(r.settings().teams.map((x) => x.id)).toEqual(["b", "c", "a"]);
  });
});

describe("the next run's team (as agent/team_queue.py pick_team takes it)", () => {
  const queue = (...teams: [string, boolean, string][]) =>
    teams.map(([id, enabled, usage], n) => ({ ...newTeam(n + 1, `T${id}`), id, enabled, usage }));
  const next = (difficulty: string, target: number, teams: ReturnType<typeof queue>) =>
    nextTeams({ ...newSettings(), run: { ...newSettings().run, difficulty, target_floor: target }, teams })
      .map((x) => `${x.difficulty}:${x.id}`);

  test("a fixed difficulty: the first enabled team whose usage fits; a disabled one is skipped", () => {
    const teams = queue(["a", false, "any"], ["b", true, "normal_only"], ["c", true, "any"]);
    expect(next("hard", 5, teams)).toEqual(["hard:c"]);
    expect(next("normal", 5, teams)).toEqual(["normal:b"]);
  });

  test("auto: one team for each difficulty a run can begin on; past floor 5 only HARD", () => {
    const teams = queue(["a", true, "hard_only"], ["b", true, "any"]);
    expect(next("auto", 5, teams)).toEqual(["hard:a", "normal:b"]);
    expect(next("auto", 10, teams)).toEqual(["hard:a"]);
  });

  test("no team fits: none is next", () => {
    expect(next("hard", 5, queue(["a", true, "normal_only"]))).toEqual([]);
  });

  test("the queue marks the next team", () => {
    const teams = queue(["a", false, "any"], ["b", true, "any"]);
    renderEditor(<TeamsTab />, { ...newSettings(), language: "zh_tw", run: { ...newSettings().run, difficulty: "hard" }, teams });
    const rows = within(document.querySelector("aside")!).getAllByRole("listitem");
    expect(rows[1]).toHaveTextContent(zh["queue.next"]);
    expect(rows[0]).not.toHaveTextContent(zh["queue.next"]);
  });
});

test("the team page's long notes show one topic to a line", () => {
  renderEditor(<TeamsTab />, settings());
  const keys = ["team.gift_list_note", "team.hard_from_floor_note", "team.min_alive_note", "keep.sell_vestiges_note", "skill.note"] as const;
  for (const key of keys) expectLines(zh[key]);
});
