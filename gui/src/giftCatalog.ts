// Every gift the gift list tab shows: the Gift Search page's, the fusion gifts, the recipe materials, the other gifts and the vestiges, with their icons.
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import packsYaml from "../../assets/resource/base/data/theme_packs.yaml?raw";
import { FUSIONS, materialsOf, type Fusion } from "./gifts";
import { SEARCH_GIFTS, SHOP_GIFTS, VESTIGES, parseThemePacks } from "./model";

/** buyable: a shop may sell it (SHOP_GIFTS, #626: the drop pool less its global excludes and the fusion gifts), tier I-IV;
 * fusion: made by fusing, so wantable but never bought; material: a recipe's material no shop sells; other: no shop sells it
 * and no recipe uses it, a keyword fusion or an event gives one; vestige: sold or fused only. Only a buyable or fusion gift
 * can be "want". */
export type Kind = "buyable" | "fusion" | "material" | "other" | "vestige";
export interface CatalogGift { id: number; keyword: string; tier: number; en: string; zh: string; kind: Kind }

const SOLD = new Set(SHOP_GIFTS.map((g) => g.id));
const USED = new Set(FUSIONS.flatMap(materialsOf));
const kindOf = (g: { id: number }, unsold: Kind): Kind => (SOLD.has(g.id) ? "buyable" : USED.has(g.id) ? "material" : unsold);

/** The data files' order: the Gift Search page's gifts in page order, then fusion gifts, materials, other gifts and vestiges. */
export const CATALOG: CatalogGift[] = [
  ...SEARCH_GIFTS.map((g): CatalogGift => ({ ...g, kind: kindOf(g, "other") })),
  ...recipes.gifts.map((g): CatalogGift => ({ id: g.id, keyword: g.keyword, tier: g.tier, en: g.en, zh: g.zh, kind: "fusion" })),
  ...recipes.materials.map((g): CatalogGift => ({ id: g.id, keyword: g.keyword, tier: g.tier, en: g.en, zh: g.zh, kind: kindOf(g, "material") })),
  ...recipes.extra_gifts.map((g): CatalogGift => ({ id: g.id, keyword: g.keyword, tier: g.tier, en: g.en, zh: g.zh, kind: kindOf(g, "other") })),
  ...VESTIGES.map((g): CatalogGift => ({ ...g, kind: "vestige" })),
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

export const FUSION_BY_ID = new Map(FUSIONS.map((f) => [f.id, f]));
/** The fusion gifts that have this gift among their materials, in data order. */
export const usedIn = (id: number): Fusion[] => FUSIONS.filter((f) => materialsOf(f).includes(id));

const PACK_NAMES = new Map(Object.entries(parseThemePacks(packsYaml).pack_ids).map(([name, id]): [number, string] => [id, name]));
/** A theme pack's name in the season's file (its `pack_ids`); its id as "#1234" for a pack the file does not know. */
export const packName = (id: number): string => PACK_NAMES.get(id) ?? `#${id}`;

/** The theme packs whose own pool (`pack_gifts`) holds the gift, by id: the only packs it shows in. */
export const packsOf = (id: number): number[] =>
  Object.entries(recipes.pack_gifts).filter(([, pool]) => pool.includes(id)).map(([pack]) => Number(pack)).sort((a, b) => a - b);
