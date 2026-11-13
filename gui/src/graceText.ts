// A grace card's effect text at a level, as the game prints it (#719): at + and ++ a value that differs from the base shows
// in yellow, and a line the base lacks shows in yellow whole. graces.json has the plain text of each level; which parts
// changed is found by comparing a level's lines with the base lines, not marked by hand in the data.
import { LEVELS, type Grace } from "./model";

/** A piece of a line's text; `up` when the level changed it from the base. */
export interface Run { text: string; up: boolean }
/** One effect line, and `sub` for a line that details the one above it (the game's "· " lines). */
export interface EffectLine { runs: Run[]; sub: boolean }

/** A level line at least this alike to a base line is that line with new values; less alike to every base line, a new one.
 * In graces.json (release 2026110501) each changed line is 0.64 or more alike to its base line, and each new line 0.33 or
 * less to the base lines still unpaired when its turn comes. */
const ALIKE = 0.5;

/** A number with its sign and percent sign (+250, 20%) is one token, so a changed value is marked whole; any other
 * character is a token of its own. */
const tokens = (line: string) => line.match(/[+-]?\d+(?:\.\d+)?%?|[\s\S]/gu) ?? [];

/** For each token of b, whether a longest common subsequence of a and b keeps it (the earliest match when several do). */
function kept(a: string[], b: string[]): boolean[] {
  const len = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0)); // of a[i..] and b[j..]
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) len[i][j] = a[i] === b[j] ? len[i + 1][j + 1] + 1 : Math.max(len[i + 1][j], len[i][j + 1]);
  }
  const keep = new Array<boolean>(b.length).fill(false);
  for (let i = 0, j = 0; i < a.length && j < b.length;) {
    if (a[i] === b[j]) {
      keep[j] = true;
      i++;
      j++;
    } else if (len[i + 1][j] >= len[i][j + 1]) i++;
    else j++;
  }
  return keep;
}

/** How alike two token lists are: twice their common tokens over all their tokens, 1 when equal. */
const alike = (a: string[], b: string[]) => (2 * kept(a, b).filter(Boolean).length) / (a.length + b.length || 1);

/** A line's tokens as runs; a space between two changed tokens is changed too, so a new line is one run. */
function runs(toks: string[], keep: boolean[]): Run[] {
  const up = toks.map((t, k) => !keep[k] && (!/^\s$/.test(t) || (k > 0 && !keep[k - 1] && k + 1 < toks.length && !keep[k + 1])));
  const out: Run[] = [];
  toks.forEach((t, k) => {
    const last = out[out.length - 1];
    if (last && last.up === up[k]) last.text += t;
    else out.push({ text: t, up: up[k] });
  });
  return out;
}

/** Grace g's effect lines at a level (the base lines when unselected), each with the parts that differ from the base marked.
 * Each level line is paired with at most one base line, the most alike pairs first: at ++ "進入第6層時，人格等級 +3" is a
 * new line, since "進入第1層時，人格等級 +3" is still there. */
export function effectLines(g: Grace, level: string): EffectLine[] {
  const lines = (LEVELS.indexOf(level) > 1 && g.effects[level as "plus" | "plus2"]) || g.effects.base;
  const own = lines.map(tokens), base = g.effects.base.map(tokens);
  const pairs = own.flatMap((l, i) => base.map((b, j) => ({ i, j, like: alike(b, l) })))
    .filter((p) => p.like >= ALIKE).sort((x, y) => y.like - x.like || x.i - y.i || x.j - y.j);
  const match = new Map<number, number>(), taken = new Set<number>();
  for (const p of pairs) {
    if (match.has(p.i) || taken.has(p.j)) continue;
    match.set(p.i, p.j);
    taken.add(p.j);
  }
  return lines.map((line, i) => {
    const j = match.get(i);
    return { runs: runs(own[i], j === undefined ? own[i].map(() => false) : kept(base[j], own[i])), sub: line.startsWith("·") };
  });
}
