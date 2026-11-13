// Component tests of the teams tab's gift list choice (#296, covering #305 as well): the list dropdown, the main keyword the
// list decides, and the button that sends the user to the gift list tab with that list chosen.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { iconUrl } from "./giftCatalog";
import { DEFAULT_LIST, mainKeyword } from "./gifts";
import { TEXT, fill } from "./i18n";
import { GIFT_KEYWORDS, GRACES, SEARCH_GIFTS, SEARCH_TABS, SINNERS, defaultGorder, newSettings, newTeam, starlightCost, type GiftList, type Settings } from "./model";
import { expectLines, renderEditor } from "./testing";
import css from "./index.css?raw";
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
    await r.user.click(within(document.querySelector("aside")!).getByText("T2"));
    expect(screen.queryByRole("group", { name: zh.resetTimes })).toBeNull();
    await r.user.click(within(document.querySelector("aside")!).getByText("T1"));
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
    await r.user.click(within(document.querySelector("aside")!).getByText("T2"));
    expect(screen.queryByText(zh.resetDone)).toBeNull();
    await r.user.click(within(document.querySelector("aside")!).getByText("T1"));
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
  const [first, second] = within(document.querySelector("aside")!).getAllByRole("listitem");
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
    await r.user.click(within(document.querySelector("aside")!).getByText("T2"));
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

  test("a sinner left out of the order shows its card darkened; deployed and backup ones at full light", () => {
    renderEditor(<TeamsTab />, ordered());
    for (const s of ["Don Quixote", "Meursault", "Gregor"]) expect(tile(s)).toHaveClass("out");
    for (const s of order) expect(tile(s)).not.toHaveClass("out");
    // at rest: the pointer over one lifts it a little, to say a click puts it back in
    const dim = cssRules(css).filter((r) => r.selector.includes(".sinner.out") && /\bimg\b/.test(r.selector) && !r.selector.includes(":hover"))
      .map((r) => r.body.match(/brightness\(([\d.]+)\)/)?.[1]);
    expect(dim.length).toBeGreaterThan(0);
    for (const b of dim) expect(Number(b)).toBeLessThan(0.6);
  });
});

/** The stylesheet's plain rules, `selector { body }`, enough to read what a selector sets. */
function cssRules(text: string) {
  return [...text.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
}

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

  test("lists the team's sections in the order the page shows them", () => {
    renderEditor(<TeamsTab />, settings());
    const jump = screen.getByRole("navigation", { name: zh["team.sections"] });
    expect(within(jump).getAllByRole("button").map((b) => b.textContent)).toEqual(
      (["team.deployment_order", "team.starlight", "gift.title", "keep.title", "skill.title", "team.more"] as const).map((k) => zh[k]));
  });
});
