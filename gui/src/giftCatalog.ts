// Every gift the gift list tab shows: the Gift Search page's, the fusion gifts, the recipe materials, the other gifts and the vestiges, with their icons
// and their effect text.
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import packsYaml from "../../assets/resource/base/data/theme_packs.yaml?raw";
import effects from "./gift_effects.json";
import plates from "./gift_plates/plates.json";
import { FUSIONS, materialsOf, type Fusion } from "./gifts";
import { GIFT_SOURCES, SHOP_GIFTS, parseThemePacks, type DataGift } from "./model";
import { webpFolder } from "./webpFolder";

/** buyable: a shop may sell it (SHOP_GIFTS, #626: the drop pool less its global excludes and the fusion gifts), tier I-IV;
 * fusion: made by fusing, so wantable but never bought; material: a recipe's material no shop sells; other: no shop sells it
 * and no recipe uses it, a keyword fusion or an event gives one; vestige: sold or fused only. Only a buyable or fusion gift
 * can be "want". */
export type Kind = "buyable" | "fusion" | "material" | "other" | "vestige";
export interface CatalogGift extends DataGift { kind: Kind }

const SOLD = new Set(SHOP_GIFTS.map((g) => g.id));
const USED = new Set(FUSIONS.flatMap(materialsOf));
const kindOf = (g: { id: number }, unsold: Kind): Kind => (SOLD.has(g.id) ? "buyable" : USED.has(g.id) ? "material" : unsold);

/** A data file's gift as the catalog holds it: its own fields (a fusion gift's recipes left out) and its kind. */
const entry = ({ id, keyword, tier, en, zh }: DataGift, kind: Kind): CatalogGift => ({ id, keyword, tier, en, zh, kind });
/** The data files' order (GIFT_SOURCES): the Gift Search page's gifts in page order, then fusion gifts, materials, other gifts and
 * vestiges. */
export const CATALOG: CatalogGift[] = [
  ...GIFT_SOURCES.search.map((g) => entry(g, kindOf(g, "other"))),
  ...GIFT_SOURCES.fusion.map((g) => entry(g, "fusion")),
  ...GIFT_SOURCES.material.map((g) => entry(g, kindOf(g, "material"))),
  ...GIFT_SOURCES.other.map((g) => entry(g, kindOf(g, "other"))),
  ...GIFT_SOURCES.vestige.map((g) => entry(g, "vestige")),
];
export const GIFT_BY_ID = new Map(CATALOG.map((g) => [g.id, g]));

/** Whether the list may want it: the shop sells it or fusing makes it. */
export const wantable = (g: CatalogGift) => g.kind === "buyable" || g.kind === "fusion";

/** A colour of a gift's effect text, by its name in the game's ColorCode table (a status word's buffType; Neutral for flavour
 * text). */
export type Colour = "Positive" | "Negative" | "Neutral";
/** A run of a gift's effect text (gift_effects.json, tools/llc_text.py effect_runs): plain text, a status word (狀態詞, the
 * game's `[tag]`, by its id) the game draws as its status icon and its name, or italic or coloured text (flavour text). */
export type EffectRun = string | { kw: string } | { text: string; i?: boolean; colour?: Colour };
/** A status word of the effect texts (gift_effects.json `keywords`; not a gift's keyword, its 體系): the colour its name is
 * printed in, its status icon (buf_icons/<icon>.webp) and its names. */
export interface StatusWord { colour: Colour; icon: string; en: string; zh: string }
export const STATUS_WORDS = effects.keywords as Record<string, StatusWord>;
/** A gift's sin, its attributeType in the game's data (ATTRIBUTE_TYPE 0..6). */
export type Sin = keyof typeof plates.plates;
const EFFECTS = effects.effects as Record<string, { sin: Sin; en: EffectRun[]; zh: EffectRun[] }>;
/** The gift's effect text in the GUI's language, as the game's gift panel prints it (gift_effects.json, #721, #764). */
export const giftEffect = (id: number, zh: boolean): EffectRun[] | undefined => EFFECTS[id]?.[zh ? "zh" : "en"];
/** The gift's sin (gift_effects.json, tools/llc_text.py gift_sins): the colour of the plate the game draws its name on (#786). */
export const giftSin = (id: number): Sin | undefined => EFFECTS[id]?.sin;
/** A status word's icon URL (gui/src/buf_icons/<icon>.webp, tools/buf_icons.py). */
export const bufIconUrl = webpFolder(import.meta.glob<string>("./buf_icons/*.webp", { eager: true, query: "?url", import: "default" }));
const plateUrl = webpFolder(import.meta.glob<string>("./gift_plates/*.webp", { eager: true, query: "?url", import: "default" }));
/** A sin's name plate (gui/src/gift_plates/, tools/gift_plates.py): the game's plate sprite tinted by the sin's colour, and
 * the ink the name holds 4.5:1 in on it, dark on a bright plate, light on the others. */
export const plateOf = (sin: Sin) => {
  const { ink } = plates.plates[sin] as { ink: keyof typeof plates.inks };
  return { url: plateUrl(sin)!, ink, colour: plates.inks[ink] };
};

/** The icon's URL (assets/.../gift_icons/<id>.webp). */
export const iconUrl = webpFolder(import.meta.glob<string>("../../assets/resource/base/data/gift_icons/*.webp", { eager: true, query: "?url", import: "default" }));

/** The keyword's game icon URL (assets/.../keyword_icons/<keyword>.webp); Keywordless has none. */
export const keywordIconUrl = webpFolder(import.meta.glob<string>("../../assets/resource/base/data/keyword_icons/*.webp", { eager: true, query: "?url", import: "default" }));

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
