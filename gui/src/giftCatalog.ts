// Every gift the gift list tab shows: what the shop sells, the fusion gifts, the recipe materials and the vestiges, with their icons.
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import packsYaml from "../../assets/resource/base/data/theme_packs.yaml?raw";
import type { Fusion } from "./gifts";
import { SEARCH_GIFTS, VESTIGES } from "./model";

/** buyable: on the Gift Search page (tier I-III); fusion: made by fusing, so wantable but never bought; material: a recipe's
 * material the shop does not sell; vestige: sold or fused only. Only a buyable or fusion gift can be "want". */
export type Kind = "buyable" | "fusion" | "material" | "vestige";
export interface CatalogGift { id: number; keyword: string; tier: number; en: string; zh: string; kind: Kind }

// LLC's names of the vestiges (ids 9991-9995, tier I-V; model.ts VESTIGES has the English ones).
const VESTIGE_ZH = ["黯淡的殘影", "微茫的殘影", "閃耀的殘影", "輝煌的殘影", "月之殘影"];

/** The data files' order: the shop's gifts in page order, then fusion gifts, materials and vestiges. */
export const CATALOG: CatalogGift[] = [
  ...SEARCH_GIFTS.map((g): CatalogGift => ({ ...g, kind: "buyable" })),
  ...recipes.gifts.map((g): CatalogGift => ({ id: g.id, keyword: g.keyword, tier: g.tier, en: g.en, zh: g.zh, kind: "fusion" })),
  ...recipes.materials.map((g): CatalogGift => ({ id: g.id, keyword: g.keyword, tier: g.tier, en: g.en, zh: g.zh, kind: "material" })),
  ...VESTIGES.map((en, i): CatalogGift => ({ id: 9991 + i, keyword: "Keywordless", tier: i + 1, en, zh: VESTIGE_ZH[i], kind: "vestige" })),
];
export const GIFT_BY_ID = new Map(CATALOG.map((g) => [g.id, g]));

/** Whether the list may want it: the shop sells it or fusing makes it. */
export const wantable = (g: CatalogGift) => g.kind === "buyable" || g.kind === "fusion";

/** The gift's name in the GUI's language, English when the data has no Chinese one. */
export const giftName = (g: CatalogGift, zh: boolean) => (zh && g.zh ? g.zh : g.en);

const ICONS = import.meta.glob<string>("../../assets/resource/base/data/gift_icons/*.webp", { eager: true, query: "?url", import: "default" });
/** The icon's URL (assets/.../gift_icons/<id>.webp). */
export const iconUrl = (id: number): string | undefined => ICONS[`../../assets/resource/base/data/gift_icons/${id}.webp`];

const KW_ICONS = import.meta.glob<string>("../../assets/resource/base/data/keyword_icons/*.webp", { eager: true, query: "?url", import: "default" });
/** The keyword's game icon URL (assets/.../keyword_icons/<keyword>.webp); Keywordless has none. */
export const keywordIconUrl = (keyword: string): string | undefined => KW_ICONS[`../../assets/resource/base/data/keyword_icons/${keyword}.webp`];

/** A keyword's gifts by tier, highest tier first: the list's own order (`gorder`) for what the shop sells, then the rest in data order. */
export function tiersOf(gorder: Record<string, number[]>, keyword: string): { tier: number; ids: number[] }[] {
  const rest = CATALOG.filter((g) => g.keyword === keyword && g.kind !== "buyable").map((g) => g.id);
  const byTier = new Map<number, number[]>();
  for (const id of [...(gorder[keyword] ?? []), ...rest]) {
    const tier = GIFT_BY_ID.get(id)?.tier;
    if (tier) byTier.set(tier, [...(byTier.get(tier) ?? []), id]);
  }
  return [...byTier].sort((a, b) => b[0] - a[0]).map(([tier, ids]) => ({ tier, ids }));
}

/** The fusion gifts' recipe data (gift_recipes.json), in data order. */
export const FUSIONS: Fusion[] = recipes.gifts;
export const FUSION_BY_ID = new Map(FUSIONS.map((f) => [f.id, f]));
/** Every gift in a fusion's recipes (all of a group's too), once each. */
export const materialsOf = (f: Fusion): number[] => [...new Set([...(f.recipes ?? []).flat(), ...(f.groups ?? []).flatMap((g) => g.ids)])];
/** The fusion gifts that have this gift among their materials, in data order. */
export const usedIn = (id: number): Fusion[] => FUSIONS.filter((f) => materialsOf(f).includes(id));

// A theme pack's id is only in the comment after its line in theme_packs.yaml ("  Falling Flowers: N3 H23  # 1010"), until the
// data file has an id field (#306).
const PACK_LINE = /^ {2}(?:"([^"]+)"|([^:#\n]+?)):[^#\n]*#\s*(\d+)/gm;
const PACK_NAMES = new Map([...packsYaml.matchAll(PACK_LINE)].map((m): [number, string] => [Number(m[3]), m[1] ?? m[2]]));
/** A theme pack's name in the season's file; its id as "#1234" for a pack the file does not list (an Extreme-only pack). */
export const packName = (id: number): string => PACK_NAMES.get(id) ?? `#${id}`;
