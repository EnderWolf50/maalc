// The click rules of the team page's sinner grid and starlight cards.
import { expect, test } from "vitest";
import {
  buyOrder, clickCard, clickEnhance, enhanceAll, gracePrice, selectAll, starlightCost, toggleSinner, type StarlightValues,
} from "./model";

test("clicking a sinner not in the order adds it at the end", () => {
  expect(toggleSinner(["Ryōshū", "Yi Sang"], "Faust")).toEqual(["Ryōshū", "Yi Sang", "Faust"]);
});

test("clicking a sinner in the order leaves it out and moves the later ones up", () => {
  expect(toggleSinner(["Ryōshū", "Yi Sang", "Faust"], "Yi Sang")).toEqual(["Ryōshū", "Faust"]);
});

test("the last sinner in the order stays", () => {
  expect(toggleSinner(["Ryōshū"], "Ryōshū")).toEqual(["Ryōshū"]);
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
