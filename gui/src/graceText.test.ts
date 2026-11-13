// What graceText marks on every grace of graces.json at every level (#719): a line the base has word for word is never
// marked, a line it lacks always is, and the text shown is the level's own, so new data from tools/llc_text.py stays checked.
import { describe, expect, test } from "vitest";
import { effectLines } from "./graceText";
import { GRACES } from "./model";

const shown = (g: (typeof GRACES)[number], level: string) =>
  effectLines(g, level).map((l) => ({ text: l.runs.map((r) => r.text).join(""), marked: l.runs.filter((r) => r.up).map((r) => r.text) }));

/** Whether `line` is `base` with some characters left out: each of its characters found in `base`, in order. */
function dropsFrom(base: string, line: string) {
  let i = 0;
  for (const ch of base) if (ch === line[i]) i++;
  return i === line.length;
}

describe.each(GRACES.map((g, i) => [`${i + 1} ${g.en}`, g] as const))("grace %s", (_, g) => {
  test("unselected and at base it shows the base lines, nothing marked", () => {
    for (const level of ["none", "base"]) {
      expect(shown(g, level)).toEqual(g.effects.base.map((text) => ({ text, marked: [] })));
    }
  });

  test.each(["plus", "plus2"] as const)("at %s it shows that level's lines; a base line is plain, a line with new text is marked", (level) => {
    const lines = shown(g, level);
    expect(lines.map((l) => l.text)).toEqual(g.effects[level]);
    for (const l of lines) {
      if (g.effects.base.includes(l.text)) expect(l.marked).toEqual([]);
      // unmarked, a line only drops words from a base line (Chance Comet's "進入商店時，獲得1件合成·售賣專用飾品")
      else if (!l.marked.join("").trim()) expect(g.effects.base.some((b) => dropsFrom(b, l.text))).toBe(true);
    }
  });
});

test("a line the level adds is marked whole, one changed in its values only there", () => {
  const favor = GRACES[6]; // Favor of the Nebulae: ++ adds a line that resembles the base's first one
  expect(shown(favor, "plus2").map((l) => l.marked)).toEqual([[], ["進入第6層時，人格等級 +3"], ["+9"]]);
});
