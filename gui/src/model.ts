// Settings types and the values that come from agent/settings.schema.json (docs/spec/04-settings.md).
import Ajv2020 from "ajv/dist/2020";
import { parse as parseYaml } from "yaml";
import schema from "../../agent/settings.schema.json";
import gifts from "../../assets/resource/base/data/gift_search.json";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import graces from "./graces.json";

export { schema };

const P = schema.properties;
const TEAM = P.teams.items.properties;

export const SINNERS: string[] = schema.$defs.order.default;
export const REWARD_CARDS: string[] = TEAM.reward_cards.default;
export const LEVELS: string[] = schema.$defs.levels.items.enum;
export const VERSION: number = P.version.const;
/** Spec 04 section 7: the graces numbered 1-10, English names as the game shows them, Chinese name and
 * effect text from LLC (graces.json carries its source and license). */
export const GRACES: Grace[] = graces.graces;
export const BOOSTS = GRACES.map((g) => g.en);
export interface Grace { en: string; zh: string; effects: { base: string[]; plus?: string[]; plus2?: string[] } }

/** Enum values of a run or team field, in schema order. */
export const runEnum = (k: keyof typeof P.run.properties) => (P.run.properties[k] as { enum: string[] }).enum;
export const teamEnum = (k: keyof typeof TEAM) => (TEAM[k] as { enum: string[] }).enum;

export type Order = string[];

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

/** Select All Graces: the unselected ones at base, or none when all are selected. */
export const selectAll = (v: StarlightValues) =>
  v.levels.includes("none") ? allTo(v, (l) => (l === "none" ? "base" : l)) : allTo(v, () => "none");

/** Enhance All + (1) or ++ (2): every grace at that level, or back to base when all already are. */
export function enhanceAll(v: StarlightValues, plus: 1 | 2) {
  const level = LEVELS[plus + 1];
  return allTo(v, () => (v.levels.every((l) => l === level) ? "base" : level));
}

/** The E.G.O Gift Search page's tabs, left to right (agent/settings.schema.json gift_search keywords). */
export const SEARCH_TABS: string[] = schema.$defs.gift.properties.keyword.enum;
/** Vestiges, tier I-V in this order (#161): the old keep_gifts named them; ids 9991-9995, from data/gift_recipes.json. */
export const VESTIGES = recipes.vestiges;
/** Spec 04 section 9: the gifts the search page offers, in page order; ids, tiers and English names from the game's
 * static data, Chinese names from LLC (data/gift_search.json carries its sources and license). */
export const SEARCH_GIFTS: SearchGift[] = gifts.gifts;
export interface SearchGift { id: number; keyword: string; tier: number; en: string; zh: string }
/** The fusion gifts, the recipe materials the search page lacks and the game's other gifts (extra_gifts: a keyword fusion or
 * an event gives one, #332), data/gift_recipes.json, spec 05: with the search page's, every gift a list names by its keyword. */
const RECIPE_GIFTS: { id: number; keyword: string }[] = [...recipes.gifts, ...recipes.materials, ...recipes.extra_gifts];

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

/** Whether a pack with these floors ({N: [1, 2], H: [1]}: NORMAL 1-2, HARD 1) shows on difficulty ("" any) and floor (0 any).
 * INFINITY and EXTREME are no difficulty of the filter. */
export function onFloor(floors: PackFloors, difficulty: "" | "normal" | "hard", floor: number) {
  const sets = difficulty ? [floors[difficulty === "hard" ? "H" : "N"]] : [floors.N, floors.H];
  return sets.some((f) => f !== undefined && (floor === 0 || f.includes(floor)));
}

/** A pack's floors as badges, NORMAL first: each difficulty it has with its runs of floors as ranges ("1–2"),
 * the rest joined by sep ("1–2、4"). A difficulty it lacks has no badge. */
export function floorBadges(floors: PackFloors, sep: string) {
  const runs = (list: number[]) => {
    const groups: number[][] = [];
    for (const n of [...list].sort((a, b) => a - b)) {
      const last = groups[groups.length - 1];
      if (last && n === last[last.length - 1] + 1) last.push(n);
      else groups.push([n]);
    }
    return groups.map((g) => (g.length > 1 ? `${g[0]}–${g[g.length - 1]}` : `${g[0]}`)).join(sep);
  };
  return (["N", "H"] as const).flatMap((d) => {
    const list = floors[d];
    return list?.length ? [{ hard: d === "H", text: runs(list) }] : [];
  });
}

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

/** Every keyword's buyable gifts, tier III first, within a tier in data-file order (agent/settings.py default_gorder). */
export const defaultGorder = (): Record<string, number[]> => Object.fromEntries(GIFT_KEYWORDS.map((k) => [
  k, [3, 2, 1].flatMap((tier) => SEARCH_GIFTS.filter((g) => g.keyword === k && g.tier === tier).map((g) => g.id)),
]));

