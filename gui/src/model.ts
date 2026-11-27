// Settings types and the values that come from agent/settings.schema.json (docs/spec/04-settings.md).
import { giftList as giftListCheck } from "virtual:settings-validator";
import { parse as parseYaml } from "yaml";
import schema from "../../agent/settings.schema.json";
import { graces, packNames, recipes, search as gifts, shopYaml, themePacksYaml } from "./gameData";

export { schema };

const P = schema.properties;
const TEAM = P.teams.items.properties;

export const SINNERS: string[] = schema.$defs.order.default;
export const LEVELS: string[] = schema.$defs.levels.items.enum;
export const VERSION: number = P.version.const;
/** Spec 04 section 7: the graces numbered 1-10, English names and effect text as the game client has them, Chinese name and
 * effect text from LLC (graces.json carries its sources and license). */
export const GRACES: Grace[] = graces.graces;
/** A piece of a grace's effect line; `up` where the game prints it yellow, what a + or ++ level changed (#733). */
export interface TextRun { text: string; up: boolean }
/** Each level's effect lines, a line as its runs. */
export interface GraceEffects { base: TextRun[][]; plus?: TextRun[][]; plus2?: TextRun[][] }
/** A grace's names and its effects in each language (#751). */
export interface Grace { en: string; zh: string; effects: { en: GraceEffects; zh: GraceEffects } }

/** Enum values of a team field, in schema order. */
export const teamEnum = (k: keyof typeof TEAM) => (TEAM[k] as { enum: string[] }).enum;

export type Order = string[];

/** A skill swap of the shop (#264, #454): one skill `from` becomes one skill `to`; `shop` is the Replace <sinner>'s Skill cell's
 * price in Cost, `id_search` the ID Skill Search's price in Cost or starlight. The GUI names a swap by `from` and `to` and shows
 * no price; the prices are for the agent (#455). */
export interface SkillSwap { from: number; to: number; shop: number; id_search: { cost: number; starlight: number } }
export type SkillSwapKey = "s1_s3" | "s2_s3" | "s1_s2";
/** data/shop.yaml's skill_replacement, keyed by swap; the agent reads the same entry, the screen's own price wins when the bot taps. */
export const SKILL_SWAPS: Record<SkillSwapKey, SkillSwap> = parseYaml(shopYaml).skill_replacement;
/** A sinner's target counts: skill 1, 2 and 3 in a deck of 6. */
export interface SkillTarget { s1: number; s2: number; s3: number }
/** The game's deck: 3 of skill 1, 2 of skill 2, 1 of skill 3; a sinner at it is left alone. */
export const GAME_DECK: SkillTarget = { s1: 3, s2: 2, s3: 1 };
/** Why a target can never be reached: a count that is not a whole number 0 to 6 (the schema's rule; a hand-edited file still
 * opens with it), a total other than 6, or, since every swap moves a card up from 3/2/1, S1 above 3 or S3 below 1. */
export type SkillFault = "range" | "total" | "s1" | "s3";
/** What a target takes from the game's 3/2/1 (spec 04 section 9, #264): a swap a→b counts only while skill a is above its target
 * and skill b below it, so the swaps are fixed. With S2 above 2, S1→S2 × (S2 − 2) and S1→S3 × (S3 − 1); otherwise S2→S3 × (2 − S2)
 * and S1→S3 × (3 − S1). `need` lists them with S1→S3 last, and is empty for a target with faults (validate.ts reports those). */
export function skillPlan(t: SkillTarget): { untouched: boolean; faults: SkillFault[]; need: { key: SkillSwapKey; n: number }[] } {
  const untouched = t.s1 === GAME_DECK.s1 && t.s2 === GAME_DECK.s2 && t.s3 === GAME_DECK.s3;
  const faults: SkillFault[] = [];
  if (![t.s1, t.s2, t.s3].every((v) => Number.isInteger(v) && v >= 0 && v <= 6)) return { untouched, faults: ["range"], need: [] };
  if (t.s1 + t.s2 + t.s3 !== 6) faults.push("total");
  if (t.s1 > GAME_DECK.s1) faults.push("s1");
  if (t.s3 < GAME_DECK.s3) faults.push("s3");
  if (faults.length) return { untouched, faults, need: [] };
  const counts: [SkillSwapKey, number][] = t.s2 > GAME_DECK.s2
    ? [["s1_s2", t.s2 - GAME_DECK.s2], ["s1_s3", t.s3 - GAME_DECK.s3]]
    : [["s2_s3", GAME_DECK.s2 - t.s2], ["s1_s3", GAME_DECK.s1 - t.s1]];
  return { untouched, faults, need: counts.filter(([, n]) => n > 0).map(([key, n]) => ({ key, n })) };
}
export type SkillPay = "cost" | "starlight";
/** Spec 04 section 9 skill_replacement: only the sinners to change, in priority order, each with its target; s1_s3_first says
 * which kind of swap to try first when the target needs two. */
