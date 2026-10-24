// Component tests of the gift list tab's hover popover, search and help (#307): what the user sees and does, and what the
// settings hold afterwards.
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import { CATALOG, GIFT_BY_ID, packName } from "./giftCatalog";
import { GiftListsTab } from "./GiftLists";
import { place, usedText } from "./GiftPopover";
import { queue } from "./gifts";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, SEARCH_GIFTS, defaultGorder, newSettings, type GiftList, type Settings } from "./model";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
type Text = keyof typeof zh;
const say = (s: string, vars: Record<string, string | number> = {}) => s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
const nameOf = (id: number) => GIFT_BY_ID.get(id)!.zh;
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

const getTile = (id: number) => screen.getByRole("button", { name: new RegExp("^" + escape(GIFT_BY_ID.get(id)!.zh) + "，") });
async function tile(r: Opened, id: number) {
  await r.user.click(screen.getByRole("tab", { name: new RegExp("^" + zh[`kw.${GIFT_BY_ID.get(id)!.keyword}` as Text]) }));
  return getTile(id);
}
/** The hover popover, or null while none is open. */
const popover = () => screen.queryByRole("dialog", { name: /./ });
/** Open the gift's keyword tab, hover its tile, and return the popover's queries. */
async function hover(r: Opened, id: number) {
  await tile(r, id);
  await r.user.hover(getTile(id));
  return within(popover()!);
}

const burnIII = SEARCH_GIFTS.filter((g) => g.keyword === "Burn" && g.tier === 3).map((g) => g.id);
const fixed = recipes.gifts.find((g) => g.recipes && !g.specific && g.recipes.length === 2)!; // fixed recipes, two of them
const material = fixed.recipes![0][0];
const lunar = recipes.gifts.find((g) => g.groups)!;
const specific = recipes.gifts.find((g) => g.specific && g.recipes)!;

afterEach(() => vi.useRealTimers());

describe("hover popover: opening and closing", () => {
  test("opens on the tile, stays while the pointer is on the tile or the popover, closes 160 ms after it leaves", async () => {
    vi.useFakeTimers();
    await act(async () => { renderEditor(<GiftListsTab />, settingsWith([mine()])); });
    const [a] = burnIII;
    expect(popover()).toBeNull();
    fireEvent.mouseEnter(getTile(a));
    expect(popover()).toHaveAccessibleName(nameOf(a));
    fireEvent.mouseLeave(getTile(a));
    act(() => { vi.advanceTimersByTime(150); });
    expect(popover()).not.toBeNull(); // not yet
    fireEvent.mouseEnter(popover()!); // the pointer crossed over to the popover: it stays
    act(() => { vi.advanceTimersByTime(500); });
    expect(popover()).not.toBeNull();
    fireEvent.mouseLeave(popover()!);
    act(() => { vi.advanceTimersByTime(159); });
    expect(popover()).not.toBeNull();
    act(() => { vi.advanceTimersByTime(1); });
    expect(popover()).toBeNull();
  });
});

describe("hover popover: closing at once", () => {
  async function opened() {
    const r = await open([mine()]);
    await r.user.hover(getTile(burnIII[0]));
    expect(popover()).not.toBeNull();
    return r;
  }
  test("a scroll of the page", async () => { await opened(); fireEvent.scroll(window); expect(popover()).toBeNull(); });
  test("the window losing focus", async () => { await opened(); fireEvent.blur(window); expect(popover()).toBeNull(); });
  test("a drag of the tile", async () => { await opened(); fireEvent.dragStart(getTile(burnIII[0]), { dataTransfer: { setData() {}, effectAllowed: "" } }); expect(popover()).toBeNull(); });
  test("a scroll inside the popover is not the page moving", async () => {
    await opened();
    fireEvent.scroll(popover()!);
    expect(popover()).not.toBeNull();
  });
  test("keyboard focus opens it, and focus leaving the tile closes it", async () => {
    await open([mine()]);
    act(() => getTile(burnIII[0]).focus());
    expect(popover()).not.toBeNull();
    act(() => getTile(burnIII[0]).blur());
    expect(popover()).toBeNull();
  });
  test("focus inside the popover keeps it; focus going elsewhere closes it", async () => {
    const r = await open([mine()]);
    await r.user.hover(getTile(burnIII[0]));
    const keep = within(popover()!).getByRole("button", { name: zh["state.keep"] });
    act(() => keep.focus());
    expect(popover()).not.toBeNull();
    await r.user.click(screen.getByRole("radio", { name: zh["state.drop"] }));
    expect(popover()).toBeNull();
  });
  test("showing another tile replaces the popover", async () => {
    const r = await open([mine()]);
    await r.user.hover(getTile(burnIII[0]));
    await r.user.hover(getTile(burnIII[1]));
    expect(screen.getAllByRole("dialog", { name: /./ })).toHaveLength(1);
    expect(popover()).toHaveAccessibleName(nameOf(burnIII[1]));
  });
});

