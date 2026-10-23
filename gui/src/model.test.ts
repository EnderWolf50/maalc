// The click rules of the team page's sinner grid and starlight cards.
import { expect, test } from "vitest";
import {
  FUSION_CONDITIONS, GIFT_KEYWORDS, SEARCH_GIFTS, SEARCH_TABS, buyOrder, clickCard, clickEnhance, defaultGorder, enhanceAll, exportGiftList, gracePrice,
  importGiftList, lanesOf, lineAt, newPackPlan, newSettings, newTeam, floorBadges, onFloor, selectAll, starlightCost, toggleGift, toggleSinner,
  weightOf, type GiftList, type StarlightValues,
} from "./model";
import { validate } from "./validate";

test("a pack shows on the floors the data file gives it", () => {
  expect(onFloor("N12 H1", "", 0)).toBe(true);
  expect(onFloor("N12 H1", "normal", 2)).toBe(true);
  expect(onFloor("N12 H1", "hard", 2)).toBe(false);
  expect(onFloor("H345", "normal", 0)).toBe(false); // HARD only
  expect(onFloor("H345", "", 4)).toBe(true);
});

test("a pack's floors become badges: ranges for runs, the rest listed, only the difficulties it has", () => {
  expect(floorBadges("N12 H1", "、")).toEqual([{ hard: false, text: "1–2" }, { hard: true, text: "1" }]);
  expect(floorBadges("H13", "、")).toEqual([{ hard: true, text: "1、3" }]); // one difficulty, a gap
  expect(floorBadges("H345", "、")).toEqual([{ hard: true, text: "3–5" }]);
  expect(floorBadges("N124 H5", "、")).toEqual([{ hard: false, text: "1–2、4" }, { hard: true, text: "5" }]);
  expect(floorBadges("N5", "、")).toEqual([{ hard: false, text: "5" }]);
  expect(floorBadges("N45 H34", ", ")).toEqual([{ hard: false, text: "4–5" }, { hard: true, text: "3–4" }]);
  expect(floorBadges("", "、")).toEqual([]);
});

test("lanes are the weights in use and 0, highest first; the line sits under the lanes at or over the threshold", () => {
  const plan = { ...newPackPlan(), weights: { A: 5, B: -5, C: 5 }, unlisted: -2 };
  expect(lanesOf(plan)).toEqual([5, 0, -2, -5]);
  expect(lanesOf(newPackPlan())).toEqual([0]); // 0 always stays
  expect(weightOf(plan, "A")).toBe(5);
  expect(weightOf(plan, "Z")).toBe(-2); // unlisted
  expect(lineAt(lanesOf(plan), 0)).toBe(2); // under 5 and 0: a best of -2 refreshes
  expect(lineAt(lanesOf(plan), 3)).toBe(1);
  expect(lineAt(lanesOf(plan), 6)).toBe(0); // over every lane: always refresh
  expect(lineAt(lanesOf(plan), -10)).toBe(4); // under every lane: never
});

test("clicking a sinner not in the order adds it at the end", () => {
  expect(toggleSinner(["Ryōshū", "Yi Sang"], "Faust")).toEqual(["Ryōshū", "Yi Sang", "Faust"]);
});

test("clicking a sinner in the order leaves it out and moves the later ones up", () => {
  expect(toggleSinner(["Ryōshū", "Yi Sang", "Faust"], "Yi Sang")).toEqual(["Ryōshū", "Faust"]);
});

test("the last sinner in the order stays", () => {
  expect(toggleSinner(["Ryōshū"], "Ryōshū")).toEqual(["Ryōshū"]);
});

const smokes = { keyword: "Bleed", tier: 3, name: "Smokes and Wires" };
const bass = { keyword: "Bleed", tier: 2, name: "Walking Bass" };