export interface SkillSinner { sinner: string; target: SkillTarget; s1_s3_first: boolean }
export interface SkillReplacement { sinners: SkillSinner[]; id_skill_search: { enabled: boolean; pay: SkillPay } }
export const SKILL_PAYMENTS: SkillPay[] = TEAM.skill_replacement.properties.id_skill_search.properties.pay.enum as SkillPay[];

/** Spec 04 section 7: base prices; + and ++ cost 2x and 3x (agent/run_start.py GRACE_BASE). */
export const BOOST_COST = [10, 10, 20, 20, 30, 30, 40, 40, 50, 60];
/** What grace n (1-10) costs at a level: what its card shows in the game's top-right corner, 0 when unselected. */
export const gracePrice = (n: number, level: string) => BOOST_COST[n - 1] * LEVELS.indexOf(level);
export const starlightCost = (levels: string[]) => levels.reduce((sum, l, i) => sum + gracePrice(i + 1, l), 0);

/** The selected graces in buying order: the order they were selected in (spec 04 section 7). */
export const buyOrder = (v: StarlightValues) => v.priority.filter((n) => v.levels[n - 1] !== "none");

/** Grace n at a level; a newly selected grace goes after the selected ones, a dropped one to the end. */
function setGrace(v: StarlightValues, n: number, level: string): StarlightValues {
  const was = v.levels[n - 1] !== "none";
  const levels = v.levels.map((l, i) => (i === n - 1 ? level : l));
  if (was === (level !== "none")) return { ...v, levels };
  const rest = v.priority.filter((x) => x !== n);
  const chosen = rest.filter((x) => levels[x - 1] !== "none");
  const priority = level === "none" ? [...rest, n] : [...chosen, n, ...rest.filter((x) => !chosen.includes(x))];
  return { ...v, levels, priority };
}

/** The card itself: select at base, or unselect at any level. */
export const clickCard = (v: StarlightValues, n: number) => setGrace(v, n, v.levels[n - 1] === "none" ? "base" : "none");

/** The card's + (1) or ++ (2): select at that level; the lit button goes back to base. */
export function clickEnhance(v: StarlightValues, n: number, plus: 1 | 2) {
  const level = LEVELS[plus + 1];
  return setGrace(v, n, v.levels[n - 1] === level ? "base" : level);
}

const allTo = (v: StarlightValues, level: (l: string) => string) =>
  v.levels.reduce((acc, l, i) => setGrace(acc, i + 1, level(l)), v);

/** Every grace selected: Select All Graces then clears them, and its button is lit. */
export const allSelected = (v: StarlightValues) => !v.levels.includes("none");
/** Every grace at + (1) or ++ (2): Enhance All of that level then puts them back to base, and its button is lit. */
export const allEnhanced = (v: StarlightValues, plus: 1 | 2) => v.levels.every((l) => l === LEVELS[plus + 1]);

/** Select All Graces: the unselected ones at base, or none when all are selected. */
export const selectAll = (v: StarlightValues) =>
  allSelected(v) ? allTo(v, () => "none") : allTo(v, (l) => (l === "none" ? "base" : l));

/** Enhance All + (1) or ++ (2): every grace at that level, or back to base when all already are. */
export function enhanceAll(v: StarlightValues, plus: 1 | 2) {
  const level = allEnhanced(v, plus) ? "base" : LEVELS[plus + 1];
  return allTo(v, () => level);
}

/** The E.G.O Gift Search page's tabs, left to right (agent/settings.schema.json gift_search keywords). */
export const SEARCH_TABS: string[] = schema.$defs.gift.properties.keyword.enum;
/** Vestiges, tier I-V in this order (#161): ids 9991-9995, from data/gift_recipes.json. */
export const VESTIGES = recipes.vestiges;
/** Spec 04 section 9: the gifts the search page offers, in page order; ids, tiers and English names from the game's
 * static data, Chinese names from LLC (data/gift_search.json carries its sources and license). */
export const SEARCH_GIFTS: SearchGift[] = gifts.gifts;
/** A gift as a data file lists it: its id, keyword, tier and names. */
export interface DataGift { id: number; keyword: string; tier: number; en: string; zh: string }
/** A gift the E.G.O Gift Search page offers. */
export type SearchGift = DataGift;
/** Every gift the data files list, by where they list it: the search page's (data/gift_search.json), then data/gift_recipes.json's
 * fusion gifts, the recipe materials the search page lacks, the game's other gifts (extra_gifts: a shop, a keyword fusion or an
 * event gives one, #332) and the vestiges (spec 05). A list names them by their keyword; the gift list tab shows them all
 * (giftCatalog.ts CATALOG). */