const KNOWN_GIFTS = new Set([...SEARCH_GIFTS, ...RECIPE_GIFTS].map((g) => g.id).concat(VESTIGES.map((v) => v.id)));

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
const giftListCheck = new Ajv2020({ strict: false }).compile({ $ref: "#/$defs/gift_list", $defs: schema.$defs });
const wellFormed = (l: unknown): l is GiftList => giftListCheck(l);

/** Every Keywordless gift a list names by its keyword (the shop's, the fusions', the other gifts'), by id, and Lunar Vestige: what a new list keeps, as the default list does.
 * Vestiges I-IV are no such gift: they stay fusion material; Lunar Vestige, tier V, never is one. */
export const keywordlessIds = (): number[] =>
  [...SEARCH_GIFTS, ...RECIPE_GIFTS].filter((g) => g.keyword === "Keywordless").map((g) => g.id).concat(VESTIGES[4].id)
    .sort((a, b) => a - b);

/** The gift list a version 10 team's keep settings come to, without id and name; lost: its keep_gifts that match no gift
 * (agent/settings.py _team_gift_list). */
function listFromV10Team(team: Record<string, unknown>): { content: Omit<GiftList, "id" | "name">; lost: number } {
  const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
  const main = typeof team.keyword === "string" ? team.keyword : null;
  const keptKeywords = new Set([main, ...arr(team.keep_keywords).filter((k) => typeof k === "string")]);
  const want = new Set(SEARCH_GIFTS.filter((g) => g.keyword === main).map((g) => g.id));
  const keep = new Set([...SEARCH_GIFTS, ...RECIPE_GIFTS].filter((g) => keptKeywords.has(g.keyword) || g.keyword === "Keywordless").map((g) => g.id));
  let lost = 0;
  for (const raw of arr(team.keep_gifts)) {
    const kept = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
    const found = SEARCH_GIFTS.find((g) => g.keyword === kept.keyword && g.tier === kept.tier && g.en === kept.name)?.id
      ?? VESTIGES.find((v) => v.en === kept.name)?.id;
    if (found) keep.add(found);
    else lost++;
  }
  const byId = (a: number, b: number) => a - b;
  return {
    content: {
      order: main && GIFT_KEYWORDS.includes(main) ? [main, ...GIFT_KEYWORDS.filter((k) => k !== main)] : [...GIFT_KEYWORDS],
      want: [...want].sort(byId), keep: [...keep].filter((i) => !want.has(i)).sort(byId), gorder: defaultGorder(),
      fusion_condition: ("fusion_condition" in team ? team.fusion_condition : "any") as string, // a bad value is for the checks
    },
    lost,
  };
}

/** Teams before version 14 to version 14 (agent/settings.py gift_lists_from_v10): a list per team, teams that keep the same share the
 * first one's list, named after the first team, "Name 2" when the name is taken. Returns each team's list id too. */
function giftListsFromV10(teams: Record<string, unknown>[]) {
  const lists: GiftList[] = [], ids: string[] = [];
  let dropped = 0;
  for (const team of teams) {
    const { content, lost } = listFromV10Team(team);
    dropped += lost;
    let list = lists.find((g) => (Object.keys(content) as (keyof typeof content)[]).every((k) => JSON.stringify(g[k]) === JSON.stringify(content[k])));
    if (!list) {
      const base = typeof team.name === "string" && team.name ? team.name : "Gift list";
      list = { id: `gift-list-${lists.length + 1}`, name: freeName(base, lists.map((g) => g.name)), ...content };
      lists.push(list);
    }
    ids.push(list.id);
  }
  return { lists, ids, dropped };
}

