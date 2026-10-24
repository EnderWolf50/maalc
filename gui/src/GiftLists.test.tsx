// Component tests of the gift list tab: what the user sees and does, and what the settings hold afterwards.
import { screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import { CATALOG, GIFT_BY_ID, iconUrl, keywordIconUrl } from "./giftCatalog";
import { GiftListsTab } from "./GiftLists";
import { DEFAULT_LIST } from "./gifts";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, SEARCH_GIFTS, defaultGorder, newSettings, type GiftList, type Settings } from "./model";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
type Text = keyof typeof zh;
const say = (s: string, vars: Record<string, string | number> = {}) => s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
const nameOf = (id: number) => GIFT_BY_ID.get(id)!.zh;
const ROMAN = ["", "I", "II", "III", "IV", "V"];
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const mine = (patch: Partial<GiftList> = {}): GiftList => ({
  id: "mine", name: "Mine", order: [...GIFT_KEYWORDS], want: [], keep: [], gorder: defaultGorder(), fusion_condition: "any", ...patch,
});
const settingsWith = (lists: GiftList[], language: Settings["language"] = "zh_tw"): Settings => ({ ...newSettings(), language, gift_lists: lists });

/** The tab over these lists, the first of them chosen (or the default). */
async function open(lists: GiftList[], language?: Settings["language"], select = lists[0]?.id ?? "default") {
  const r = renderEditor(<GiftListsTab />, settingsWith(lists, language));
  if (select !== "default") await r.user.selectOptions(screen.getByRole("combobox", { name: TEXT[language ?? "zh_tw"]["gl.list"] }), select);
  return r;
}
type Opened = Awaited<ReturnType<typeof open>>;
const list = (r: Opened) => r.settings().gift_lists[0];
const flash = () => screen.getByRole("status").textContent;

/** The tile of a gift on the tab that is open. */
const getTile = (id: number) => screen.getByRole("button", { name: new RegExp("^" + escape(GIFT_BY_ID.get(id)!.zh) + "，") });
/** Open the gift's keyword tab, then its tile. */
async function tile(r: Opened, id: number) {
  await r.user.click(screen.getByRole("tab", { name: new RegExp("^" + zh[`kw.${GIFT_BY_ID.get(id)!.keyword}` as Text]) }));
  return getTile(id);
}

const burnIII = SEARCH_GIFTS.filter((g) => g.keyword === "Burn" && g.tier === 3).map((g) => g.id);
const fixed = recipes.gifts.find((g) => g.recipes && !g.specific)!; // a fusion gift with fixed recipes
const material = fixed.recipes![0][0];
const vestige = 9991;

describe("the catalog", () => {
  test("every gift has an icon, and the data's gifts, fusions, materials and vestiges are each listed once", () => {
    expect(new Set(CATALOG.map((g) => g.id)).size).toBe(CATALOG.length);
    expect(CATALOG.length).toBe(SEARCH_GIFTS.length + recipes.gifts.length + recipes.materials.length + 5);
    for (const g of CATALOG) expect(iconUrl(g.id), String(g.id)).toBeTruthy();
  });
});