export const GIFT_SOURCES: Record<"search" | "fusion" | "material" | "other" | "vestige", DataGift[]> = {
  search: SEARCH_GIFTS, fusion: recipes.gifts, material: recipes.materials, other: recipes.extra_gifts, vestige: VESTIGES,
};
/** The gifts a shop may sell (#626, data/gift_recipes.json `shop.sells`; agent/settings.py shop_gifts): the search page's in
 * page order, then the materials' and extra_gifts' in data order. A list may want them, and the shop buys them. */
const SOLD = new Set(recipes.shop.sells);
export const SHOP_GIFTS: SearchGift[] = [...SEARCH_GIFTS, ...recipes.materials, ...recipes.extra_gifts].filter((g) => SOLD.has(g.id));

/** The game searches 3 gifts at most; agent/settings.schema.json caps gift_search.gifts the same. */
export const MAX_GIFTS: number = TEAM.gift_search.properties.gifts.maxItems;
const sameGift = (a: GiftRef, b: GiftRef) => a.keyword === b.keyword && a.tier === b.tier && a.name === b.name;
/** A gift card's click: add the gift at the end of the list (up to max), or take it out. */
export const toggleGift = (list: GiftRef[], gift: GiftRef, max = MAX_GIFTS) =>
  list.some((g) => sameGift(g, gift)) ? list.filter((g) => !sameGift(g, gift))
    : list.length >= max ? list : [...list, gift];

/** The sinner grid's click (spec 04 section 6): add at the end, or leave out; the last one stays. */
export function toggleSinner(order: Order, sinner: string): Order {
  if (!order.includes(sinner)) return [...order, sinner];
  return order.length === 1 ? order : order.filter((x) => x !== sinner);
}
export interface StarlightValues { levels: string[]; priority: number[]; convert_leftover: boolean }
export interface DeploymentPlan { id: string; name: string; order: Order }
export interface StarlightPlan extends StarlightValues { id: string; name: string }
/** Spec 04 section 8 (#240): a weight -10..10 per pack, the refresh threshold, the weight of a pack not listed or not
 * read, and the event packs' mode. */
export interface PackPlanValues { weights: Record<string, number>; threshold: number; unlisted: number; event_packs: string }
export interface ThemePackPlan extends PackPlanValues { id: string; name: string }
/** A theme pack's floors (spec 05 section 2, #387): N (NORMAL) and H (HARD) list the floors 1-15, I (INFINITY) and X (EXTREME)
 * are true where it shows on every floor of that mode. */
export interface PackFloors { N?: number[]; H?: number[]; I?: true; X?: true }
/** assets/resource/base/data/theme_packs.yaml (spec 05 section 2): the season's packs with their floors, every pack's id by
 * name (also packs the list leaves out, #306) and the locked default plan. */
export interface ThemePacks { packs: Record<string, PackFloors>; pack_ids: Record<string, number>; default_plan: PackPlanValues }