describe("hover popover: where it goes", () => {
  const view = { w: 1000, h: 800 }, size = { w: 300, h: 200 };
  const box = (left: number, top: number) => ({ left, top, right: left + 64, bottom: top + 64 });
  test("its top-left corner is 14 px right of the tile's left and 2 px under the tile", () => {
    expect(place(box(100, 100), size, view)).toEqual({ left: 114, top: 166 });
  });
  test("no room to the right: mirrored, its right edge 14 px left of the tile's right", () => {
    expect(place(box(800, 100), size, view)).toEqual({ left: 864 - 14 - 300, top: 166 });
  });
  test("no room below: above the tile, its bottom 2 px over the tile's top", () => {
    expect(place(box(100, 700), size, view)).toEqual({ left: 114, top: 700 - 2 - 200 });
  });
  test("what fits nowhere is pushed into the window, the top-left kept visible", () => {
    expect(place(box(-50, 300), size, view)).toEqual({ left: 6, top: 366 });
    expect(place(box(100, 300), { w: 300, h: 900 }, view)).toEqual({ left: 114, top: 6 });
  });
});

describe("hover popover: setting the state", () => {
  test("the three buttons show the state and set it; the list holds the result", async () => {
    const [a] = burnIII;
    const r = await open([mine({ want: [a] })]);
    await r.user.hover(getTile(a));
    const p = within(popover()!);
    expect(p.getByRole("group", { name: zh["gl.tip_set_group"] })).toBeInTheDocument();
    expect(p.getByRole("button", { name: zh["state.want"] })).toHaveAttribute("aria-pressed", "true");
    await r.user.click(p.getByRole("button", { name: zh["state.keep"] }));
    expect(list(r)).toMatchObject({ want: [], keep: [a] });
    expect(within(popover()!).getByRole("button", { name: zh["state.keep"] })).toHaveAttribute("aria-pressed", "true"); // still open, updated
    await r.user.click(within(popover()!).getByRole("button", { name: zh["state.drop"] }));
    expect(list(r)).toMatchObject({ want: [], keep: [] });
  });

  test("a locked gift's buttons are disabled and say what to cancel", async () => {
    const r = await open([mine({ want: [fixed.id] })]);
    const p = await hover(r, material);
    for (const s of ["want", "keep", "drop"]) expect(p.getByRole("button", { name: zh[`state.${s}` as Text] })).toBeDisabled();
    expect(p.getByText(say(zh["gl.tip_locked"], { by: nameOf(fixed.id) }))).toBeInTheDocument();
  });

  test("on the read-only default they are disabled with the reason", async () => {
    const r = await open([mine()], "zh_tw", "default");
    const p = await hover(r, burnIII[0]);
    expect(p.getByRole("button", { name: zh["state.keep"] })).toBeDisabled();
    expect(p.getByText(zh["gl.tip_ro"])).toBeInTheDocument();
  });
});

