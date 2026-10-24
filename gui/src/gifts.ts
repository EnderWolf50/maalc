// What a gift list (spec 04 section 13) makes of a gift: its state, what locks it, the buy queue, the fusion to make.
// The same rules as agent/gifts.py, which tests/gift_list_cases.json pins on both sides.
import { parse as parseYaml } from "yaml";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import listsYaml from "../../assets/resource/base/data/gift_lists.yaml?raw";
import { SEARCH_GIFTS, type GiftList } from "./model";

/** The part of a gift list these rules read. */
export type ListRules = Pick<GiftList, "order" | "want" | "keep" | "gorder">;
export type GiftState = "want" | "keep" | "drop";
export interface Fusion {
  id: number; keyword: string; recipes?: number[][]; groups?: { ids: number[]; need: number }[]; specific?: boolean; packs?: number[];
}
/** gift_search.json's gifts (the buyable ones) and gift_recipes.json's gifts, the game files' unless a test passes its own. */
export interface GiftTables { buyable: { id: number }[]; fusions: Fusion[] }
const GAME_TABLES: GiftTables = { buyable: SEARCH_GIFTS, fusions: recipes.gifts };

/** The data file's default list: the fields of a gift list without id and name. */
export const DEFAULT_LIST: Omit<GiftList, "id" | "name"> = parseYaml(listsYaml).default_list;

/** The list a team's `gift_list` names: "default" is the data file's list; undefined when no list has that id. */
export const resolveList = (ref: string, lists: GiftList[]): ListRules | undefined =>
  ref === "default" ? DEFAULT_LIST : lists.find((g) => g.id === ref);

/** The first keyword of `order` that is not Keywordless: the team's main keyword. */
export const mainKeyword = (list: ListRules): string => list.order.find((k) => k !== "Keywordless")!;

/** The main keyword of the list a team's `gift_list` names; undefined when no list has that id. */
export const teamKeyword = (ref: string, lists: GiftList[]): string | undefined => {
  const list = resolveList(ref, lists);
  return list && mainKeyword(list);
};

/** "want", "keep" or "drop" (everything the list does not mention). */
export const state = (list: ListRules, id: number): GiftState => (list.want.includes(id) ? "want" : list.keep.includes(id) ? "keep" : "drop");

const materials = (f: Fusion) => [...(f.recipes ?? []).flat(), ...(f.groups ?? []).flatMap((g) => g.ids)];

/** The wanted fusions that lock a drop gift, in data-file order: it is a material of any of their recipes, or of any group.
 * A pack-specific fusion (data `specific`) only when runPacks and its `packs` share one, or runPacks is null (unknown). */
export function lockers(list: ListRules, id: number, runPacks: number[] | null = null, tables: GiftTables = GAME_TABLES): number[] {
  if (state(list, id) !== "drop") return [];
  return tables.fusions
    .filter((f) => state(list, f.id) === "want" && materials(f).includes(id)
      && (!f.specific || runPacks === null || (f.packs ?? []).some((p) => runPacks.includes(p))))
    .map((f) => f.id);
}

/** "want", "keep" (kept, or a drop gift something locks) or "drop". */
export function effective(list: ListRules, id: number, runPacks: number[] | null = null, tables: GiftTables = GAME_TABLES): GiftState {
  const own = state(list, id);
  return own === "drop" && lockers(list, id, runPacks, tables).length ? "keep" : own;
}

/** The ids to buy, first first: per keyword in `order`, its `gorder` gifts the list wants and the shop sells. */
export function queue(list: ListRules, tables: GiftTables = GAME_TABLES): number[] {
  const buyable = new Set(tables.buyable.map((g) => g.id));
  return list.order.flatMap((k) => list.gorder[k]).filter((id) => buyable.has(id) && state(list, id) === "want");
}

/** The materials to put in for a fusion, or undefined: the first recipe `owned` (id to count) has all of; for groups the
 * first `need` owned ids of each group in data-file order. A set needing more than `slots` materials (none: any) is passed over. */
function pick(f: Fusion, owned: Map<number, number>, slots = Infinity): number[] | undefined {
  const have = (id: number) => owned.get(id) ?? 0;
  for (const recipe of f.recipes ?? []) {
    if (recipe.length <= slots && recipe.every((id) => have(id) >= recipe.filter((x) => x === id).length)) return [...recipe];
  }
  const picked = (f.groups ?? []).map((g) => g.ids.filter(have).slice(0, g.need));
  if (picked.length && picked.every((p, i) => p.length === f.groups![i].need) && picked.flat().length <= slots) return picked.flat();
}

/** {gift, materials} for the first wanted fusion in list order whose materials `ownedIds` (repeats count) hold, else null.
 * List order = the keyword's place in `order` (`queue`'s), then data-file order: a fusion is in no `gorder` (that holds the
 * shop's gifts). A pack-specific fusion is made whatever the run packs.
 * `slots`: the fuse page's material slots; a recipe needing more is passed over (the next wanted one is tried). */
export function recipeFusion(list: ListRules, ownedIds: number[], tables: GiftTables = GAME_TABLES, slots?: number): { gift: number; materials: number[] } | null {
  const owned = new Map<number, number>();
  for (const id of ownedIds) owned.set(id, (owned.get(id) ?? 0) + 1);
  const place = (f: Fusion) => {
    const n = list.order.indexOf(f.keyword);
    return n < 0 ? list.order.length : n;
  };
  for (const f of [...tables.fusions].sort((a, b) => place(a) - place(b))) {
    const materials = state(list, f.id) === "want" ? pick(f, owned, slots) : undefined;
    if (materials) return { gift: f.id, materials };
  }
  return null;
}