export const EVENT_MODES: string[] = P.theme_pack_plans.items.properties.event_packs.enum;
export const newPackPlan = (): PackPlanValues => ({ weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" });

export function parseThemePacks(text: string): ThemePacks {
  const data = (parseYaml(text) ?? {}) as Partial<ThemePacks>;
  return { packs: data.packs ?? {}, pack_ids: data.pack_ids ?? {}, default_plan: { ...newPackPlan(), ...data.default_plan } };
}
/** The season's theme pack data file, read when the window starts (gameData.ts). */
export const THEME_PACKS: ThemePacks = parseThemePacks(themePacksYaml);
/** Each pack's Chinese name by its name (#899): theme_pack_names.json's name of its id in `pack_ids`, from LLC. A pack LLC has
 * not named, or one the data file lacks, has none, and shows its English name. */
const PACK_ZH: Record<string, string> = Object.fromEntries(Object.entries(THEME_PACKS.pack_ids).flatMap(([name, id]) => {
  const zh = (packNames.packs as Record<string, { zh: string } | undefined>)[String(id)]?.zh;
  return zh ? [[name, zh]] : [];
}));
/** A pack's name in the Chinese UI (`zh`): its Chinese name (PACK_ZH); undefined in the English UI and for a pack with none, which
 * shows its English name. */
export const packZh = (name: string, zh: boolean): string | undefined => (zh ? PACK_ZH[name] : undefined);

/** The pack filter's difficulties, "" any: the modes of the data file's floors. */
export type PackMode = "" | "normal" | "hard" | "infinity" | "extreme";
export const MODE_KEYS = { normal: "N", hard: "H", infinity: "I", extreme: "X" } as const;
/** The floors' modes in badge order: NORMAL, HARD, INFINITY, EXTREME. */
const FLOOR_MODES = ["N", "H", "I", "X"] as const;
/** The floors a 15-floor run plays as INFINITY and as EXTREME, as the agent reads them (agent/run_start.py MODE_BANDS, #387). */
export const MODE_BANDS = { I: [6, 10], X: [11, 15] } as const;

/** A long lane's groups (#742; grouping by difficulty, the user's choice of 2026-11-22), by the data file's N, H and X keys: NORMAL (every such pack
 * has HARD floors too), HARD without NORMAL, EXTREME only, and the rest (a pack the data file lacks). */
export type PackGroup = "both" | "hard" | "extreme" | "other";
const PACK_GROUPS: PackGroup[] = ["both", "hard", "extreme", "other"];
/** The fewest packs a lane groups: every lane that long, not only 0 (the default plan's -5 lane holds 51); a shorter one is
 * a few rows, read at a glance. */
export const GROUP_MIN = 20;
const groupOf = (f: PackFloors | undefined): PackGroup => (!f ? "other" : f.N?.length ? "both" : f.H?.length ? "hard" : f.X ? "extreme" : "other");

/** The groups of a lane's packs shown at the difficulty the filter picks, each in the lane's order, the empty ones left out;
 * null when the lane stays one run of packs: under GROUP_MIN packs, all of them in one group (a filter above left only that
 * one), where a title would say nothing, or EXTREME picked, where every pack shown is on EXTREME and 只在困難 would say not. */
export function packGroups(names: string[], packs: Record<string, PackFloors>, difficulty: PackMode = ""):
  { group: PackGroup; names: string[] }[] | null {
  if (names.length < GROUP_MIN || difficulty === "extreme") return null;
  const groups = PACK_GROUPS.map((group) => ({ group, names: names.filter((n) => groupOf(packs[n]) === group) }))
    .filter((g) => g.names.length);
  return groups.length < 2 ? null : groups;
}

/** Whether a pack with these floors ({N: [1, 2], H: [1]}: NORMAL 1-2, HARD 1; I, X: every floor of MODE_BANDS) shows on
 * difficulty ("" any) and floor (0 any). */
export function onFloor(floors: PackFloors, difficulty: PackMode, floor: number) {
  const keys = difficulty ? [MODE_KEYS[difficulty]] : FLOOR_MODES;
  return keys.some((k) => {
    if (k === "I" || k === "X") return floors[k] === true && (floor === 0 || (floor >= MODE_BANDS[k][0] && floor <= MODE_BANDS[k][1]));
    const list = floors[k];
    return list !== undefined && (floor === 0 || list.includes(floor));
  });
}

/** A pack's floors as badges, NORMAL, HARD, INFINITY, EXTREME: each mode it has with its runs of floors as ranges ("1–2"),
 * the rest joined by sep ("1–2、4"); INFINITY and EXTREME their MODE_BANDS. A mode it lacks has no badge. */
export function floorBadges(floors: PackFloors, sep: string): { mode: keyof PackFloors; text: string }[] {
  const runs = (list: number[]) => {
    const groups: number[][] = [];
    for (const n of [...list].sort((a, b) => a - b)) {
      const last = groups[groups.length - 1];
      if (last && n === last[last.length - 1] + 1) last.push(n);
      else groups.push([n]);
    }
    return groups.map((g) => (g.length > 1 ? `${g[0]}–${g[g.length - 1]}` : `${g[0]}`)).join(sep);
  };
  return FLOOR_MODES.flatMap((mode): { mode: keyof PackFloors; text: string }[] => {
    if (mode === "I" || mode === "X") return floors[mode] ? [{ mode, text: MODE_BANDS[mode].join("–") }] : [];
    const list = floors[mode];
    return list?.length ? [{ mode, text: runs(list) }] : [];
  });
}

/** The whole numbers a pack's weight may take (the schema's pack_weight). */
export const WEIGHT_MIN: number = schema.$defs.pack_weight.minimum;
export const WEIGHT_MAX: number = schema.$defs.pack_weight.maximum;

/** A pack's weight: its own, else the plan's unlisted weight (the agent's rule, spec 03 section 6). */
export const weightOf = (plan: PackPlanValues, name: string) => plan.weights[name] ?? plan.unlisted;

/** The weights that get a lane: every one in use and 0, highest first. */
export const lanesOf = (plan: PackPlanValues) =>
  [...new Set([0, plan.unlisted, ...Object.values(plan.weights)])].sort((a, b) => b - a);

/** How many lanes sit above the threshold line: those whose packs meet it. */
export const lineAt = (lanes: number[], threshold: number) => lanes.filter((w) => w >= threshold).length;

/** Spec 04 section 13: the Gift Search page's tabs, which is the order a new gift list buys them in. */
export const GIFT_KEYWORDS: string[] = schema.$defs.gift_list.properties.order.items.enum;
export const FUSION_CONDITIONS: string[] = schema.$defs.gift_list.properties.fusion_condition.enum;
/** A gift list (spec 04 section 13): the gifts neither in want nor in keep are drop. */
export interface GiftList {
  id: string; name: string; order: string[]; want: number[]; keep: number[]; gorder: Record<string, number[]>; fusion_condition: string;
}

/** Every keyword's gifts a shop may sell (SHOP_GIFTS), the highest tier first, within a tier in SHOP_GIFTS' order
 * (agent/settings.py default_gorder). */
export const defaultGorder = (): Record<string, number[]> => Object.fromEntries(GIFT_KEYWORDS.map((k) => [
  k, [...SHOP_GIFTS].sort((a, b) => b.tier - a.tier).filter((g) => g.keyword === k).map((g) => g.id), // a stable sort
]));

const KNOWN_GIFTS = new Set(Object.values(GIFT_SOURCES).flat().map((g) => g.id));

/** A gift list as the GUI uses it, and how many ids it dropped (agent/settings.py clean_gift_list): ids no data file has
 * leave want and keep; a gorder keyword lacking gifts gets them last, ids the keyword does not have are dropped. */
export function cleanGiftList(list: GiftList): { list: GiftList; dropped: number } {
  const known = (ids: number[]) => ids.filter((i) => KNOWN_GIFTS.has(i));
  const gorder = Object.fromEntries(Object.entries(defaultGorder()).map(([k, all]) => {
    const given = [...new Set(Array.isArray(list.gorder[k]) ? list.gorder[k] : [])].filter((i) => all.includes(i));
    return [k, [...given, ...all.filter((i) => !given.includes(i))]];
  }));
  const want = known(list.want), keep = known(list.keep);
  return { list: { ...list, want, keep, gorder }, dropped: list.want.length - want.length + list.keep.length - keep.length };
}

/** Whether a loaded gift list passes the schema, so cleaning it hides no schema error (the agent cleans after the schema check too). */
const wellFormed = (l: unknown): l is GiftList => giftListCheck(l);

/** Spec 04 section 13: a gift list as text for a friend, without the id. */
export const exportGiftList = (list: GiftList) => {
  const { id, ...rest } = list;
  return JSON.stringify(rest, null, 2);
};

/** A pasted gift list as a new list (spec 04 section 13): "(匯入)" after its name, unknown ids dropped, an order that is not all
 * the keywords once the default, a want that is also in keep stays wanted, an unknown fusion condition "any". skipped counts
 * the ids dropped. Throws a message for text that is not a gift list. */
export function importGiftList(text: string, taken: string[], suffix: string): { list: GiftList; skipped: number } {
  const raw: unknown = JSON.parse(text);
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("not a gift list");
  const o = raw as Record<string, unknown>;
  const ids = (v: unknown) => (Array.isArray(v) ? [...new Set(v)] : []);
  const isId = (v: unknown): v is number => Number.isInteger(v) && (v as number) > 0;
  const bad = (v: unknown) => ids(v).filter((i) => !isId(i)).length;
  const want = ids(o.want).filter(isId);
  const gorder = o.gorder && typeof o.gorder === "object" && !Array.isArray(o.gorder) ? o.gorder as Record<string, unknown> : {};
  const order = Array.isArray(o.order) && o.order.length === GIFT_KEYWORDS.length && GIFT_KEYWORDS.every((k) => (o.order as unknown[]).includes(k))
    ? o.order as string[] : [...GIFT_KEYWORDS];
  const { list, dropped } = cleanGiftList({
    id: newId(), name: freeName(`${typeof o.name === "string" ? o.name : ""}${suffix}`, taken), order,
    want, keep: ids(o.keep).filter(isId).filter((i) => !want.includes(i)),
    gorder: Object.fromEntries(Object.entries(gorder).map(([k, v]) => [k, ids(v).filter(isId)])),
    fusion_condition: typeof o.fusion_condition === "string" && FUSION_CONDITIONS.includes(o.fusion_condition) ? o.fusion_condition : "any",
  });
  return { list, skipped: dropped + bad(o.want) + bad(o.keep) };
}

export type Ref<T> = { plan: string } | { custom: T };
export interface Team {
  id: string; name: string; game_team: number; usage: string;
  hard_from_floor: number | null; deployment_order: Ref<Order>; starlight: Ref<StarlightValues>;
  theme_pack_plan: string; reward_cards: string[]; shop_refresh_keyword: number; shop_refresh_normal: number; heal: string;
  reserve_cost: number; min_alive: number; guard_turns: number;
  gift_search: { enabled: boolean; gifts: GiftRef[] }; allow_white_gossypium: boolean;
  gift_list: string; sell_max_tier: number; sell_vestiges: boolean; skill_replacement: SkillReplacement;
}
/** A gift on the E.G.O Gift Search page: its keyword tab, tier and English name (spec 04 section 9). */
export interface GiftRef { keyword: string; tier: number; name: string }
export interface Settings {
  version: number;
  language: "zh_tw" | "en_us";
  deployment_order_plans: DeploymentPlan[];
  starlight_plans: StarlightPlan[];
  theme_pack_plans: ThemePackPlan[];
  gift_lists: GiftList[];
  /** The team list, in the order the user arranged it; the queue is team_queue (#803). */
  teams: Team[];
  /** The team queue (ADR 0014, ADR 0016): the ids of the teams the user put in it, in the order they play, a team once for each
   * place it has; the Agent moves a team's first place to its end after a claim. */
  team_queue: string[];
  event_overrides: { question: string; option: string }[];
  trial_risk_overrides: { trial: string; risk: number }[];
  /** The Mirror Dungeon task's options and the four every task reads (#813); no editor shows them yet, a save keeps them. */
  run: RunOptions;
  luxcavation: { exp: LuxOptions; thread: LuxOptions };
  charge_enkephalin: { count: number };
  /** The task list the runner posts (#811): the order is the run order, an entry ticked off is skipped. A task may be listed
   * more than once, each entry with its own tick, all of them reading that task's options. */
  tasks: { id: string; enabled: boolean }[];
  emulator: { address: string | null; mumu_index: number | null; mumu_manager: string | null };
  schedules: { id: string; days: string[]; time: string; wake: boolean }[];
  /** The kind of device the runner drives (#939): the emulator (the emulator section), or the PC client's window, which the
   * runner refuses as not supported yet; pc_size the window's client area for a run, by its height. No editor shows it yet,
   * a save keeps it. */
  device: DeviceSetting;
}
export interface DeviceSetting { kind: "emulator" | "pc"; pc_size: "keep" | "720" | "900" | "1080" | "1440" }
export interface RunOptions {
  difficulty: string; target_floor: number; runs: number | null; weekly_bonus_use: string; weekly_bonus_amount: string;
  stop_when_weekly_bonus_out: boolean; starlight_unaffordable: string; wipe_retries: number; after_retries: string;
  webhook_url: string; theme_pack_refresh: string; auto_accept_terms: boolean; auto_download: boolean;
  keep_dismissed_screens: boolean;
}
export interface LuxOptions { mode: string; count: number; team: string | null; retries: number; consecutive: boolean }

const defaultsOf = (props: Record<string, object>) =>
  Object.fromEntries(Object.entries(props).map(([k, v]) => [k, structuredClone((v as { default?: unknown }).default)]));

export const newId = () => crypto.randomUUID();

/** The sections version 23 added (#813) as a new file has them, from the schema's defaults (agent/settings.py defaults):
 * run, luxcavation (Thread's count 3, the day's bonuses), charge_enkephalin, emulator; tasks every task once, all ticked, in
 * the user's order (#874); schedules none. */
export function newSections(): Pick<Settings, "run" | "luxcavation" | "charge_enkephalin" | "tasks" | "emulator" | "schedules"> {
  const lux = () => defaultsOf(schema.$defs.luxcavation.properties) as unknown as LuxOptions;
  return {
    run: defaultsOf(P.run.properties) as unknown as RunOptions,
    luxcavation: { exp: lux(), thread: { ...lux(), count: 3 } },
    charge_enkephalin: defaultsOf(P.charge_enkephalin.properties) as { count: number },
    tasks: structuredClone(P.tasks.default) as Settings["tasks"],
    emulator: defaultsOf(P.emulator.properties) as Settings["emulator"],
    schedules: [],
  };
}

/** The device section version 25 added (#939) at the schema's defaults (agent/settings.py device_defaults): the emulator. */
export const newDevice = () => defaultsOf(P.device.properties) as unknown as DeviceSetting;

/** A new settings file: empty lists (spec 04 section 4), the task options at their defaults, every task ticked, the emulator. */
export function newSettings(): Settings {
  return {
    version: VERSION, language: "zh_tw",
    deployment_order_plans: [], starlight_plans: [], theme_pack_plans: [], gift_lists: [], teams: [], team_queue: [],
    event_overrides: [], trial_risk_overrides: [], ...newSections(), device: newDevice(),
  };
}

export const defaultStarlight = (): StarlightValues => ({
  levels: structuredClone(schema.$defs.levels.default), priority: structuredClone(schema.$defs.priority.default), convert_leftover: false,
});

/** Spec 04 section 9: a new team at 1-based position n. */
export function newTeam(n: number, name: string): Team {
  const d = defaultsOf(TEAM);
  return {
    ...d, id: newId(), name, game_team: Math.min(n, 40),
    deployment_order: { custom: structuredClone(SINNERS) }, starlight: { custom: defaultStarlight() },
  } as Team;
}

/** "Name", "Name 2", ... whichever is not taken yet. */
export function freeName(base: string, taken: string[]) {
  for (let i = 1; ; i++) {
    const name = i === 1 ? base : `${base} ${i}`;
    if (!taken.includes(name)) return name;
  }
}

/** v0.1.0's, the first release: the versions before it were the developers' own files, and their migrations went (#653). */
export const OLDEST_VERSION = 20;
/** MIGRATIONS[n] turns a version-n file into a version-(n + 1) file, one for each n from OLDEST_VERSION up; keep in step with
 * agent/settings.py. 20 -> 21 changes nothing now: version 21 dropped run, luxcavation and charge_enkephalin while the
 * client held their values (#782), and 22 -> 23 brings them back, so a version 20 file keeps its own (#813). 24 -> 25
 * (#939): the device section at its defaults, the emulator; a hand-made one gets each key it lacks (agent/settings.py
 * _device_in). */
export const MIGRATIONS: Record<number, (d: Record<string, unknown>) => Record<string, unknown>> = {
  20: (d) => ({ ...d }),
  21: (d) => ({ ...d, team_queue: queueInListOrder(d.teams) }),
  22: (d) => sectionsBack(d),
  23: (d) => queueAsPutIn(d),
  24: (d) => ({ ...d, device: "device" in d ? withMissing(newDevice(), d.device) : newDevice() }),
};
/** The first version whose file holds its run values (#813): an older one's come back from outside the file once (readBack.ts). */
export const SECTIONS_VERSION = 23;

const isObject = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);

/** have with every key of fallback it lacks, an object inside an object filled the same way; anything else is have's own,
 * so the schema check names what a hand edit broke (agent/settings.py _with_missing). */
function withMissing(fallback: unknown, have: unknown): unknown {
  if (!isObject(fallback) || !isObject(have)) return have;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(fallback)) out[k] = k in have ? withMissing(v, have[k]) : v;
  for (const [k, v] of Object.entries(have)) if (!(k in fallback)) out[k] = v;
  return out;
}