describe("hover popover: what it says", () => {
  test("the head has the Chinese and English names; the category is the keyword, tier and kind", async () => {
    const [a] = burnIII;
    const r = await open([mine()]);
    const p = await hover(r, a);
    expect(p.getByText(GIFT_BY_ID.get(a)!.en)).toBeInTheDocument();
    expect(p.getByText(say(zh["gl.tip_cat_line"], { kw: zh["kw.Burn"], tier: "III" }))).toBeInTheDocument();
    const q = await hover(r, fixed.id);
    expect(q.getByText(say(zh["gl.tip_cat_line"], { kw: zh[`kw.${fixed.keyword}` as Text], tier: "IV" }) + zh["gl.tip_cat_fusion"])).toBeInTheDocument();
  });

  test("a locked gift: why, and a way to the wanted fusion or to stop wanting it", async () => {
    const r = await open([mine({ want: [fixed.id] })]);
    const p = await hover(r, material);
    expect(p.getByText(say(zh["gl.tip_lock_why"], { by: nameOf(fixed.id) }))).toBeInTheDocument();
    expect(p.queryByText(/這一局拿到主題包/)).not.toBeInTheDocument(); // a fixed recipe locks whatever the run's packs
    await r.user.click(p.getByRole("button", { name: say(zh["gl.tip_goto"], { name: nameOf(fixed.id) }) }));
    expect(screen.getByRole("tab", { name: new RegExp("^" + zh[`kw.${fixed.keyword}` as Text]) })).toHaveAttribute("aria-selected", "true");
    expect(getTile(fixed.id)).toHaveFocus();
    expect(popover()).toBeNull(); // the popover of the old tile is gone, and the new tile's does not open under the scroll
    const q = await hover(r, material);
    await r.user.click(q.getByRole("button", { name: zh["gl.tip_unwant"] }));
    expect(list(r).want).toEqual([]);
  });

  test("a pack-specific fusion locks its materials, and the popover says which pack makes it count", async () => {
    const r = await open([mine({ want: [specific.id] })]);
    const p = await hover(r, specific.recipes![0][0]);
    expect(p.getByText(say(zh["gl.tip_pack"], { packs: specific.packs!.map(packName).join(zh["gl.sep"]) }))).toBeInTheDocument();
  });

  test("every pack a recipe names shows by its name: the re-run copies and the Extreme-only packs too", () => {
    expect(recipes.gifts.flatMap((g) => g.packs ?? []).filter((p) => packName(p).startsWith("#"))).toEqual([]);
    expect([1004, 1113, 1507].map(packName)).toEqual(["Automated Factory", "Miracle in District 20 BokGak", "Who Couldn't be Bloodfiends"]);
    expect(packName(1)).toBe("#1"); // an id the file does not know stays an id
  });

  test("a wanted fusion says its recipe's gifts are all locked", async () => {
    const r = await open([mine({ want: [fixed.id, lunar.id] })]);
    expect((await hover(r, fixed.id)).getByText(say(zh["gl.tip_mats_all"], { n: new Set(fixed.recipes!.flat()).size }))).toBeInTheDocument();
    const [a, b] = lunar.groups!;
    expect((await hover(r, lunar.id)).getByText(say(zh["gl.tip_mats_mix"], { a: a.ids.length, b: b.ids.length, n: a.ids.length + b.ids.length }))).toBeInTheDocument();
  });

  test("the uses: the fusions a gift is a material of; more than four are cut to four and a count", async () => {
    const r = await open([mine()]);
    const p = await hover(r, material);
    const users = recipes.gifts.filter((g) => (g.recipes ?? []).flat().includes(material)).map((g) => g.zh);
    expect(users.length).toBeGreaterThan(0);
    for (const n of users) expect(p.getByText(new RegExp(escape(n)))).toBeInTheDocument();
    const names = ["一", "二", "三", "四", "五", "六"];
    expect(usedText(names.slice(0, 4), zh)).toBe(say(zh["gl.tip_used_list"], { names: "一、二、三、四" }));
    expect(usedText(names, zh)).toBe(say(zh["gl.tip_used_more"], { names: "一、二、三、四", n: 6 }));
    expect(usedText(names, TEXT.en_us)).toBe(say(TEXT.en_us["gl.tip_used_more"], { names: "一, 二, 三, 四", n: 6 }));
  });

  test("the recipes: numbered when there are two; Lunar Memory shows fragments 7 pick 2 and memories 3 pick 3 (all)", async () => {
    const r = await open([mine()]);
    const p = await hover(r, fixed.id);
    for (const id of new Set(fixed.recipes!.flat())) expect(p.getAllByText(nameOf(id)).length).toBeGreaterThan(0);
    expect(p.getByText("1")).toBeInTheDocument();
    expect(p.getByText("2")).toBeInTheDocument();
    const q = await hover(r, lunar.id);
    expect(q.getByText(say(zh["gl.tip_group"], { name: zh["gl.tip_fragment"], n: 7, need: 2 }))).toBeInTheDocument();
    expect(q.getByText(say(zh["gl.tip_group"], { name: zh["gl.tip_memory"], n: 3, need: 3 }) + zh["gl.tip_all"])).toBeInTheDocument();
    for (const id of lunar.groups!.flatMap((g) => g.ids)) expect(q.getAllByText(nameOf(id)).length).toBeGreaterThan(0);
  });

  test("the order: the place in the buy queue; a fusion is made, not bought; an unwanted gift is not queued", async () => {
    const [a, b, c] = burnIII;
    const l = mine({ want: [b, a, fixed.id] });
    const r = await open([l]);
    const q = queue(l);
    expect(q.length).toBeGreaterThan(0);
    expect((await hover(r, a)).getByText(say(zh["gl.tip_buy_rank"], { n: q.indexOf(a) + 1, total: q.length }))).toBeInTheDocument();
    expect((await hover(r, c)).getByText(zh["gl.tip_buy_none"])).toBeInTheDocument();
    expect((await hover(r, fixed.id)).getByText(zh["gl.tip_fusion_want"])).toBeInTheDocument();
    await r.user.click(within(popover()!).getByRole("button", { name: zh["state.drop"] }));
    expect(within(popover()!).getByText(zh["gl.tip_fusion_no"])).toBeInTheDocument();
  });

  test("in English", async () => {
    const en = TEXT.en_us, [a] = burnIII;
    const r = await open([mine({ want: [a] })], "en_us");
    await r.user.hover(screen.getByRole("button", { name: new RegExp("^" + escape(GIFT_BY_ID.get(a)!.en) + ", ") }));
    const p = within(popover()!);
    expect(p.getByText(en["gl.tip_set"])).toBeInTheDocument();
    expect(p.getByText(say(en["gl.tip_buy_rank"], { n: 1, total: 1 }))).toBeInTheDocument();
    expect(popover()).toHaveAccessibleName(GIFT_BY_ID.get(a)!.en);
  });
});

