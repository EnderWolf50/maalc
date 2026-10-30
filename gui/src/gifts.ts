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
/** The fusion gifts' recipe data (gift_recipes.json), in data order. */
export const FUSIONS: Fusion[] = recipes.gifts;
const GAME_TABLES: GiftTables = { buyable: SEARCH_GIFTS, fusions: FUSIONS };

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

/** Every gift in a fusion's recipes (all of a group's too), once each. */
export const materialsOf = (f: Fusion): number[] => [...new Set([...(f.recipes ?? []).flat(), ...(f.groups ?? []).flatMap((g) => g.ids)])];

/** Whether the list still makes a fusion: wanted, not in `owned` (the gifts held; none when unknown), and not pack-specific
 * (data `specific`) unless runPacks and its `packs` share one, or runPacks is null (unknown). */
const toMake = (list: ListRules, f: Fusion, runPacks: number[] | null, owned: number[]) =>
  state(list, f.id) === "want" && !owned.includes(f.id) && (!f.specific || runPacks === null || (f.packs ?? []).some((p) => runPacks.includes(p)));

/** The fusions the list still makes (toMake) that lock a drop gift, in data-file order: it is a material of any of their
 * recipes, or of any group. A wanted fusion owned locks nothing: it is made no more (the user, 2026-10-30). */
export function lockers(list: ListRules, id: number, runPacks: number[] | null = null, tables: GiftTables = GAME_TABLES, owned: number[] = []): number[] {
  if (state(list, id) !== "drop") return [];
  return tables.fusions.filter((f) => materialsOf(f).includes(id) && toMake(list, f, runPacks, owned)).map((f) => f.id);
}

/** "want", "keep" (kept, or a drop gift something locks) or "drop". */
export function effective(list: ListRules, id: number, runPacks: number[] | null = null, tables: GiftTables = GAME_TABLES, owned: number[] = []): GiftState {
  const own = state(list, id);
  return own === "drop" && lockers(list, id, runPacks, tables, owned).length ? "keep" : own;
}

/** The ids to buy, first first: per keyword in `order`, its `gorder` gifts the list wants and the shop sells. */
export function queue(list: ListRules, tables: GiftTables = GAME_TABLES): number[] {
  const buyable = new Set(tables.buyable.map((g) => g.id));
  return list.order.flatMap((k) => list.gorder[k]).filter((id) => buyable.has(id) && state(list, id) === "want");
}

/** The fusions in list order: the keyword's place in `order` (`queue`'s), then data-file order (a fusion is in no `gorder`,
 * which holds the shop's gifts). */
function inListOrder(list: ListRules, fusions: Fusion[]): Fusion[] {
  const place = (f: Fusion) => {
    const n = list.order.indexOf(f.keyword);
    return n < 0 ? list.order.length : n;
  };
  return [...fusions].sort((a, b) => place(a) - place(b));
}

const counts = (ids: number[]) => {
  const held = new Map<number, number>();
  for (const id of ids) held.set(id, (held.get(id) ?? 0) + 1);
  return held;
};

/** What the shop buys, first first: [id, null] for each gift of `queue` (the list wants it), then [id, fusion id] for each
 * gift the shop sells that a fusion the list still makes (toMake; in recipeFusion's order) lacks: none once `owned` completes
 * one of its recipes or its groups; else each id a recipe needs more of than owned, and the ids not owned of a group short
 * of its `need`. Each id once, for its first reason. A material keeps its own state, and is bought no more once its fusion
 * is owned (the user, 2026-10-30). A pack-specific fusion buys nothing while runPacks is null (the agent restarted mid-run):
 * the run may never have pulled its pack; its materials stay locked all the same (lockers). */
export function purchases(list: ListRules, runPacks: number[] | null = null, owned: number[] = [], tables: GiftTables = GAME_TABLES): [number, number | null][] {
  const buyable = new Set(tables.buyable.map((g) => g.id)), held = counts(owned), have = (id: number) => held.get(id) ?? 0;
  const out = new Map<number, number | null>(queue(list, tables).map((id) => [id, null]));
  for (const f of inListOrder(list, tables.fusions)) {
    if ((f.specific && runPacks === null) || !toMake(list, f, runPacks, owned) || pick(f, held)) continue;
    const short = [
      ...(f.recipes ?? []).flatMap((r) => [...counts(r)].filter(([id, n]) => have(id) < n).map(([id]) => id)),
      ...(f.groups ?? []).filter((g) => g.ids.filter(have).length < g.need).flatMap((g) => g.ids.filter((id) => !have(id))),
    ];
    for (const id of short) if (buyable.has(id) && !out.has(id)) out.set(id, f.id);
  }
  return [...out];
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

/** {gift, materials} for the first wanted fusion in list order (inListOrder) whose materials `ownedIds` (repeats count) hold,
 * else null. A pack-specific fusion is made whatever the run packs. A fusion already owned is not made again. Every owned gift
 * is a material, whatever its state: a wanted fusion comes before any keep (the user, 2026-10-30: "want is the highest
 * priority, it may eat a keep"). `slots`: the fuse page's material slots; a recipe needing more is passed over (the next
 * wanted one is tried). */
export function recipeFusion(list: ListRules, ownedIds: number[], tables: GiftTables = GAME_TABLES, slots?: number): { gift: number; materials: number[] } | null {
  const owned = counts(ownedIds);
  for (const f of inListOrder(list, tables.fusions)) {
    const materials = state(list, f.id) === "want" && !ownedIds.includes(f.id) ? pick(f, owned, slots) : undefined;
    if (materials) return { gift: f.id, materials };
  }
  return null;
}