/** 22 -> 23 (#813): each section newSections has that the file lacks comes in at its defaults, and each key a section
 * lacks (agent/settings.py _sections_back). A version 20 file still has its own run, luxcavation and charge_enkephalin. */
function sectionsBack(d: Record<string, unknown>): Record<string, unknown> {
  const out = { ...d };
  for (const [k, v] of Object.entries(newSections())) out[k] = k in d ? withMissing(v, d[k]) : v;
  return out;
}

/** 21 -> 22 (#803): team_queue, the order of teams so far (agent/settings.py _queue_in_list_order). A teams list broken by
 * hand gives what ids it has: the schema check names what is wrong. */
function queueInListOrder(teams: unknown): unknown[] {
  if (!Array.isArray(teams)) return [];
  return teams.filter((t) => t !== null && typeof t === "object" && !Array.isArray(t) && "id" in t).map((t) => t.id);
}

/** 23 -> 24 (#954): the queue is the teams the user put in it, so the disabled teams leave it, the rest in their order, and no
 * team has the switch; run.start_team goes and moves nothing (agent/settings.py _queue_as_put_in). What a hand edit broke
 * stays, for the schema check to name it. */
function queueAsPutIn(d: Record<string, unknown>): Record<string, unknown> {
  const out = { ...d };
  const without = (x: unknown, key: string) => (isObject(x) ? Object.fromEntries(Object.entries(x).filter(([k]) => k !== key)) : x);
  if (Array.isArray(d.teams)) {
    const off = d.teams.filter((t) => isObject(t) && t.enabled === false).map((t) => t.id);
    out.teams = d.teams.map((t) => without(t, "enabled"));
    if (Array.isArray(d.team_queue)) out.team_queue = d.team_queue.filter((id) => !off.includes(id));
  }
  if ("run" in d) out.run = without(d.run, "start_team");
  return out;
}