describe("search", () => {
  const box = () => screen.getByRole("searchbox", { name: zh["gl.search"] });
  const tiles = () => [...document.querySelectorAll<HTMLElement>("[data-gift]")];
  const shownIds = () => tiles().map((t) => Number(t.dataset.gift));
  const [a, b] = burnIII;

  test("by the Chinese name, in part", async () => {
    const r = await open([mine()]);
    const name = nameOf(a);
    await r.user.type(box(), name.slice(0, 2));
    expect(shownIds()).toContain(a);
    expect(shownIds().every((id) => CATALOG.find((g) => g.id === id)!.zh.includes(name.slice(0, 2)))).toBe(true);
  });

  test("by the English name, whatever the case", async () => {
    const r = await open([mine()]);
    const en = GIFT_BY_ID.get(b)!.en;
    await r.user.type(box(), en.slice(0, 6).toUpperCase());
    expect(shownIds()).toContain(b);
    expect(shownIds().every((id) => CATALOG.find((g) => g.id === id)!.en.toLowerCase().includes(en.slice(0, 6).toLowerCase()))).toBe(true);
  });

  test("by id: that gift alone", async () => {
    const r = await open([mine()]);
    await r.user.type(box(), String(a));
    expect(shownIds()).toEqual([a]);
    await r.user.clear(box());
    await r.user.type(box(), String(a).slice(0, -1)); // part of an id is no match
    expect(shownIds()).toEqual([]);
  });

  test("results are grouped by keyword in the list's order, and no tab is selected", async () => {
    const r = await open([mine({ order: ["Bleed", ...GIFT_KEYWORDS.filter((k) => k !== "Bleed")] })]);
    await r.user.type(box(), "e");
    const heads = screen.getAllByRole("heading", { level: 3 }).map((h) => GIFT_KEYWORDS.findIndex((k) => h.textContent!.includes(zh[`kw.${k}` as Text])));
    expect(heads.length).toBeGreaterThan(2);
    expect(heads[0]).toBe(GIFT_KEYWORDS.indexOf("Bleed"));
    expect(screen.getAllByRole("tab").every((t) => t.getAttribute("aria-selected") === "false")).toBe(true);
    expect(screen.getByText(say(zh["gl.search_n"], { n: tiles().length }))).toBeInTheDocument();
  });

  test("a result is a tile like any other: a click applies the state, and the popover opens", async () => {
    const r = await open([mine()]);
    await r.user.type(box(), String(a));
    await r.user.click(getTile(a));
    expect(list(r).want).toEqual([a]);
    expect(popover()).not.toBeNull();
  });

  test("nothing found says so and offers to clear", async () => {
    const r = await open([mine()]);
    await r.user.type(box(), "zzzzzz");
    expect(screen.getByText(say(zh["gl.search_none"], { q: "zzzzzz" }))).toBeInTheDocument();
    await r.user.click(screen.getByRole("button", { name: zh["gl.search_clear"] }));
    expect(box()).toHaveValue("");
    expect(screen.getByRole("tab", { name: /^燒傷/ })).toHaveAttribute("aria-selected", "true");
  });

  test("Esc clears it and brings back the tab; a tab click leaves the search", async () => {
    const r = await open([mine()]);
    await r.user.type(box(), String(a));
    await r.user.keyboard("{Escape}");
    expect(box()).toHaveValue("");
    expect(screen.getByRole("tab", { name: /^燒傷/ })).toHaveAttribute("aria-selected", "true");
    await r.user.type(box(), String(a));
    await r.user.click(screen.getByRole("tab", { name: /^流血/ }));
    expect(box()).toHaveValue("");
    expect(screen.getByRole("tab", { name: /^流血/ })).toHaveAttribute("aria-selected", "true");
  });

  test("Esc that closes the list options does not also clear the search", async () => {
    const r = await open([mine()]);
    await r.user.type(box(), String(a));
    await r.user.click(screen.getByRole("button", { name: zh["gl.opts"] }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    // A popover opening and closing re-registers the tab's key listener after the menu's own: its order must not matter.
    await r.user.hover(getTile(a));
    await r.user.unhover(getTile(a));
    await waitFor(() => expect(popover()).toBeNull());
    await r.user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(box()).toHaveValue(String(a));
    await r.user.keyboard("{Escape}"); // nothing else is open now: this one clears it
    expect(box()).toHaveValue("");
  });

  test("/ jumps to the box, unless the user is typing somewhere", async () => {
    const r = await open([mine()]);
    act(() => (document.activeElement as HTMLElement).blur()); // the list choice has focus after open()
    await r.user.keyboard("/");
    expect(box()).toHaveFocus();
    expect(box()).toHaveValue(""); // the slash is the shortcut, not text
    await r.user.keyboard("/");
    expect(box()).toHaveValue("/");
    await r.user.clear(box());
    getTile(a).focus();
    await r.user.keyboard("/");
    expect(box()).toHaveFocus();
  });

  test("a popover whose tile the search takes away goes with it", async () => {
    const r = await open([mine()]);
    act(() => (document.activeElement as HTMLElement).blur()); // the list choice has focus after open()
    await r.user.hover(getTile(a));
    expect(popover()).not.toBeNull();
    await r.user.keyboard("/e");
    expect(box()).toHaveValue("e");
    expect(popover()).toBeNull();
  });

  test("an arrow key on the tabs while searching goes to the first tab, either way", async () => {
    const r = await open([mine()]);
    for (const key of ["{ArrowRight}", "{ArrowLeft}"]) {
      await r.user.type(box(), String(a));
      screen.getAllByRole("tab")[0].focus();
      await r.user.keyboard(key);
      expect(box()).toHaveValue("");
      expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
    }
  });

  test("in English", async () => {
    const en = TEXT.en_us;
    const r = await open([mine()], "en_us");
    await r.user.type(screen.getByRole("searchbox", { name: en["gl.search"] }), String(a));
    expect(screen.getByText(say(en["gl.search_n"], { n: 1 }))).toBeInTheDocument();
  });
});

describe("help", () => {
  const button = () => screen.getByRole("button", { name: new RegExp("^" + zh["gl.help"]) });
  test("a button opens and closes it; it holds the legend, the keys and the purchase order rule", async () => {
    const r = await open([mine()]);
    expect(button()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(zh["gl.help_order"])).not.toBeInTheDocument();
    await r.user.click(button());
    expect(button()).toHaveAttribute("aria-expanded", "true");
    const help = within(screen.getByRole("dialog", { name: zh["gl.help"] }));
    for (const k of ["want", "keep", "drop", "locked", "fusion"]) expect(help.getByText(zh[`gl.help_${k}` as Text])).toBeInTheDocument();
    expect(help.getByText(zh["gl.help_keys"])).toBeInTheDocument();
    expect(help.getByText(zh["gl.help_order"])).toBeInTheDocument();
    await r.user.click(button());
    expect(screen.queryByRole("dialog", { name: zh["gl.help"] })).not.toBeInTheDocument();
  });

  test("Esc and a click elsewhere close it", async () => {
    const r = await open([mine()]);
    await r.user.click(button());
    await r.user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: zh["gl.help"] })).not.toBeInTheDocument();
    await r.user.click(button());
    await r.user.click(screen.getByRole("tab", { name: /^流血/ }));
    expect(screen.queryByRole("dialog", { name: zh["gl.help"] })).not.toBeInTheDocument();
  });

  test("in English", async () => {
    const en = TEXT.en_us;
    const r = await open([mine()], "en_us");
    await r.user.click(screen.getByRole("button", { name: new RegExp("^" + en["gl.help"]) }));
    expect(screen.getByText(en["gl.help_order"])).toBeInTheDocument();
  });
});