function migrateV10(d: Record<string, unknown>) {
  const teams = Array.isArray(d.teams) ? d.teams : [];
  const objects = teams.filter((t): t is Record<string, unknown> => !!t && typeof t === "object" && !Array.isArray(t));
  const { lists, ids, dropped } = giftListsFromV10(objects);
  const gift_list = new Map(objects.map((t, i) => [t, ids[i]]));
  return {
    data: {
      ...d, gift_lists: lists,
      teams: Array.isArray(d.teams) ? d.teams.map((t) => {
        if (!gift_list.has(t)) return t;
        const { keyword, keep_keywords, keywordless, keep_gifts, fusion_condition, ...rest } = t;
        return { ...rest, gift_list: gift_list.get(t) };
      }) : d.teams,
    },
    dropped,
  };
}

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
  id: string; name: string; enabled: boolean; game_team: number; usage: string;
  hard_from_floor: number | null; deployment_order: Ref<Order>; starlight: Ref<StarlightValues>;
  theme_pack_plan: string; reward_cards: string[]; shop_refresh_limit: number; heal: string;
  reserve_cost: number; min_alive: number; guard_turns: number; trial_risk_weight: string;
  gift_search: { enabled: boolean; gifts: GiftRef[] }; allow_white_gossypium: boolean;
  gift_list: string; sell_max_tier: number; sell_vestiges: boolean;
}
/** A gift on the E.G.O Gift Search page: its keyword tab, tier and English name (spec 04 section 9). */
export interface GiftRef { keyword: string; tier: number; name: string }
export interface Settings {
  version: number;
  language: "zh_tw" | "en_us";
  run: {
    difficulty: string; runs: number | null; weekly_bonus_use: string; weekly_bonus_amount: string;
    stop_when_weekly_bonus_out: boolean; starlight_unaffordable: string; wipe_retries: number;
    after_retries: string; webhook_url: string; theme_pack_refresh: string;
    auto_accept_terms: boolean; auto_download: boolean; keep_dismissed_screens: boolean;
  };
  deployment_order_plans: DeploymentPlan[];
  starlight_plans: StarlightPlan[];
  theme_pack_plans: ThemePackPlan[];
  gift_lists: GiftList[];
  teams: Team[];
  event_overrides: { question: string; option: string }[];
  trial_risk_overrides: { trial: string; risk: number }[];
  luxcavation: { exp: Luxcavation; thread: Luxcavation };
  charge_enkephalin: { count: number };
}
/** One Luxcavation daily task's options (#366): the wins to get, a teams[] id (null: none picked), the defeats fought again. */
export interface Luxcavation { count: number; team: string | null; retries: number; consecutive: boolean }
// count: EXP 1, Thread 3 (its 3 Daily Bonuses a day; the schema's default is EXP's)
const newLuxcavation = (count = 1): Luxcavation =>
  ({ ...defaultsOf(schema.$defs.luxcavation.properties), count }) as unknown as Luxcavation;

const clone = <T,>(v: T): T => structuredClone(v);
const defaultsOf = (props: Record<string, object>) =>
  Object.fromEntries(Object.entries(props).map(([k, v]) => [k, clone((v as { default?: unknown }).default)]));

export const newId = () => crypto.randomUUID();

/** A new settings file: empty lists and the schema defaults for run (spec 04 section 4). */
export function newSettings(): Settings {
  return {
    version: VERSION, language: "zh_tw", run: defaultsOf(P.run.properties) as Settings["run"],
    deployment_order_plans: [], starlight_plans: [], theme_pack_plans: [], gift_lists: [], teams: [],
    event_overrides: [], trial_risk_overrides: [], luxcavation: { exp: newLuxcavation(), thread: newLuxcavation(3) },
    charge_enkephalin: { count: 0 },
  };
}

export const defaultStarlight = (): StarlightValues => ({
  levels: clone(schema.$defs.levels.default), priority: clone(schema.$defs.priority.default), convert_leftover: false,
});

/** Spec 04 section 9: a new team at 1-based position n. */
export function newTeam(n: number, name: string): Team {
  const d = defaultsOf(TEAM);
  return {
    ...d, id: newId(), name, enabled: true, game_team: Math.min(n, 40),
    deployment_order: { custom: clone(SINNERS) }, starlight: { custom: defaultStarlight() },
  } as Team;
}

/** "Name", "Name 2", ... whichever is not taken yet. */
export function freeName(base: string, taken: string[]) {
  for (let i = 1; ; i++) {
    const name = i === 1 ? base : `${base} ${i}`;
    if (!taken.includes(name)) return name;
  }
}