/** Each task id once, in the order a new file lists them (a task listed twice at its first entry's place): the order a
 * read-back of v1.0.0's task list puts the tasks it did not list in (readBack.ts). A load keeps a task list as the file has
 * it: a task left out stays out (#874). */
export const TASK_ORDER: string[] = [...new Set((P.tasks.default as { id: string }[]).map((x) => x.id))];

/** Parse a settings file; an older version is migrated and the caller writes it back, one without a migration refused
 * (spec 04 section 2). old: the file's version and the file as it read, before its migration (null when it needed none),
 * for what the caller does with an older file before it writes it back (App.tsx). */
export function parseSettings(text: string): {
  data: Settings; unknown: number; old: { version: number; data: Record<string, unknown> } | null;
} {
  let data = JSON.parse(text);
  const asRead = data;
  let version = data?.version;
  if (!Number.isInteger(version)) throw new Error(`version must be an integer, got ${JSON.stringify(version)}`);
  if (version > VERSION) throw new Error(`settings version ${version} is newer than this GUI supports (${VERSION}); update maalc`);
  const migrated = version < VERSION;
  for (; version < VERSION; version++) {
    if (!MIGRATIONS[version]) { // the agent says the same (agent/settings.py migrate)
      throw new Error(`settings version ${version} is too old: maalc reads version ${OLDEST_VERSION} and later; start a new settings file in the settings GUI`);
    }
    data = { ...MIGRATIONS[version](data), version: version + 1 };
  }
  const lists = Array.isArray(data.gift_lists) ? data.gift_lists : [];
  let unknown = 0; // ids in a list that no data file has (a new season): dropped, the caller warns
  data = {
    ...data,
    gift_lists: lists.map((l: unknown) => {
      if (!wellFormed(l)) return l; // the schema check names what is wrong
      const cleaned = cleanGiftList(l);
      unknown += cleaned.dropped;
      return cleaned.list;
    }),
  };
  return { data, unknown, old: migrated ? { version: asRead.version, data: asRead } : null };
}