describe("tabs", () => {
  test("a keyword's tab and heading show its game icon; Keywordless has none", async () => {
    await open([mine()]);
    for (const tab of screen.getAllByRole("tab")) {
      const k = GIFT_KEYWORDS.find((x) => tab.textContent!.startsWith(zh[`kw.${x}` as Text]))!;
      const img = tab.querySelector("img");
      if (k === "Keywordless") expect(img).toBeNull();
      else {
        expect(keywordIconUrl(k)).toBeTruthy();
        expect(img).toHaveAttribute("src", keywordIconUrl(k));
      }
      expect(tab).toHaveAccessibleName(new RegExp("^" + zh[`kw.${k}` as Text]));
    }
    expect(screen.getByRole("heading", { name: new RegExp("^" + zh[`kw.${GIFT_KEYWORDS[0]}` as Text]) }).querySelector("img")).toHaveAttribute("src", keywordIconUrl(GIFT_KEYWORDS[0]));
  });

  test("eleven keyword tabs in the game's order; the first is open, a click or an arrow key moves", async () => {
    const r = await open([mine()]);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(11);
    expect(tabs.map((t) => GIFT_KEYWORDS.findIndex((k) => t.textContent!.startsWith(zh[`kw.${k}` as Text])))).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    await r.user.click(tabs[3]);
    expect(tabs[3]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("aria-selected", "false");
    tabs[3].focus();
    await r.user.keyboard("{ArrowRight}");
    expect(tabs[4]).toHaveAttribute("aria-selected", "true");
    expect(tabs[4]).toHaveFocus();
    await r.user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(tabs[2]).toHaveAttribute("aria-selected", "true");
  });

  test("the badge counts what the list sets; the header says which keyword is the main one", async () => {
    const r = await open([mine({ order: ["Bleed", ...GIFT_KEYWORDS.filter((k) => k !== "Bleed")], want: burnIII.slice(0, 2), keep: [burnIII[2]] })]);
    expect(screen.getByRole("tab", { name: /^燒傷/ })).toHaveTextContent("3");
    expect(screen.getByRole("tab", { name: /^流血/ })).not.toHaveTextContent(/\d/);
    await r.user.click(screen.getByRole("tab", { name: /^流血/ }));
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(zh["gl.main"]);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(say(zh["gl.rank"], { n: 1 }));
    await r.user.click(screen.getByRole("tab", { name: /^燒傷/ }));
    expect(screen.getByRole("heading", { level: 3 })).not.toHaveTextContent(zh["gl.main"]);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(say(zh["gl.rank"], { n: 2 }));
  });

  test("Keywordless is never the main keyword, even first in the order", async () => {
    const r = await open([mine({ order: ["Keywordless", ...GIFT_KEYWORDS.filter((k) => k !== "Keywordless")] })]);
    await r.user.click(screen.getByRole("tab", { name: /^無體系/ }));
    expect(screen.getByRole("heading", { level: 3 })).not.toHaveTextContent(zh["gl.main"]);
    await r.user.click(screen.getByRole("tab", { name: /^燒傷/ }));
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(zh["gl.main"]);
  });
});

describe("applying a state", () => {
  test("1, 2 and 3 choose the state; a click applies it, and the list holds the result", async () => {
    const [a, b, c] = burnIII;
    const r = await open([mine({ want: [c] })]);
    const radio = (s: string) => screen.getByRole("radio", { name: zh[`state.${s}` as Text] });
    expect(radio("want")).toBeChecked();
    await r.user.click(getTile(a));
    expect(list(r).want).toEqual([c, a]);
    await r.user.keyboard("2");
    expect(radio("keep")).toBeChecked();
    expect(radio("want")).not.toBeChecked();
    await r.user.click(getTile(b));
    expect(list(r).keep).toEqual([b]);
    await r.user.click(getTile(a)); // want -> keep moves it
    expect(list(r)).toMatchObject({ want: [c], keep: [b, a] });
    await r.user.click(radio("drop"));
    await r.user.click(getTile(c));
    await r.user.keyboard("3");
    await r.user.click(getTile(b));
    expect(list(r)).toMatchObject({ want: [], keep: [a] });
  });

  test("the apply bar is one tab stop; the arrow keys move the choice", async () => {
    const r = await open([mine()]);
    const radio = (s: string) => screen.getByRole("radio", { name: zh[`state.${s}` as Text] });
    expect(radio("keep")).toHaveAttribute("tabindex", "-1");
    radio("want").focus();
    await r.user.keyboard("{ArrowRight}");
    expect(radio("keep")).toBeChecked();
    expect(radio("keep")).toHaveFocus();
    await r.user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(radio("drop")).toBeChecked();
  });

  test("the badge and the header count a kept fusion gift as kept", async () => {
    const r = await open([mine({ keep: [fixed.id] })]);
    await tile(r, fixed.id);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(say(zh["gl.n_keep"], { n: 1 }));
    expect(screen.getByRole("tab", { name: new RegExp("^" + zh[`kw.${fixed.keyword}` as Text]) })).toHaveTextContent("1");
  });

  test("a tile's accessible name is the gift, its tier and its state", async () => {
    const [a] = burnIII;
    const r = await open([mine({ keep: [a] })]);
    expect(getTile(a)).toHaveAccessibleName(say(zh["gl.tile"], { name: nameOf(a), tier: "III", state: zh["state.keep"], lock: "" }));
    expect(r.settings().gift_lists[0].keep).toEqual([a]);
  });

  test("the arrow keys walk the grid and Enter or Space apply the state", async () => {
    const [a, b] = burnIII;
    const r = await open([mine()]);
    getTile(a).focus();
    await r.user.keyboard("{Enter}");
    expect(list(r).want).toEqual([a]);
    await r.user.keyboard("{ArrowRight}");
    expect(getTile(b)).toHaveFocus();
    await r.user.keyboard(" ");
    expect(list(r).want).toEqual([a, b]);
    await r.user.keyboard("{ArrowLeft}");
    expect(getTile(a)).toHaveFocus();
    expect(getTile(a)).toHaveAttribute("tabindex", "0"); // roving: one tile is the tab stop
    expect(getTile(b)).toHaveAttribute("tabindex", "-1");
  });

  test("the up and down keys go to the tile in the row above or below (jsdom has no layout: three tiles a row are laid out by hand)", async () => {
    const rect = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const tiles = [...document.querySelectorAll("[data-gift]")], i = tiles.indexOf(this);
      const [row, col] = [Math.floor(i / 3), i % 3];
      return { top: row * 70, left: col * 70, bottom: row * 70 + 64, right: col * 70 + 64, width: 64, height: 64, x: col * 70, y: row * 70, toJSON() {} };
    });
    try {
      const r = await open([mine()]);
      const tiles = [...document.querySelectorAll<HTMLElement>("[data-gift]")];
      tiles[4].focus();
      await r.user.keyboard("{ArrowDown}");
      expect(tiles[7]).toHaveFocus();
      await r.user.keyboard("{ArrowUp}{ArrowUp}");
      expect(tiles[1]).toHaveFocus();
    } finally {
      rect.mockRestore();
    }
  });

  test("a digit typed in a select is not a state choice", async () => {
    const r = await open([mine()]);
    await r.user.click(screen.getByRole("combobox", { name: zh["team.fusion_condition"] }));
    await r.user.keyboard("2");
    expect(screen.getByRole("radio", { name: zh["state.want"] })).toBeChecked();
  });
});

