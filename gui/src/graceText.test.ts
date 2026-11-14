// What effectLines shows of every grace of graces.json at every level (#719, #733): the level's own lines, yellow where the
// game's text markup is (tools/llc_text.py carries it into the data), so new data from the tool stays checked.
import { describe, expect, test } from "vitest";
import { effectLines } from "./graceText";
import { GRACES } from "./model";
import { textOf } from "./testing";

const shown = (g: (typeof GRACES)[number], level: string) =>
  effectLines(g, level).map((l) => ({ text: textOf(l.runs), marked: l.runs.filter((r) => r.up).map((r) => r.text) }));

describe.each(GRACES.map((g, i) => [`${i + 1} ${g.en}`, g] as const))("grace %s", (_, g) => {
  test("unselected and at base it shows the base lines, nothing marked, as the game's base text has no yellow", () => {
    for (const level of ["none", "base"]) {
      expect(effectLines(g, level).map((l) => l.runs)).toEqual(g.effects.base);
      expect(shown(g, level).flatMap((l) => l.marked)).toEqual([]);
    }
  });

  test.each(["plus", "plus2"] as const)("at %s it shows that level's lines, marked where the data marks them", (level) => {
    expect(effectLines(g, level).map((l) => l.runs)).toEqual(g.effects[level]);
  });
});

// A guard, not proof of #733: the old code found these lines from plain strings, this one from the runs.
test("a line that starts with · details the line above it", () => {
  const comet = GRACES[8]; // Chance Comet: at + the two floor ranges of its first line
  expect(effectLines(comet, "plus").map((l) => l.sub)).toEqual([false, true, true, false, false]);
});