/** The queue with, for each of `ids` in turn, the first place of that id moved to the end (agent/team_queue.py requeue); an id
 * the queue lacks moves nothing. */
export const moveToEnd = (queue: string[], ids: string[]) => ids.reduce((q, id) => {
  const i = q.indexOf(id);
  return i < 0 ? q : [...q.slice(0, i), ...q.slice(i + 1), id];
}, queue);

/** The ids whose first place `after` moved to the end of `before`, in order: the fewest such moves (moveToEnd) that give
 * `after`. The Agent makes one at each claim (#501); a team's places are alike, so which one moved is always its first. Null
 * when `after` is not the same places in another order (a place added or taken out). */
export function movedToEnd(before: string[], after: string[]): string[] | null {
  for (let k = 0; k <= after.length; k++) {
    const tail = after.slice(after.length - k), moved = moveToEnd(before, tail);
    if (moved.length === after.length && moved.every((id, i) => id === after[i])) return tail;
  }
  return null;
}

/** The editor's settings once another writer changed the file from `base` to `disk` under it (#501): with no unsaved
 * edit, the file; otherwise the edits stay, and the places the file moved to the end of the queue go there in them too. The
 * Agent writes team_queue only (#803): the team list keeps the draft's order. */
export function rebase(base: Settings, draft: Settings, disk: Settings): Settings {
  if (JSON.stringify(draft) === JSON.stringify(base)) return disk;
  // a file without a queue (left half edited by hand) moves nothing: the schema check names it
  const moved = movedToEnd(base.team_queue ?? [], disk.team_queue ?? []) ?? [];
  const queue = draft.team_queue;
  if (!moved.length || !Array.isArray(queue)) return draft;
  return { ...draft, team_queue: moveToEnd(queue, moved) };
}

