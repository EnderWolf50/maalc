// Settings types and the values that come from agent/settings.schema.json (docs/spec/04-settings.md).
import { parse as parseYaml } from "yaml";
import schema from "../../agent/settings.schema.json";
import gifts from "../../assets/resource/base/data/gift_search.json";
import graces from "./graces.json";

export { schema };

const P = schema.properties;
const TEAM = P.teams.items.properties;

export const SINNERS: string[] = schema.$defs.order.default;
export const REWARD_CARDS: string[] = TEAM.reward_cards.default;
export const KEYWORDS: string[] = TEAM.keyword.enum;
export const LEVELS: string[] = schema.$defs.levels.items.enum;
export const MARKS: string[] = P.theme_pack_plans.items.properties.marks.additionalProperties.enum;
export const VERSION: number = P.version.const;
/** Spec 04 section 7: the graces numbered 1-10, English names as the game shows them, Chinese name and
 * effect text from the wiki (graces.json carries its source and license). */
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
export const SEARCH_TABS: string[] = TEAM.gift_search.properties.gifts.items.properties.keyword.enum;
/** Spec 04 section 9: the gifts the search page offers, in page order; ids, tiers and English names from the game's
 * static data, Chinese names from the wiki (data/gift_search.json carries its sources and license). */
export const SEARCH_GIFTS: SearchGift[] = gifts.gifts;
export interface SearchGift { id: number; keyword: string; tier: number; en: string; zh: string }

/** The game searches 3 gifts at most; agent/settings.schema.json caps gift_search.gifts the same. */
export const MAX_GIFTS: number = TEAM.gift_search.properties.gifts.maxItems;
const sameGift = (a: GiftRef, b: GiftRef) => a.keyword === b.keyword && a.tier === b.tier && a.name === b.name;
/** A gift card's click: add the gift at the end of the search list, or take it out. */
export const toggleGift = (list: GiftRef[], gift: GiftRef) =>
  list.some((g) => sameGift(g, gift)) ? list.filter((g) => !sameGift(g, gift))
    : list.length >= MAX_GIFTS ? list : [...list, gift];

/** The sinner grid's click (spec 04 section 6): add at the end, or leave out; the last one stays. */
export function toggleSinner(order: Order, sinner: string): Order {
  if (!order.includes(sinner)) return [...order, sinner];
  return order.length === 1 ? order : order.filter((x) => x !== sinner);
}
export interface StarlightValues { levels: string[]; priority: number[]; convert_leftover: boolean }
export interface DeploymentPlan { id: string; name: string; order: Order }
export interface StarlightPlan extends StarlightValues { id: string; name: string }
export interface ThemePackPlan { id: string; name: string; marks: Record<string, string> }
/** assets/resource/base/data/theme_packs.yaml (spec 05 section 2): the season's packs and the locked default plan. */
export interface ThemePacks { packs: string[]; default_plan: Record<string, string> }

export function parseThemePacks(text: string): ThemePacks {
  const data = (parseYaml(text) ?? {}) as Partial<ThemePacks>;
  return { packs: data.packs ?? [], default_plan: data.default_plan ?? {} };
}
export type Ref<T> = { plan: string } | { custom: T };
export interface Team {
  id: string; name: string; enabled: boolean; game_team: number; keyword: string; usage: string;
  hard_from_floor: number; deployment_order: Ref<Order>; starlight: Ref<StarlightValues>;
  theme_pack_plan: string; reward_cards: string[]; shop_refresh_limit: number; heal: string;
  reserve_cost: number; min_alive: number; guard_turns: number; trial_risk_weight: string;
  gift_search: { enabled: boolean; gifts: GiftRef[] }; allow_white_gossypium: boolean;
}
/** A gift on the E.G.O Gift Search page: its keyword tab, tier and English name (spec 04 section 9). */
export interface GiftRef { keyword: string; tier: number; name: string }
export interface Settings {
  version: number;
  language: "zh_tw" | "en_us";
  run: {
    difficulty: string; runs: number; weekly_bonus_use: string; weekly_bonus_amount: string;
    stop_when_weekly_bonus_out: boolean; starlight_unaffordable: string; wipe_retries: number;
    after_retries: string; webhook_url: string; theme_pack_refresh: string;
  };
  deployment_order_plans: DeploymentPlan[];
  starlight_plans: StarlightPlan[];
  theme_pack_plans: ThemePackPlan[];
  teams: Team[];
  event_overrides: { question: string; option: string }[];
  trial_risk_overrides: { trial: string; risk: number }[];
}

const clone = <T,>(v: T): T => structuredClone(v);
const defaultsOf = (props: Record<string, object>) =>
  Object.fromEntries(Object.entries(props).map(([k, v]) => [k, clone((v as { default?: unknown }).default)]));

export const newId = () => crypto.randomUUID();

/** A new settings file: empty lists and the schema defaults for run (spec 04 section 4). */
export function newSettings(): Settings {
  return {
    version: VERSION, language: "zh_tw", run: defaultsOf(P.run.properties) as Settings["run"],
    deployment_order_plans: [], starlight_plans: [], theme_pack_plans: [], teams: [],
    event_overrides: [], trial_risk_overrides: [],
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
};

function withTeamDefault(d: Record<string, unknown>, field: Record<string, unknown>) {
  return {
    ...d,
    teams: Array.isArray(d.teams)
      ? d.teams.map((t) => (t && typeof t === "object" ? { ...clone(field), ...t } : t)) : d.teams,
  };
}

/** Parse a settings file; an older version is migrated and the caller writes it back (spec 04 section 2). */
export function parseSettings(text: string): { data: Settings; migrated: boolean } {
  let data = JSON.parse(text);
  let version = data?.version;
  if (!Number.isInteger(version)) throw new Error(`version must be an integer, got ${JSON.stringify(version)}`);
  if (version > VERSION) throw new Error(`settings version ${version} is newer than this GUI supports (${VERSION}); update maalc`);
  const migrated = version < VERSION;
  for (; version < VERSION; version++) {
    if (!MIGRATIONS[version]) throw new Error(`settings version ${version} cannot be migrated`);
    data = { ...MIGRATIONS[version](data), version: version + 1 };
  }
  return { data, migrated };
}
