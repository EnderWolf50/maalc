// A grace card's effect text at a level, as the game prints it (#719, #733): at + and ++ the text the game prints yellow is
// marked. graces.json says which runs those are, from the game's own text markup (tools/llc_text.py).
import { LEVELS, type Grace, type Run } from "./model";

/** One effect line, and `sub` for a line that details the one above it (the game's "· " lines). */
export interface EffectLine { runs: Run[]; sub: boolean }

/** Grace g's effect lines at a level (the base lines when unselected). */
export function effectLines(g: Grace, level: string): EffectLine[] {
  const lines = (LEVELS.indexOf(level) > 1 && g.effects[level as "plus" | "plus2"]) || g.effects.base;
  return lines.map((runs) => ({ runs, sub: runs[0].text.startsWith("·") }));
}