/** The difficulties a team's usage lets it play (agent/team_queue.py USAGE_FITS; tests/settings_cases.json next_run holds
 * both to the same picks). */
const USAGE_FITS: Record<string, string[]> = { any: ["hard", "normal"], hard_only: ["hard"], normal_only: ["normal"] };

export type Difficulty = "normal" | "hard";

/** The Mirror Dungeon task's next new run, for each difficulty it plays (run.difficulty: auto plays either), Normal first:
 * the team that plays it, the first team in team_queue whose usage fits that difficulty (agent/team_queue.py pick_team).
 * `team` null: no team plays it. */
export type NextRun = { difficulty: Difficulty; team: string | null };
export function nextRuns(s: Settings): NextRun[] {
  const d = s.run.difficulty;
  const played: Difficulty[] = d === "normal" || d === "hard" ? [d] : ["normal", "hard"];
  return played.map((difficulty) => ({
    difficulty,
    team: s.team_queue.find((id) => {
      const team = s.teams.find((t) => t.id === id);
      return !!team && !!USAGE_FITS[team.usage]?.includes(difficulty);
    }) ?? null,
  }));
}

/** The queue with the places of team `id` back in it, once the delete that took them out is undone: `was` the queue before the
 * delete, `now` as it is. What the Agent moved since (movedToEnd) is moved in `was` too; places added or taken out since leave
 * `now` as it is, each of the team's back at its old index. */
export function queueWithTeam(was: string[], now: string[], id: string): string[] {
  const moved = movedToEnd(was.filter((x) => x !== id), now);
  if (moved) return moveToEnd(was, moved);
  const queue = [...now];
  was.forEach((x, j) => { if (x === id) queue.splice(Math.min(j, queue.length), 0, id); });
  return queue;
}

/** Where place `at` of `was`, taken out of it, goes back in `now`, what the queue became since by the Agent's moves alone: the
 * place it has once those are made in `was` (movedToEnd); `at` when `now` is no such thing. */
export function placeBack(was: string[], at: number, now: string[]): number {
  const without = (queue: string[], j: number) => queue.filter((_, k) => k !== j);
  const moved = movedToEnd(without(was, at), now);
  if (!moved) return at;
  const full = moveToEnd(was, moved);
  const back = full.findIndex((id, j) => id === was[at] && without(full, j).every((x, k) => x === now[k]));
  return back < 0 ? at : back;
}