test("clicking a gift adds it at the end of the search list, clicking it again takes it out", () => {
  const list = toggleGift([smokes], bass);
  expect(list).toEqual([smokes, bass]);
  expect(toggleGift(list, { ...smokes })).toEqual([bass]);
  // The game searches 3 at most: a fourth is not added, but any can still be removed.
  const full = [smokes, bass, { keyword: "Bleed", tier: 1, name: "C" }];
  expect(toggleGift(full, { keyword: "Bleed", tier: 1, name: "D" })).toEqual(full);
  expect(toggleGift(full, bass)).toHaveLength(2);
});

test("every gift on the search page has a keyword tab, a tier of 1-3 and a unique name", () => {
  expect(SEARCH_GIFTS.length).toBeGreaterThan(300);
  for (const g of SEARCH_GIFTS) {
    expect(SEARCH_TABS).toContain(g.keyword);
    expect([1, 2, 3]).toContain(g.tier);
  }
  expect(new Set(SEARCH_GIFTS.map((g) => g.en)).size).toBe(SEARCH_GIFTS.length);
});

const none = (): StarlightValues => ({ levels: Array(10).fill("none"), priority: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], convert_leftover: false });
const levelOf = (v: StarlightValues, n: number) => v.levels[n - 1];

test("clicking a card selects it at base, and clicking it again leaves it unselected", () => {
  const v = clickCard(none(), 3);
  expect(levelOf(v, 3)).toBe("base");
  expect(levelOf(clickCard(v, 3), 3)).toBe("none");
});

test("clicking an enhanced card leaves it unselected", () => {
  expect(levelOf(clickCard(clickEnhance(none(), 4, 2), 4), 4)).toBe("none");
});

test("+ or ++ on an unselected card selects it at that level", () => {
  expect(levelOf(clickEnhance(none(), 2, 1), 2)).toBe("plus");
  expect(levelOf(clickEnhance(none(), 2, 2), 2)).toBe("plus2");
});

test("the other enhancement button switches the level; the lit one goes back to base", () => {
  const plus = clickEnhance(none(), 2, 1);
  expect(levelOf(clickEnhance(plus, 2, 2), 2)).toBe("plus2");
  expect(levelOf(clickEnhance(plus, 2, 1), 2)).toBe("base");
  expect(levelOf(clickEnhance(clickEnhance(none(), 2, 2), 2, 2), 2)).toBe("base");
});

