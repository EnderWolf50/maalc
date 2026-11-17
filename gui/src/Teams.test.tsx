// Component tests of the teams tab's gift list choice (#296, covering #305 as well): the list dropdown, the main keyword the
// list decides, and the button that sends the user to the gift list tab with that list chosen.
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { bufIconUrl, iconUrl } from "./giftCatalog";
import { DEFAULT_LIST, mainKeyword } from "./gifts";
import { TEXT, fill } from "./i18n";
import { GIFT_KEYWORDS, GRACES, SEARCH_GIFTS, SEARCH_TABS, SINNERS, defaultGorder, newSettings, newTeam, starlightCost, type GiftList, type Settings } from "./model";
import { contrast, cssRules, cssValueOf, expectLines, filterEffect, linear, pickInList, queuedTeams, renderEditor, sideList } from "./testing";
import css from "./index.css?raw";
import mainTsx from "./main.tsx?raw";
import { TeamsTab } from "./Teams";
import { useEditor } from "./ui";

// The editor reads its settings through api.ts, which falls back to the browser's localStorage; the tests give it a file's text.
const file = vi.hoisted(() => ({ text: "", resets: [] as string[] }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  resetTeamTimes: (id: string) => { file.resets.push(id); return Promise.resolve(); },
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

describe("Reset time records", () => {
  beforeEach(() => { file.resets = []; });

  test("a question left open goes with its team: the next team picked is not asked, and gets no marker", async () => {
    const s = settings();
    s.teams.push({ ...newTeam(2, "T2"), id: "t2" });
    const r = renderEditor(<TeamsTab />, s);
    await r.user.click(screen.getByRole("button", { name: zh.resetTimes }));
    await pickInList(r.user, "T2");
    expect(screen.queryByRole("group", { name: zh.resetTimes })).toBeNull();
    await pickInList(r.user, "T1");
    expect(screen.queryByRole("group", { name: zh.resetTimes })).toBeNull();
    expect(file.resets).toEqual([]);
  });

  test("the note of a reset stays with its team: the next team picked does not show it, the way back does", async () => {
    const s = settings();
    s.teams.push({ ...newTeam(2, "T2"), id: "t2" });
    const r = renderEditor(<TeamsTab />, s);
    await r.user.click(screen.getByRole("button", { name: zh.resetTimes }));
    await r.user.click(screen.getByRole("button", { name: zh.resetGo }));
    await screen.findByText(zh.resetDone);
    await pickInList(r.user, "T2");
    expect(screen.queryByText(zh.resetDone)).toBeNull();
    await pickInList(r.user, "T1");
    expect(screen.getByText(zh.resetDone)).toBeTruthy();
  });

  test("asks in the page, not in a browser dialog; Cancel writes nothing, the confirm writes the marker", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const r = renderEditor(<TeamsTab />, settings());
    await r.user.click(screen.getByRole("button", { name: zh.resetTimes }));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: zh.resetTimes })).toHaveTextContent(zh.resetConfirm);
    expect(screen.getByRole("button", { name: zh.cancel })).toHaveFocus(); // the marker cannot be taken back: Enter keeps things
    await r.user.click(screen.getByRole("button", { name: zh.cancel }));
    expect(file.resets).toEqual([]);
    expect(screen.queryByRole("group", { name: zh.resetTimes })).toBeNull();
    await r.user.click(screen.getByRole("button", { name: zh.resetTimes }));
    await r.user.click(screen.getByRole("button", { name: zh.resetGo }));
    expect(file.resets).toEqual([r.settings().teams[0].id]);
    expect(await screen.findByText(zh.resetDone)).toBeInTheDocument();
  });
});

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
    render(<App start="teams" />);
    await user.click(await screen.findByRole("button", { name: zh["team.edit_list"] }));
    expect(screen.getByRole("tab", { name: zh["tab.gifts"] })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("other");
    expect(screen.getByRole("tab", { name: zh["tab.teams"] })).toHaveAttribute("aria-selected", "false");
  });

  test("a team on the default list opens the read-only default", async () => {
    file.text = JSON.stringify(settings("default"));
    const user = userEvent.setup();
    render(<App start="teams" />);
    await user.click(await screen.findByRole("button", { name: zh["team.edit_list"] }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("default"));
    expect(screen.getByText(zh["gl.readonly"])).toBeInTheDocument();
  });

  test("the chosen list stays when the user goes to another tab and comes back", async () => {
    file.text = JSON.stringify(settings("other"));
    const user = userEvent.setup();
    render(<App start="teams" />);
    await user.click(await screen.findByRole("button", { name: zh["team.edit_list"] }));
    await user.click(screen.getByRole("tab", { name: zh["tab.events"] }));
    await user.click(screen.getByRole("tab", { name: zh["tab.gifts"] }));
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("other");
  });
});