describe("locked gifts", () => {
  test("a drop material of a wanted fusion shows kept and locked; a click says why and changes nothing", async () => {
    const r = await open([mine({ want: [fixed.id] })]);
    const g = GIFT_BY_ID.get(material)!;
    const t = await tile(r, material);
    expect(t).toHaveAccessibleName(say(zh["gl.tile"], { name: g.zh, tier: ROMAN[g.tier], state: zh["state.keep"], lock: zh["gl.locked"] }));
    await r.user.keyboard("3");
    await r.user.click(t);
    expect(flash()).toBe(say(zh["gl.lock_why"], { name: g.zh, by: nameOf(fixed.id) }));
    expect(list(r)).toMatchObject({ want: [fixed.id], keep: [] });
  });

  test("a locked material is no gift the list set: the tab count and the heading's kept count leave it out", async () => {
    const r = await open([mine({ want: [fixed.id] })]);
    await tile(r, material);
    const kept = screen.getByRole("heading", { level: 3 }).textContent!;
    expect(kept).not.toContain(say(zh["gl.n_keep"], { n: 1 }));
    const tab = screen.getByRole("tab", { name: new RegExp("^" + zh[`kw.${GIFT_BY_ID.get(material)!.keyword}` as Text]) });
    const same = GIFT_BY_ID.get(material)!.keyword === GIFT_BY_ID.get(fixed.id)!.keyword;
    expect(tab.querySelector(".gl-n")?.textContent ?? "").toBe(same ? "1" : ""); // the wanted fusion alone, if it is under this keyword
  });

  test("the GUI does not know the run's packs: a pack-specific fusion locks its materials too", async () => {
    const specific = recipes.gifts.find((g) => g.specific && g.recipes)!;
    const m = specific.recipes![0][0];
    const r = await open([mine({ want: [specific.id] })]);
    expect((await tile(r, m)).getAttribute("aria-label")).toContain(zh["gl.locked"]);
  });

  test("a material the list keeps itself is not locked", async () => {
    const r = await open([mine({ want: [fixed.id], keep: [material] })]);
    expect((await tile(r, material)).getAttribute("aria-label")).not.toContain(zh["gl.locked"]);
  });
});