/** MIGRATIONS[n] turns a version-n file into a version-(n + 1) file; keep in step with agent/settings.py. */
const MIGRATIONS: Record<number, (d: Record<string, unknown>) => Record<string, unknown>> = {
  // Version 2 adds teams[].guard_turns (#52); its short orders need nothing.
  1: (d) => withTeamDefault(d, { guard_turns: 0 }),
  // Version 3 adds teams[].gift_search (#54), off.
  2: (d) => withTeamDefault(d, { gift_search: { enabled: false, gifts: [] } }),
  // Version 4 adds run.theme_pack_refresh (#41), "all" as before.
  3: (d) => (d.run && typeof d.run === "object" ? { ...d, run: { theme_pack_refresh: "all", ...d.run } } : d),
  // Version 5 adds teams[].allow_white_gossypium (#90), on as before.
  4: (d) => withTeamDefault(d, { allow_white_gossypium: true }),
  // Version 6 (#137): runs 0 (no limit) becomes null, off; hard_from_floor 0 (the whole run HARD) becomes 1,
  // which says the same.
  5: (d) => {
    const run = d.run && typeof d.run === "object" ? (d.run as Record<string, unknown>) : null;
    const teams = Array.isArray(d.teams) ? d.teams : null;
    return {
      ...d,
      run: run && run.runs === 0 ? { ...run, runs: null } : d.run,
      teams: teams ? teams.map((t) => (t && typeof t === "object" && t.hard_from_floor === 0
        ? { ...t, hard_from_floor: 1 } : t)) : d.teams,
    };
  },
  // Version 7 adds what the shop keeps out of fusions and sales (#77, #161), as before: no other keyword, keywordless
  // kept, no gift; tier V and vestiges never sold.
  6: (d) => withTeamDefault(d, { keep_keywords: [], keywordless: "keep", keep_gifts: [], sell_max_tier: 4, sell_vestiges: false }),
  // Version 8 adds run.auto_accept_terms and run.auto_download (#85, #86), on: the user's decision (2026-10-21).
  7: (d) => (d.run && typeof d.run === "object" ? { ...d, run: { auto_accept_terms: true, auto_download: true, ...d.run } } : d),
  // Version 9 weighs theme packs (#240): prefer / neutral / avoid become 5 / 0 / -5, threshold 0, unlisted 0, event packs
  // by weight: the same picks as before. A bad mark stays as it is for the checks to name.
  8: (d) => ({
    ...d,
    theme_pack_plans: Array.isArray(d.theme_pack_plans) ? d.theme_pack_plans.map((p) => {
      if (!p || typeof p !== "object" || !p.marks || typeof p.marks !== "object") return p;
      const { marks, ...rest } = p as { marks: Record<string, unknown> };
      const weights = Object.fromEntries(Object.entries(marks).map(([k, v]) => [k, MARK_WEIGHTS[v as string] ?? v]));
      return { ...rest, weights, threshold: 0, unlisted: 0, event_packs: "weight" };
    }) : d.theme_pack_plans,
  }),
  // Version 10 adds teams[].fusion_condition (#263), "any": the shop fuses as before.
  9: (d) => withTeamDefault(d, { fusion_condition: "any" }),
  // Version 11 adds run.keep_dismissed_screens (#244), on.
  10: (d) => (d.run && typeof d.run === "object" ? { ...d, run: { keep_dismissed_screens: true, ...d.run } } : d),
  // Version 12 adds the daily tasks (#362): luxcavation.exp and .thread (#366, #368: one win for EXP, three for Thread,
  // no team picked yet, no retries) and charge_enkephalin (#373: no Lunacy charges).
  11: (d) => {
    const lux = d.luxcavation ?? {};
    const out = { charge_enkephalin: { count: 0 }, ...d };
    return lux && typeof lux === "object" ? { ...out, luxcavation: { exp: newLuxcavation(), thread: newLuxcavation(3), ...lux } } : out;
  },
  // Version 13 adds luxcavation.<task>.consecutive (#375), on.
  12: (d) => {
    const lux = d.luxcavation as Record<string, unknown> | undefined;
    if (!lux || typeof lux !== "object") return d;
    const fixed = Object.fromEntries(Object.entries(lux).map(([k, o]) => [k, o && typeof o === "object" ? { consecutive: true, ...o } : o]));
    return { ...d, luxcavation: fixed };
  },
  // Version 14 (#291) moves the shop's keep settings from the teams to gift lists: a list per team, teams that kept the same
  // share one; keyword (the list's order starts with it), keep_keywords, keywordless, keep_gifts and fusion_condition go. A
  // keywordless gift is always kept now.
  13: (d) => {
    const { data, dropped } = migrateV10(d);
    v10Dropped = dropped;
    return data;
  },
};
/** The version 10 keep_gifts the last migration found no gift for (parseSettings returns it). */
let v10Dropped = 0;

const MARK_WEIGHTS: Record<string, number> = { prefer: 5, neutral: 0, avoid: -5 };

function withTeamDefault(d: Record<string, unknown>, field: Record<string, unknown>) {
  return {
    ...d,
    teams: Array.isArray(d.teams)
      ? d.teams.map((t) => (t && typeof t === "object" ? { ...clone(field), ...t } : t)) : d.teams,
  };
}

/** Parse a settings file; an older version is migrated and the caller writes it back (spec 04 section 2). */
export function parseSettings(text: string): { data: Settings; migrated: boolean; dropped: number; unknown: number } {
  let data = JSON.parse(text);
  let version = data?.version;
  if (!Number.isInteger(version)) throw new Error(`version must be an integer, got ${JSON.stringify(version)}`);
  if (version > VERSION) throw new Error(`settings version ${version} is newer than this GUI supports (${VERSION}); update maalc`);
  const migrated = version < VERSION;
  v10Dropped = 0;
  for (; version < VERSION; version++) {
    if (!MIGRATIONS[version]) throw new Error(`settings version ${version} cannot be migrated`);
    data = { ...MIGRATIONS[version](data), version: version + 1 };
  }
  const dropped = v10Dropped;
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
  return { data, migrated, dropped, unknown };
}