describe("deleting a team", () => {
  const teams = ["a", "b", "c"].map((id, n) => ({ ...newTeam(n + 1, `T${id}`), id }));
  function AgentClaimsA() { // what the editor holds once the Agent's requeue of a is read (#501, #803)
    const { update } = useEditor();
    return <button onClick={() => update((s) => { s.team_queue.push(...s.team_queue.splice(0, 1)); })}>claim a</button>;
  }

  test("can be undone: the team comes back in its place, in the editor", async () => {
    const r = renderEditor(<TeamsTab />, { ...newSettings(), language: "zh_tw", ...queuedTeams(teams) });
    await pickInList(r.user, "Tb");
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    expect(r.settings().teams.map((x) => x.id)).toEqual(["a", "c"]);
    expect(screen.getByRole("status")).toHaveTextContent(fill(zh["undo.deleted"], { name: "Tb" }));
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect(r.settings().teams).toEqual(teams);
    expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Tb");
    expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
  });

  test("undone after the Agent moved the queue, it goes back there before the team that followed it, not to its old index", async () => {
    const r = renderEditor(<><TeamsTab /><AgentClaimsA /></>, { ...newSettings(), language: "zh_tw", ...queuedTeams(teams) });
    await pickInList(r.user, "Tb");
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    await r.user.click(screen.getByRole("button", { name: "claim a" }));
    expect(r.settings().team_queue).toEqual(["c", "a"]);
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect([r.settings().teams.map((x) => x.id), r.settings().team_queue]).toEqual([["a", "b", "c"], ["b", "c", "a"]]);
  });

  test("the last team of the queue, undone after the Agent moved the queue, goes back last", async () => {
    const r = renderEditor(<><TeamsTab /><AgentClaimsA /></>, { ...newSettings(), language: "zh_tw", ...queuedTeams(teams) });
    await pickInList(r.user, "Tc");
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    await r.user.click(screen.getByRole("button", { name: "claim a" }));
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["b", "a", "c"]);
  });
});

test("the team page says what a target past floor 5 asks of a team, which the Mirror Dungeon task's start checks (#779)", () => {
  // the target floor is the Mirror Dungeon task's option, which its start checks: a save is not refused over it, so the
  // rule shows beside usage
  renderEditor(<TeamsTab />, settings());
  expect(screen.getByText(zh["team.target_floor_note"])).toBeVisible();
  // each names the option where the Run tab shows it (#814)
  for (const key of ["team.target_floor_note", "team.min_alive_note", "team.hard_from_floor_note"] as const) {
    expect(zh[key]).toContain("「執行」分頁鏡牢");
    expect(TEXT.en_us[key]).toContain("Mirror Dungeon in the Run tab");
  }
});

test("the team page's long notes show one topic to a line", () => {
  renderEditor(<TeamsTab />, settings());
  const keys = ["team.gift_list_note", "team.hard_from_floor_note", "team.min_alive_note", "keep.sell_vestiges_note", "skill.note"] as const;
  for (const key of keys) expectLines(zh[key]);
});