describe("read-only default", () => {
  test("it shows the data file's content; every change only shows the notice", async () => {
    const r = await open([mine()], "zh_tw", "default");
    expect(screen.getByRole("combobox", { name: zh["gl.list"] })).toHaveValue("default");
    expect(screen.getByText(zh["gl.readonly"])).toBeInTheDocument();
    const wanted = DEFAULT_LIST.want.find((id) => GIFT_BY_ID.get(id)!.kind === "buyable")!;
    expect(await tile(r, wanted)).toHaveAccessibleName(new RegExp(zh["state.want"]));
    const before = JSON.stringify(r.settings());
    await r.user.keyboard("3");
    await r.user.click(getTile(wanted));
    expect(flash()).toBe(zh["gl.ro"]);
    await r.user.selectOptions(screen.getByRole("combobox", { name: zh["team.fusion_condition"] }), "tier4");
    expect(flash()).toBe(zh["gl.ro"]);
    expect(JSON.stringify(r.settings())).toBe(before);
  });

  test("the user's own list is editable, and its fusion condition is stored", async () => {
    const r = await open([mine()]);
    expect(screen.queryByText(zh["gl.readonly"])).not.toBeInTheDocument();
    await r.user.selectOptions(screen.getByRole("combobox", { name: zh["team.fusion_condition"] }), "tier4");
    expect(list(r).fusion_condition).toBe("tier4");
  });
});

describe("gifts that cannot be wanted", () => {
  test("a vestige set to want becomes keep, with a notice", async () => {
    const r = await open([mine()]);
    await r.user.click(await tile(r, vestige));
    expect(list(r)).toMatchObject({ want: [], keep: [vestige] });
    expect(flash()).toBe(say(zh["gl.unbuyable_keep"], { name: nameOf(vestige) }));
  });

  test("so does a recipe material the shop does not sell; a vestige can still be dropped", async () => {
    const unbuyable = recipes.materials[0].id;
    const r = await open([mine({ keep: [vestige] })]);
    await r.user.click(await tile(r, unbuyable));
    expect(list(r).keep).toEqual([vestige, unbuyable]);
    await r.user.keyboard("3");
    await r.user.click(await tile(r, vestige));
    expect(list(r).keep).toEqual([unbuyable]);
  });

  test("a fusion gift can be wanted", async () => {
    const r = await open([mine()]);
    await r.user.click(await tile(r, fixed.id));
    expect(list(r).want).toEqual([fixed.id]);
  });
});

describe("an empty list", () => {
  test("shows a banner; one click starts it from the default's content", async () => {
    const r = await open([mine()]);
    expect(screen.getByText(zh["gl.empty"])).toBeInTheDocument();
    await r.user.click(screen.getByRole("button", { name: zh["gl.from_default"] }));
    expect(list(r)).toMatchObject({
      id: "mine", name: "Mine", want: DEFAULT_LIST.want, keep: DEFAULT_LIST.keep, order: DEFAULT_LIST.order, gorder: DEFAULT_LIST.gorder,
    });
    expect(screen.queryByText(zh["gl.empty"])).not.toBeInTheDocument();
  });

  test("no banner for a list with something set, nor for the default", async () => {
    const r = await open([mine({ keep: [vestige] })]);
    expect(screen.queryByText(zh["gl.empty"])).not.toBeInTheDocument();
    await r.user.selectOptions(screen.getByRole("combobox", { name: zh["gl.list"] }), "default");
    expect(screen.queryByText(zh["gl.empty"])).not.toBeInTheDocument();
  });
});

describe("the tab in English", () => {
  test("names, states and keywords are the English ones", async () => {
    const [a] = burnIII;
    await open([mine({ want: [a] })], "en_us");
    const en = TEXT.en_us;
    const g = GIFT_BY_ID.get(a)!;
    expect(screen.getByRole("tab", { name: /^Burn/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: en["state.want"] })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: new RegExp("^" + escape(g.en) + ", ") }))
      .toHaveAccessibleName(say(en["gl.tile"], { name: g.en, tier: "III", state: en["state.want"], lock: "" }));
    expect(within(screen.getByRole("tabpanel")).getByRole("heading", { level: 3 })).toHaveTextContent("Burn");
  });
});
