// The starlight cards in English (#751): the effects show as in Chinese, from the client's English text, yellow where the game
// prints it; and a title sits on one line, its type shrunk to the title band down to a floor (fittedSize), wrapping only below it.
import { screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { GRACES, defaultStarlight, newSettings, type Settings } from "./model";
import css from "./index.css?raw";
import { StarlightTab, fittedSize } from "./Starlight";
import { cssRules, renderEditor } from "./testing";

/** The starlight tab in a language, on one plan whose grace n is at levels[n]; the others unselected. */
const show = (language: Settings["language"], levels: Record<number, string>) => {
  const plan = { id: "s1", name: "Plan", ...defaultStarlight() };
  for (const [n, level] of Object.entries(levels)) plan.levels[+n - 1] = level;
  return renderEditor(<StarlightTab />, { ...newSettings(), language, starlight_plans: [plan] });
};
const card = (name: string) => screen.getByRole("group", { name });
const lines = (name: string) => [...card(name).querySelectorAll("li")].map((li) => li.textContent);
const marked = (name: string) => [...card(name).querySelectorAll("mark")].map((m) => m.textContent);

describe("in English", () => {
  test("a card shows its effects as the game's English page does, at base with nothing marked", () => {
    show("en_us", {});
    // tests/screens/StarlightPage.png, the game's English starlight page
    expect(lines("Star of the Beginning")).toEqual([
      "Starting Cost +150", "Theme Pack Selection +1", "Shop E.G.O Gift Choice +1", "1 Free normal Refresh(es) for Shops"]);
    expect(lines("Starlight Guidance")).toEqual(["Max Speed +2", "Gain 1 Clash Power Up", "Gain 1 Damage Up", "Gain 1 Protection"]);
    expect(card("Star of the Beginning").querySelector("mark")).toBeNull();
  });

  test("at + and ++ a card shows that level's text, marked where the client's English text is yellow", () => {
    show("en_us", { 1: "plus2", 9: "plus" });
    expect(lines("Star of the Beginning")).toEqual([
      "Starting Cost +250", "Theme Pack Selection +1", "Shop E.G.O Gift Choice +1", "2 Free normal Refresh(es) for Shops"]);
    expect(marked("Star of the Beginning")).toEqual(["+250", "2"]);
    const comet = [...card("Chance Comet").querySelectorAll("li")];
    expect(comet.filter((li) => li.classList.contains("sub")).map((li) => li.textContent)).toEqual([
      "· Floor 5 or lower : Tier 1~3", "· Floor 6 or higher : Tier 2~3"]);
    expect(marked("Chance Comet")).toEqual([
      "· Floor 5 or lower : Tier 1~3", "· Floor 6 or higher : Tier 2~3", "/Floor 5", "selected Keyword category"]);
  });

  test("the effects describe the card's pick button, and no subtitle repeats its name", () => {
    show("en_us", { 1: "plus" });
    const pick = within(card("Star of the Beginning")).getByRole("button", { name: "Star of the Beginning+" });
    expect(pick).toHaveAccessibleDescription(/Starting Cost \+250/);
    expect(card("Star of the Beginning").querySelector("small")).toBeNull();
  });
});

test("in Chinese a card keeps LLC's Chinese effects and its English name under the title", () => {
  show("zh_tw", { 1: "plus" });
  expect(lines(GRACES[0].zh)[0]).toBe("初始經費 +250");
  expect(card(GRACES[0].zh).querySelector("small")).toHaveTextContent("Star of the Beginning");
});

// Worked examples from the real window (1500 x 860, cards 222 px wide, a title band of 119.9 px, the stylesheet's size 15.1 px)
// and the titles' widths in Barlow Condensed 700: "Cumulating Starcloud++" 8.64 em, "Star-shower" 4.47 em.
describe("a title's size", () => {
  test("stays the stylesheet's when the title fits its band", () => {
    expect(fittedSize(15.1, 4.47 * 15.1, 119.9)).toBeNull();
  });

  test("shrinks until the title fits its band, a pixel to spare", () => {
    expect(fittedSize(15.1, 8.64 * 15.1, 119.9)).toBe(13.7);
  });

  test("stops at the floor, 12 px, where the title may wrap", () => {
    expect(fittedSize(15.1, 12 * 15.1, 119.9)).toBe(12);
  });

  // the stylesheet takes --fit over its own size: Plans.test.tsx "a card is wide enough for its longest title on one line"
  test("of an English title is in the game's narrow display face", () => {
    expect(cssRules(css).find((r) => r.selector === ".grace .title:lang(en)")?.body).toMatch(/font-family:\s*var\(--font-display\)/);
  });
});