describe("a team on a starlight plan", () => {
  const levels = GRACES.map(() => "none");
  levels[2] = "plus";
  levels[0] = "base";
  const onPlan = (): Settings => {
    const s = settings();
    s.starlight_plans = [{ id: "p1", name: "Cheap", levels, priority: [3, 1, 2, 4, 5, 6, 7, 8, 9, 10], convert_leftover: false }];
    s.teams[0].starlight = { plan: "p1" };
    return s;
  };

  test("shows the plan's picks in buying order with their level and the total; the cards are folded away", () => {
    renderEditor(<TeamsTab />, onPlan());
    const receipt = document.querySelector(".receipt")!;
    expect([...receipt.querySelectorAll("li")].map((li) => li.textContent)).toEqual([`1${GRACES[2].zh}+`, `2${GRACES[0].zh}`]);
    expect(receipt).toHaveTextContent(`★ ${starlightCost(levels)}`);
    expect(document.querySelector(".starlight")!.closest("details")).not.toHaveAttribute("open");
  });

  test("a plan that buys no grace says so on the receipt, not an empty line", () => {
    const s = onPlan();
    s.starlight_plans[0].levels = GRACES.map(() => "none");
    renderEditor(<TeamsTab />, s);
    const receipt = document.querySelector(".receipt")!;
    expect(receipt.querySelector("ol")).toBeNull();
    expect(receipt).toHaveTextContent(zh["starlight.none"]);
    expect(receipt).toHaveTextContent("★ 0");
  });

  test("a team's own starlight shows the cards to edit, no receipt", () => {
    renderEditor(<TeamsTab />, settings());
    expect(document.querySelector(".receipt")).toBeNull();
    expect(document.querySelector(".starlight")!.closest("details")).toBeNull();
  });
});

test("the queue names a team that is off and a team kept to one difficulty", () => {
  const s = settings();
  s.teams = [{ ...newTeam(1, "T1") }, { ...newTeam(2, "T2"), enabled: false, usage: "hard_only" }];
  renderEditor(<TeamsTab />, s);
  const [first, second] = sideList().getAllByRole("listitem");
  expect(first).not.toHaveTextContent(zh["team.disabled"]);
  expect(first).not.toHaveTextContent(zh["usage.hard_only"]);
  expect(second).toHaveTextContent(zh["team.disabled"]);
  expect(second).toHaveTextContent(zh["usage.hard_only"]);
});

test("a team on a deployment order plan says where that plan is changed", () => {
  const s = settings();
  s.deployment_order_plans = [{ id: "d1", name: "Bleed order", order: [...SINNERS] }];
  s.teams[0].deployment_order = { plan: "d1" };
  renderEditor(<TeamsTab />, s);
  expect(screen.getByText(fill(zh["team.plan_note"], { name: "Bleed order", tab: zh["tab.deployment"], custom: zh.custom }))).toBeInTheDocument();
});

describe("the E.G.O Gift Search keyword tabs", () => {
  const tabs = () => within(document.querySelector(".gift-search")!).getAllByRole("tab");

  test("name the keyword in the GUI's language and open on the list's main keyword", () => {
    renderEditor(<TeamsTab />, settings());
    expect(tabs().map((b) => b.textContent)).toEqual(SEARCH_TABS.map(kw));
    const on = tabs().find((b) => b.getAttribute("aria-selected") === "true")!;
    expect(on).toHaveTextContent(kw("Bleed"));
  });

  test("follow the team picked: the next team's grid opens on its own list's main keyword", async () => {
    const s = settings();
    s.teams.push({ ...newTeam(2, "T2"), id: "t2", gift_list: "other" });
    const r = renderEditor(<TeamsTab />, s);
    await pickInList(r.user, "T2");
    const on = tabs().find((b) => b.getAttribute("aria-selected") === "true")!;
    expect(on).toHaveTextContent(kw("Tremor"));
  });

  test("walk with the arrow keys, one tab stop for the row", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    const at = SEARCH_TABS.indexOf("Bleed");
    expect(tabs().map((b) => b.getAttribute("tabindex"))).toEqual(SEARCH_TABS.map((_, i) => (i === at ? "0" : "-1")));
    tabs()[at].focus();
    await r.user.keyboard("{ArrowRight}");
    expect(tabs()[at + 1]).toHaveAttribute("aria-selected", "true");
    expect(tabs()[at + 1]).toHaveFocus();
    await r.user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(tabs()[at - 1]).toHaveAttribute("aria-selected", "true");
    expect(tabs()[at - 1]).toHaveFocus();
    await r.user.keyboard("{End}");
    expect(tabs()[SEARCH_TABS.length - 1]).toHaveFocus();
    await r.user.keyboard("{ArrowRight}"); // round at the end, as the main tabs
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs()[0]).toHaveFocus();
  });
});

