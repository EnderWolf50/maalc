// The click rules of the team page's sinner grid and starlight selectors.
import { expect, test } from "vitest";
import { clickLevel, lowestLevel, starlightCost, toggleSinner } from "./model";

test("clicking a sinner not in the order adds it at the end", () => {
  expect(toggleSinner(["Ryōshū", "Yi Sang"], "Faust")).toEqual(["Ryōshū", "Yi Sang", "Faust"]);
});

test("clicking a sinner in the order leaves it out and moves the later ones up", () => {
  expect(toggleSinner(["Ryōshū", "Yi Sang", "Faust"], "Yi Sang")).toEqual(["Ryōshū", "Faust"]);
});

test("the last sinner in the order stays", () => {
  expect(toggleSinner(["Ryōshū"], "Ryōshū")).toEqual(["Ryōshū"]);
});

test("a starlight segment raises the level to it, or lowers it below a lit one", () => {
  // segments: 0 = the boost itself, 1 = +, 2 = ++
  expect(clickLevel("none", 0)).toBe("base");
  expect(clickLevel("none", 2)).toBe("plus2");
  expect(clickLevel("base", 1)).toBe("plus");
  expect(clickLevel("plus2", 2)).toBe("plus");
  expect(clickLevel("plus2", 0)).toBe("none");
  expect(clickLevel("base", 0)).toBe("none");
});

test("the starlight total is each bought boost's base price times 1, 2 or 3", () => {
  const levels = ["base", "plus2", "none", "none", "none", "none", "none", "none", "none", "plus"];
  expect(starlightCost(levels)).toBe(10 + 30 + 120); // spec 04 section 7 prices
  expect(starlightCost(Array(10).fill("none"))).toBe(0);
});

test("the select-all selector shows the level every boost has at least", () => {
  expect(lowestLevel(["plus2", "plus", "plus2"])).toBe("plus");
  expect(lowestLevel(["plus2", "none"])).toBe("none");
});
