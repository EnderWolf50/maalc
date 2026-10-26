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
/** Vestiges, tier I-V in this order (#161): only fusion or sale material, kept by name in keep_gifts. */
export const VESTIGES: string[] = schema.$defs.vestige.properties.name.enum;
/** Spec 04 section 9: the gifts the search page offers, in page order; ids, tiers and English names from the game's
 * static data, Chinese names from LLC (data/gift_search.json carries its sources and license). */
export const SEARCH_GIFTS: SearchGift[] = gifts.gifts;
export interface SearchGift { id: number; keyword: string; tier: number; en: string; zh: string }

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
/** assets/resource/base/data/theme_packs.yaml (spec 05 section 2): the season's packs with their floors ("N12 H1")
 * and the locked default plan. */
export interface ThemePacks { packs: Record<string, string>; default_plan: PackPlanValues }

export const EVENT_MODES: string[] = P.theme_pack_plans.items.properties.event_packs.enum;
export const newPackPlan = (): PackPlanValues => ({ weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" });

export function parseThemePacks(text: string): ThemePacks {
  const data = (parseYaml(text) ?? {}) as Partial<ThemePacks>;
  return { packs: data.packs ?? {}, default_plan: { ...newPackPlan(), ...data.default_plan } };
}

/** The floor digits of one difficulty in a pack's floors: "N12 H1", "N" -> "12"; undefined when it has none. */
const floorDigits = (floors: string, letter: "N" | "H") => floors.match(new RegExp(letter + "(\\d+)"))?.[1];

/** Whether a pack with these floors ("N12 H1": NORMAL 1-2, HARD 1) shows on difficulty ("" any) and floor (0 any). */
export function onFloor(floors: string, difficulty: "" | "normal" | "hard", floor: number) {
  const on = (letter: "N" | "H") => floorDigits(floors, letter);
  const sets = (difficulty ? [on(difficulty === "hard" ? "H" : "N")] : [on("N"), on("H")]).filter((x) => x !== undefined);
  return sets.some((f) => floor === 0 || f!.includes(String(floor)));
}

/** A pack's floors ("N12 H1") as badges, NORMAL first: each difficulty it has with its runs of floors as ranges ("1–2"),
 * the rest joined by sep ("1–2、4"). A difficulty it lacks has no badge. */
export function floorBadges(floors: string, sep: string) {
  const runs = (digits: string) => {
    const groups: number[][] = [];
    for (const n of [...digits].map(Number).sort((a, b) => a - b)) {
      const last = groups[groups.length - 1];
      if (last && n === last[last.length - 1] + 1) last.push(n);
      else groups.push([n]);
    }
    return groups.map((g) => (g.length > 1 ? `${g[0]}–${g[g.length - 1]}` : `${g[0]}`)).join(sep);
  };
  return (["N", "H"] as const).flatMap((d) => {
    const digits = floorDigits(floors, d);
    return digits ? [{ hard: d === "H", text: runs(digits) }] : [];
  });
}

/** A pack's weight: its own, else the plan's unlisted weight (the agent's rule, spec 03 section 6). */
export const weightOf = (plan: PackPlanValues, name: string) => plan.weights[name] ?? plan.unlisted;

/** The weights that get a lane: every one in use and 0, highest first. */
export const lanesOf = (plan: PackPlanValues) =>
  [...new Set([0, plan.unlisted, ...Object.values(plan.weights)])].sort((a, b) => b - a);

/** How many lanes sit above the threshold line: those whose packs meet it. */
export const lineAt = (lanes: number[], threshold: number) => lanes.filter((w) => w >= threshold).length;
export type Ref<T> = { plan: string } | { custom: T };
export interface Team {
  id: string; name: string; enabled: boolean; game_team: number; keyword: string; usage: string;
  hard_from_floor: number | null; deployment_order: Ref<Order>; starlight: Ref<StarlightValues>;
  theme_pack_plan: string; reward_cards: string[]; shop_refresh_limit: number; heal: string;
  reserve_cost: number; min_alive: number; guard_turns: number; trial_risk_weight: string;
  gift_search: { enabled: boolean; gifts: GiftRef[] }; allow_white_gossypium: boolean;
  keep_keywords: string[]; keywordless: string; keep_gifts: GiftRef[]; sell_max_tier: number; sell_vestiges: boolean;
  fusion_condition: string;
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
  teams: Team[];
  event_overrides: { question: string; option: string }[];
  trial_risk_overrides: { trial: string; risk: number }[];
  luxcavation: { exp: Luxcavation };
}
/** One Luxcavation daily task's options (#366): the wins to get, a teams[] id (null: none picked), the defeats fought again. */
export interface Luxcavation { count: number; team: string | null; retries: number }
const newLuxcavation = (): Luxcavation => defaultsOf(schema.$defs.luxcavation.properties) as unknown as Luxcavation;

const clone = <T,>(v: T): T => structuredClone(v);
const defaultsOf = (props: Record<string, object>) =>
  Object.fromEntries(Object.entries(props).map(([k, v]) => [k, clone((v as { default?: unknown }).default)]));

export const newId = () => crypto.randomUUID();

/** A new settings file: empty lists and the schema defaults for run (spec 04 section 4). */
export function newSettings(): Settings {
  return {
    version: VERSION, language: "zh_tw", run: defaultsOf(P.run.properties) as Settings["run"],
    deployment_order_plans: [], starlight_plans: [], theme_pack_plans: [], teams: [],
    event_overrides: [], trial_risk_overrides: [], luxcavation: { exp: newLuxcavation() },
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
  // Version 12 adds luxcavation.exp (#366): one win, no team picked yet, no retries.
  11: (d) => {
    const lux = d.luxcavation ?? {};
    return lux && typeof lux === "object" ? { ...d, luxcavation: { exp: newLuxcavation(), ...lux } } : d;
  },
};

const MARK_WEIGHTS: Record<string, number> = { prefer: 5, neutral: 0, avoid: -5 };

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