describe("the E.G.O Gift Search gifts: icon first, details on hover (#721)", () => {
  // Dust to Dust (9053), Burn III: its names, and the start of its effect in each language (gift_effects.json)
  const DUST = { id: 9053, zh: "土歸土", en: "Dust to Dust", zhEffect: "波次的首個回合開始時，使全體敵方單位", enEffect: "First Turn Start of a wave: inflict 5 Burn Potency" };
  const burnFirst = (language: Settings["language"] = "zh_tw"): Settings => ({ ...settings("mine", language), gift_lists: [list("mine", "Burn")] });
  const tile = (name: string) => within(document.querySelector(".gift-search")!).getByRole("button", { name: new RegExp(name) });
  const card = () => screen.queryByRole("dialog", { name: /./ });

  test("a gift shows its icon first and its name under it; its English name and effect are in the gift list's hover card", async () => {
    const r = renderEditor(<TeamsTab />, burnFirst());
    const t = tile(DUST.zh);
    expect(t.firstElementChild).toHaveAttribute("src", iconUrl(DUST.id));
    expect([...t.children].filter((x) => !x.matches(".sr-only")).map((x) => x.textContent).join("")).toBe(DUST.zh); // nothing else shows
    expect(card()).toBeNull();
    await r.user.hover(t);
    expect(card()).toHaveAccessibleName(DUST.zh);
    expect(card()).toHaveClass("gl-tip");
    expect(within(card()!).getByText(DUST.en)).toBeInTheDocument();
    expect(card()).toHaveTextContent(DUST.zhEffect);
    // as on the gift list tab's card (#764): each Burn its status icon, then its name
    expect(within(card()!).getAllByText("燒傷").map((x) => x.previousElementSibling?.getAttribute("src"))).toEqual([
      bufIconUrl("Combustion"), bufIconUrl("Combustion"), bufIconUrl("Combustion"), bufIconUrl("Combustion")]);
    await r.user.unhover(t);
    await waitFor(() => expect(card()).toBeNull());
  });

  test("Esc closes the card, as on the gift list tab", async () => {
    const r = renderEditor(<TeamsTab />, burnFirst());
    act(() => tile(DUST.zh).focus());
    expect(card()).not.toBeNull();
    await r.user.keyboard("{Escape}");
    expect(card()).toBeNull();
  });

  test("in English the card names the gift once and gives the English effect", async () => {
    const r = renderEditor(<TeamsTab />, burnFirst("en_us"));
    await r.user.hover(tile(DUST.en));
    expect(card()).toHaveAccessibleName(DUST.en);
    expect(within(card()!).getAllByText(DUST.en)).toHaveLength(1);
    expect(card()).toHaveTextContent(DUST.enEffect);
  });

  test("with 3 picked, a gift that cannot be added still opens its card, which says why; a screen reader hears it too", async () => {
    const s = burnFirst();
    s.teams[0].gift_search.gifts = SEARCH_GIFTS.filter((g) => g.keyword === "Burn").slice(1, 4).map((g) => ({ keyword: g.keyword, tier: g.tier, name: g.en }));
    const r = renderEditor(<TeamsTab />, s);
    const t = tile(DUST.zh);
    expect(t).toBeDisabled();
    expect(t).toHaveAccessibleDescription(zh["gift.full"]);
    expect(t).not.toHaveAttribute("title"); // the native tooltip would sit over the card
    await r.user.hover(t);
    expect(card()).toHaveAccessibleName(DUST.zh);
    expect(card()).toHaveTextContent(DUST.zhEffect);
    expect(card()).toHaveTextContent(zh["gift.full"]);
  });

  test("keyboard and screen reader stay as they were: both names are the button's name, focus shows the card, a click picks it with its number", async () => {
    const r = renderEditor(<TeamsTab />, burnFirst());
    const t = tile(DUST.zh);
    expect(t).toHaveAccessibleName(new RegExp(`${DUST.zh}.*${DUST.en}`));
    act(() => t.focus());
    expect(card()).toHaveAccessibleName(DUST.zh);
    await r.user.click(t);
    expect(r.settings().teams[0].gift_search.gifts).toEqual([{ keyword: "Burn", tier: 3, name: DUST.en }]);
    expect(t).toHaveAttribute("aria-pressed", "true");
    expect(t.querySelector(".rank")).toHaveTextContent("1");
  });
});