test("the buying order is the order cards were selected in", () => {
  let v = clickCard(none(), 7);
  v = clickEnhance(v, 2, 2);
  v = clickCard(v, 9);
  expect(buyOrder(v)).toEqual([7, 2, 9]);
  v = clickCard(v, 2);
  expect(buyOrder(v)).toEqual([7, 9]);
  v = clickCard(v, 2);
  expect(buyOrder(v)).toEqual([7, 9, 2]);
  expect([...v.priority].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
});

test("changing a selected card's level keeps its place in the buying order", () => {
  let v = clickCard(clickCard(none(), 5), 1);
  v = clickEnhance(v, 5, 1);
  expect(buyOrder(v)).toEqual([5, 1]);
});

test("Select All Graces adds the unselected cards at base after the selected ones; when all are selected it clears", () => {
  const v = selectAll(clickEnhance(none(), 6, 2));
  expect(buyOrder(v)).toEqual([6, 1, 2, 3, 4, 5, 7, 8, 9, 10]);
  expect(v.levels).toEqual(["base", "base", "base", "base", "base", "plus2", "base", "base", "base", "base"]);
  expect(selectAll(v).levels).toEqual(Array(10).fill("none"));
});

test("Enhance All sets every card to that level and selects it; pressed again it goes back to base", () => {
  const v = enhanceAll(clickCard(none(), 10), 1);
  expect(v.levels).toEqual(Array(10).fill("plus"));
  expect(buyOrder(v)[0]).toBe(10);
  expect(enhanceAll(v, 1).levels).toEqual(Array(10).fill("base"));
  expect(enhanceAll(v, 2).levels).toEqual(Array(10).fill("plus2"));
});

test("the starlight total is each bought boost's base price times 1, 2 or 3", () => {
  const levels = ["base", "plus2", "none", "none", "none", "none", "none", "none", "none", "plus"];
  expect(starlightCost(levels)).toBe(10 + 30 + 120); // spec 04 section 7 prices
  expect(starlightCost(Array(10).fill("none"))).toBe(0);
});

test("a card's price is its base price times 1, 2 or 3", () => {
  expect(gracePrice(10, "none")).toBe(0);
  expect(gracePrice(10, "base")).toBe(60);
  expect(gracePrice(1, "plus")).toBe(20);
  expect(gracePrice(10, "plus2")).toBe(180);
});

test("a new settings file forfeits a run whose wipe retries ran out instead of stopping the batch (#95)", () => {
  expect(newSettings().run.after_retries).toBe("forfeit");
});

const SHARED: GiftList = {
  id: "g1", name: "Fire", order: GIFT_KEYWORDS, want: [9053], keep: [9071], gorder: { Burn: [9071, 9053] }, fusion_condition: "tier4",
};

test("the default gorder lists a keyword's buyable gifts tier III first, in data-file order", () => {
  const burn = defaultGorder().Burn;
  expect(burn).toHaveLength(22);
  expect(burn.slice(0, 2)).toEqual([9053, 9071]);
  expect(Object.keys(defaultGorder())).toEqual(GIFT_KEYWORDS);
});

test("a gift list exports without its id and imports as a new list that passes the checks", () => {
  const text = exportGiftList(SHARED);
  expect(JSON.parse(text)).toEqual({ name: "Fire", order: GIFT_KEYWORDS, want: [9053], keep: [9071], gorder: { Burn: [9071, 9053] }, fusion_condition: "tier4" });
  const { list, skipped } = importGiftList(text, ["Fire（匯入）"], "（匯入）");
  expect(skipped).toBe(0);
  expect(list.name).toBe("Fire（匯入） 2");
  expect(list.id).not.toBe("g1");
  expect(list.fusion_condition).toBe("tier4");
  expect(list.gorder.Burn.slice(0, 2)).toEqual([9071, 9053]);
  expect(list.gorder.Bleed).toEqual(defaultGorder().Bleed);
  const s = newSettings();
  s.gift_lists.push(list);
  s.teams.push({ ...newTeam(1, "T"), gift_list: list.id });
  expect(validate(s)).toEqual([]);
});

test("every fusion condition survives an export and an import", () => {
  for (const fusion_condition of FUSION_CONDITIONS) {
    expect(importGiftList(exportGiftList({ ...SHARED, fusion_condition }), [], "").list.fusion_condition).toBe(fusion_condition);
  }
  expect(FUSION_CONDITIONS).toEqual(["any", "upgrade", "tier4"]);
});

test("an import skips bad ids and falls back to the defaults", () => {
  const messy = JSON.stringify({
    name: "X", order: ["Burn"], want: [9053, 9053, 12345, "9071", 1.5], keep: [9053, 9071, 9991, 77], gorder: { Burn: "no", Fire: [1] },
    fusion_condition: "aggressive",
  });
  const { list, skipped } = importGiftList(messy, [], "（匯入）");
  expect(list.name).toBe("X（匯入）");
  expect(list.order).toEqual(GIFT_KEYWORDS); // not all 11 keywords once
  expect(list.want).toEqual([9053]); // the repeat, an unknown id and the ones that are not ids go
  expect(list.keep).toEqual([9071, 9991]); // a wanted gift is not kept too
  expect(skipped).toBe(4); // "9071" and 1.5 are not ids, 12345 and 77 are no gift
  expect(list.fusion_condition).toBe("any");
  expect(list.gorder.Burn).toEqual(defaultGorder().Burn);
  expect(Object.keys(list.gorder)).toEqual(GIFT_KEYWORDS);
});

test("an import of something that is not a gift list throws", () => {
  expect(() => importGiftList("{", [], "")).toThrow();
  expect(() => importGiftList("[1]", [], "")).toThrow("not a gift list");
  expect(() => importGiftList("null", [], "")).toThrow("not a gift list");
});
