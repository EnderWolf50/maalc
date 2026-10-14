// Settings types and the values that come from agent/settings.schema.json (docs/spec/04-settings.md).
import { parse as parseYaml } from "yaml";
import schema from "../../agent/settings.schema.json";

export { schema };

const P = schema.properties;
const TEAM = P.teams.items.properties;

export const SINNERS: string[] = schema.$defs.order.default;
export const REWARD_CARDS: string[] = TEAM.reward_cards.default;
export const KEYWORDS: string[] = TEAM.keyword.enum;
export const LEVELS: string[] = schema.$defs.levels.items.enum;
export const MARKS: string[] = P.theme_pack_plans.items.properties.marks.additionalProperties.enum;
export const VERSION: number = P.version.const;
/** Spec 04 section 7: the boosts by their in-game English names, numbered 1–10. */
export const BOOSTS = [
  "Star of the Beginning", "Cumulating Starcloud", "Interstellar Travel", "Star-shower", "Binary Star-shop",
  "Moon Star-shop", "Favor of the Nebulae", "Starlight Guidance", "Chance Comet", "Perfected Possibility",
];

/** Enum values of a run or team field, in schema order. */
export const runEnum = (k: keyof typeof P.run.properties) => (P.run.properties[k] as { enum: string[] }).enum;
export const teamEnum = (k: keyof typeof TEAM) => (TEAM[k] as { enum: string[] }).enum;

export type Order = string[];
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
  reserve_cost: number; min_alive: number; trial_risk_weight: string;
}
export interface Settings {
  version: number;
  language: "zh_tw" | "en_us";
  run: {
    difficulty: string; runs: number; weekly_bonus_use: string; weekly_bonus_amount: string;
    stop_when_weekly_bonus_out: boolean; starlight_unaffordable: string; wipe_retries: number;
    after_retries: string; webhook_url: string;
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
const MIGRATIONS: Record<number, (d: Record<string, unknown>) => Record<string, unknown>> = {};

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
