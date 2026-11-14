// A grace card's effect text at a level, as the game prints it (#719, #733, #751): at + and ++ the text the game prints yellow
// is marked. graces.json says which runs those are, from the game's own text markup (tools/llc_text.py), in each language.
import { LEVELS, type Grace, type TextRun } from "./model";

/** One effect line, and `sub` for a line that details the one above it (the game's "· " lines). */
export interface EffectLine { runs: TextRun[]; sub: boolean }

/** Grace g's effect lines at a level (the base lines when unselected), in Chinese or in English. */
export function effectLines(g: Grace, level: string, zh: boolean): EffectLine[] {
  const effects = g.effects[zh ? "zh" : "en"];
  const lines = (LEVELS.indexOf(level) > 1 && effects[level as "plus" | "plus2"]) || effects.base;
  return lines.map((runs) => ({ runs, sub: runs[0].text.startsWith("·") }));
}
