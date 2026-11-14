// What effectLines shows of every grace of graces.json at every level, in both languages (#719, #733, #751): the level's own
// lines, yellow where the game's text markup is (tools/llc_text.py carries it into the data), so new data from the tool stays
// checked.
import { describe, expect, test } from "vitest";
import { effectLines } from "./graceText";
import { GRACES } from "./model";
import { textOf } from "./testing";

const shown = (g: (typeof GRACES)[number], level: string, zh: boolean) =>
  effectLines(g, level, zh).map((l) => ({ text: textOf(l.runs), marked: l.runs.filter((r) => r.up).map((r) => r.text) }));

describe.each(GRACES.flatMap((g, i) => (["zh", "en"] as const).map((lang) => [`${i + 1} ${g.en} (${lang})`, g, lang] as const)))(
  "grace %s", (_, g, lang) => {
    const zh = lang === "zh";
    test("unselected and at base it shows the base lines, nothing marked, as the game's base text has no yellow", () => {
      for (const level of ["none", "base"]) {
        expect(effectLines(g, level, zh).map((l) => l.runs)).toEqual(g.effects[lang].base);
        expect(shown(g, level, zh).flatMap((l) => l.marked)).toEqual([]);
      }
    });

    test.each(["plus", "plus2"] as const)("at %s it shows that level's lines, marked where the data marks them", (level) => {
      expect(effectLines(g, level, zh).map((l) => l.runs)).toEqual(g.effects[lang][level]);
    });
  });

test("each language shows its own text: English in English, Chinese in Chinese", () => {
  const star = GRACES[0]; // Star of the Beginning at ++: the game's English page, and LLC's Chinese
  expect(shown(star, "plus2", false)[3]).toEqual({ text: "2 Free normal Refresh(es) for Shops", marked: ["2"] });
  expect(shown(star, "plus2", true)[3]).toEqual({ text: "可免費進行商店普通刷新 2次", marked: ["2次"] });
});

// A guard, not proof of #733: the old code found these lines from plain strings, this one from the runs.
test("a line that starts with · details the line above it, in either language", () => {
  const comet = GRACES[8]; // Chance Comet: at + the two floor ranges of its first line
  for (const zh of [true, false]) expect(effectLines(comet, "plus", zh).map((l) => l.sub)).toEqual([false, true, true, false, false]);
});