describe("the deployment order tiles (#718)", () => {
  // 7 deployed, 2 backups; Don Quixote, Meursault and Gregor are left out
  const order = ["Ryōshū", "Yi Sang", "Faust", "Hong Lu", "Ishmael", "Rodion", "Outis", "Heathcliff", "Sinclair"];
  const ordered = () => {
    const s = settings();
    s.teams[0].deployment_order = { custom: order };
    return s;
  };
  const tile = (name: string) => within(document.querySelector<HTMLElement>('[data-section="order"]')!).getByRole("button", { name: new RegExp(name) });
  // each sinner's default identity, LCB Sinner (the static data's BASE_APPEARANCE personality, 1.118.1)
  const DEFAULT_IDENTITY: Record<string, number> = {
    "Yi Sang": 10101, Faust: 10201, "Don Quixote": 10301, "Ryōshū": 10401, Meursault: 10501, "Hong Lu": 10601,
    Heathcliff: 10701, Ishmael: 10801, Rodion: 10901, Sinclair: 11001, Outis: 11101, Gregor: 11201,
  };

  test("each tile shows its sinner's default identity card, in the order or not", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of SINNERS) {
      expect(tile(s).querySelector("img")?.getAttribute("src")).toMatch(new RegExp(`sinner_cards/${DEFAULT_IDENTITY[s]}\\.webp$`));
    }
  });

  const LEFT_OUT = ["Don Quixote", "Meursault", "Gregor"];
  const artLook = (name: string, hover = false) => filterEffect(cssValueOf(css, tile(name).querySelector("img")!, "filter", hover));

  // #750, as the formation screen draws them (tests/screens/Formation.png, measured in #744): a selected card's art at 0.42-0.48
  // of its light in red and green, 0.36-0.43 in blue, a card left out grey at 0.99 of its light.
  test("a sinner in the order shows its card darkened as the game's, one left out grey at full light", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of LEFT_OUT) expect(tile(s)).toHaveClass("out");
    for (const s of order) expect(tile(s)).not.toHaveClass("out");
    for (const s of order) {
      expect(artLook(s).light).toBeGreaterThanOrEqual(0.4);
      expect(artLook(s).light).toBeLessThanOrEqual(0.5);
    }
    for (const s of LEFT_OUT) expect(artLook(s)).toEqual({ light: 1, colour: 0 });
  });

  // #756: the glow is its ring alone (tools/sinner_cards.py ring_only), nothing over the art, so the art's filter alone sets its
  // light. The formation screen draws a white pixel of a selected card at R 0.47-0.50, G 0.46-0.49, B 0.44-0.46 (#754's fit),
  // relative luminance 0.179-0.200.
  test("a white pixel of a card in the order comes out at the game's light", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of order) {
      expect(artLook(s).colour).toBe(1);
      expect(linear(artLook(s).light)).toBeGreaterThanOrEqual(0.179);
      expect(linear(artLook(s).light)).toBeLessThanOrEqual(0.2);
    }
  });

  // #761: the formation screen draws a card in the order with its frame and ring at half their light. Along the card's edges,
  // the ring's crest reads R 0.50-0.51 of the focused card's (Lamp, at full light) on all 10 cards in the order of
  // tests/screens/Formation.png: the channel the sprite has full in both, so the light itself; the slot keeps a 0.5 grey for
  // its graphics. Its number and its plate stay at full light, so they read first.
  const frameLook = (name: string, hover = false) => filterEffect(cssValueOf(css, tile(name), "filter", hover, "::after"));
  test("a card in the order has its frame and ring at half their light, as the game's, its number and plate at full", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of order) {
      expect(frameLook(s).light).toBeGreaterThanOrEqual(0.45);
      expect(frameLook(s).light).toBeLessThanOrEqual(0.55);
      expect(frameLook(s).colour).toBe(1);
      for (const part of [".num", ".banner"]) {
        const el = tile(s).querySelector(part)!;
        expect(filterEffect(cssValueOf(css, el, "filter")).light).toBe(1);
        expect(cssValueOf(css, el, "opacity")).toBeUndefined();
      }
    }
    for (const s of LEFT_OUT) expect(frameLook(s)).toEqual({ light: 1, colour: 1 });
  });

  // The game's name dims with its frame too, but a name must read: it dims only as far as it keeps 4.5:1 over a white pixel
  // of its art, darkened as its card's, under the shade's lightest 68 % (index.css, .sinner::before). The tile keeps the
  // game's ink in both themes: the light theme sets none of these colours.
  const hex = (name: string) => {
    expect(css.match(new RegExp(`${name}:`, "g"))).toHaveLength(1);
    return css.match(new RegExp(`${name}:\\s*#([0-9a-f]{6})`, "i"))![1].match(/../g)!.map((c) => parseInt(c, 16) / 255);
  };
  test("the name of a card in the order dims with its frame, as far as it keeps 4.5:1 over white art; one left out's stays", () => {
    renderEditor(<TeamsTab />, ordered());
    const nameLook = (s: string) => filterEffect(cssValueOf(css, tile(s).querySelector(".name")!, "filter"));
    for (const s of LEFT_OUT) expect(nameLook(s)).toEqual({ light: 1, colour: 1 });
    for (const s of order) {
      expect(nameLook(s).light).toBeLessThan(1);
      const ink = hex("--art-name").map((c) => c * nameLook(s).light);
      const under = hex("--art-shade").map((c) => 0.68 * c + 0.32 * artLook(s).light);
      expect(contrast(ink, under)).toBeGreaterThanOrEqual(4.5);
    }
  });

  test("the pointer over a sinner left out gives it some colour back, at the same light, to say a click puts it in", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of LEFT_OUT) {
      expect(artLook(s, true).colour).toBeGreaterThan(artLook(s).colour);
      expect(artLook(s, true).colour).toBeLessThan(1);
      expect(artLook(s, true).light).toBe(1);
    }
  });

  test("the pointer over a sinner lights its frame, in the order or not, and nothing behind the card: no button fill round the frame's edge", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of ["Ryōshū", "Sinclair", "Gregor"]) {
      expect(cssValueOf(css, tile(s), "background", true)).toBe("none");
      expect(frameLook(s, true).light).toBeGreaterThanOrEqual(1.3 * frameLook(s).light);
    }
  });

  test("a team on a plan follows the same rule, quieter than a grid one edits: every card has less light, the order's less colour", () => {
    renderEditor(<TeamsTab />, ordered());
    const editable = Object.fromEntries(SINNERS.map((s) => [s, artLook(s)]));
    const editableFrame = Object.fromEntries(SINNERS.map((s) => [s, frameLook(s)]));
    cleanup();
    const onPlan = settings();
    onPlan.deployment_order_plans = [{ id: "d1", name: "Bleed order", order }];
    onPlan.teams[0].deployment_order = { plan: "d1" };
    renderEditor(<TeamsTab />, onPlan);
    for (const s of SINNERS) expect(tile(s)).toBeDisabled();
    for (const s of SINNERS) expect(artLook(s).light).toBeLessThan(editable[s].light);
    for (const s of order) expect(artLook(s).colour).toBeLessThan(editable[s].colour);
    for (const s of LEFT_OUT) expect(artLook(s).colour).toBe(0);
    // the same rule: the order's cards darker than the ones left out; every frame and its ring with less colour, none lighter
    for (const s of order) for (const out of LEFT_OUT) expect(artLook(s).light).toBeLessThan(artLook(out).light);
    for (const s of SINNERS) {
      expect(frameLook(s).colour).toBeLessThan(editableFrame[s].colour);
      expect(frameLook(s).light).toBeLessThanOrEqual(editableFrame[s].light);
    }
    for (const s of order) for (const out of LEFT_OUT) expect(frameLook(s).light).toBeLessThan(frameLook(out).light);
  });

  // #732: the tile is the game's formation card. Its frame is the game's 162 x 230 sprite (tools/sinner_cards.py FRAME_PARTS).
  const rulesOf = (pick: (selector: string) => boolean) => cssRules(css).filter((r) => pick(r.selector)).map((r) => r.body).join("\n");

  test("each tile is the formation card: the game's frame round the art, in the frame's shape, at most the frame's size", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of SINNERS) expect(tile(s)).toHaveClass("sinner");
    expect(rulesOf((x) => x === ".sinner")).toMatch(/aspect-ratio:\s*162\s*\/\s*230/);
    expect(rulesOf((x) => x === ".sinners")).toMatch(/grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*162px\)\)/);
    expect(rulesOf((x) => /^\.sinner::after$/.test(x))).toMatch(/--sprite-sinner-frame-frame/);
  });

  test("a sinner in the order has its number and the game's plate, 上場 red and 替補 teal, under the game's glow; one left out has none", () => {
    renderEditor(<TeamsTab />, ordered());
    expect(tile("Ryōshū")).toHaveClass("deployed");
    expect(tile("Ryōshū").querySelector(".num")).toHaveTextContent("1");
    expect(tile("Ryōshū").querySelector(".banner")).toHaveTextContent(zh["order.deployed"]);
    expect(tile("Sinclair")).toHaveClass("backup");
    expect(tile("Sinclair").querySelector(".num")).toHaveTextContent("9");
    expect(tile("Sinclair").querySelector(".banner")).toHaveTextContent(zh["order.backup"]);
    for (const s of ["Don Quixote", "Meursault", "Gregor"]) expect(tile(s).querySelector(".num, .banner")).toBeNull();
    expect(rulesOf((x) => x.includes(".sinner.deployed .banner"))).toMatch(/--sprite-sinner-frame-plate-deployed/);
    expect(rulesOf((x) => x.includes(".sinner.backup .banner"))).toMatch(/--sprite-sinner-frame-plate-backup/);
    const glow = cssRules(css).filter((r) => r.body.includes("--sprite-sinner-frame-glow")).map((r) => r.selector).join(" ");
    expect(glow).toMatch(/\.sinner\.deployed::after/);
    expect(glow).toMatch(/\.sinner\.backup::after/);
  });

  test("the number is drawn as the formation screen's (#741): no dark outline, a soft rim, a weight the app bundles", () => {
    const num = rulesOf((x) => x === ".sinner .num");
    expect(num).not.toMatch(/text-stroke/);
    expect(num).toMatch(/filter:[^;]*drop-shadow/);
    const weight = num.match(/font:\s*(\d{3})\s/)?.[1];
    expect(weight).toBeDefined();
    expect(mainTsx).toContain(`@fontsource/barlow-condensed/latin-${weight}.css`);
  });

  test("the name sits at the foot as the game writes an identity's, in the sinner's own spelling", () => {
    renderEditor(<TeamsTab />, ordered());
    expect(tile("Ryōshū").querySelector(".name")).toHaveTextContent(/^Ryōshū$/);
    expect(rulesOf((x) => x === ".sinner .name")).not.toMatch(/text-transform:\s*uppercase/);
  });
});

