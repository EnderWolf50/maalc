// Component tests of the teams tab's gift list choice (#296, covering #305 as well): the list dropdown, the main keyword the
// list decides, and the button that sends the user to the gift list tab with that list chosen.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { DEFAULT_LIST, mainKeyword } from "./gifts";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, defaultGorder, newSettings, newTeam, type GiftList, type Settings } from "./model";
import { renderEditor } from "./testing";
import { TeamsTab } from "./Teams";

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