describe("the section index", () => {
  test("sits above the team editor, not under the team list, so a long list never pushes it away", () => {
    const s = settings();
    for (let n = 2; n <= 30; n++) s.teams.push({ ...newTeam(n, `T${n}`), id: `t${n}` });
    renderEditor(<TeamsTab />, s);
    const jump = screen.getByRole("navigation", { name: zh["team.sections"] });
    expect(jump.closest("aside")).toBeNull();
    const editor = document.querySelector(".team")!;
    expect(jump.compareDocumentPosition(editor) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test("its links follow the page's sections from top to bottom", () => {
    renderEditor(<TeamsTab />, settings());
    const jump = screen.getByRole("navigation", { name: zh["team.sections"] });
    const headings = [...document.querySelectorAll<HTMLElement>(".team [data-section]")]
      .map((el) => el.querySelector(":scope > legend, :scope > summary")!.textContent!.replace(/\s*\(\d+\)$/, ""));
    expect(headings).toHaveLength(6);
    expect(within(jump).getAllByRole("button").map((b) => b.textContent)).toEqual(headings);
  });

  test("jumps to a section: a closed panel opens, and its summary takes the focus", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    const jump = screen.getByRole("navigation", { name: zh["team.sections"] });
    const gift = screen.getByText(zh["gift.title"], { exact: false, selector: "summary" });
    expect(gift.closest("details")).not.toHaveAttribute("open");
    await r.user.click(within(jump).getByRole("button", { name: zh["gift.title"] }));
    expect(gift.closest("details")).toHaveAttribute("open");
    expect(gift).toHaveFocus();
  });

  test("a section it jumps to stops with its heading below the index, on one row or two (#746)", () => {
    // From the scrolling page's top the index reaches main's top padding (16 px, 14 in a narrow window) plus --sections-shown,
    // which the page measures: 32.75 px on one row, 60.8 on two (English at 800 px wide, measured in the real window).
    const margin = cssRules(css).filter((r) => r.selector === ".team [data-section]").map((r) => r.body).join("\n")
      .match(/scroll-margin-top:\s*([^;]+)/)![1];
    const stop = (shown: number) => [...margin.replace(/var\(--sections-shown[^)]*\)/g, `${shown}px`).matchAll(/([+-]\s*)?(\d+(?:\.\d+)?)px/g)]
      .reduce((sum, m) => sum + (m[1]?.trim() === "-" ? -1 : 1) * Number(m[2]), 0);
    for (const shown of [32.75, 60.8]) {
      for (const padding of [16, 14]) expect(stop(shown) - (padding + shown)).toBeGreaterThanOrEqual(8);
    }
    expect(stop(60.8) - 60.8).toBeCloseTo(stop(32.75) - 32.75); // the same room under two rows as under one
  });

  test("lists the team's sections in the order the page shows them", () => {
    renderEditor(<TeamsTab />, settings());
    const jump = screen.getByRole("navigation", { name: zh["team.sections"] });
    expect(within(jump).getAllByRole("button").map((b) => b.textContent)).toEqual(
      (["team.deployment_order", "team.starlight", "gift.title", "keep.title", "skill.title", "team.more"] as const).map((k) => zh[k]));
  });
});
