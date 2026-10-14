// The two layers of checks of docs/spec/04-settings.md section 2, run before every save.
// crossCheck mirrors cross_check in agent/settings.py message for message;
// tests/settings_cases.json holds the cases both test suites run.
import Ajv2020 from "ajv/dist/2020";
import { schema, type Settings } from "./model";

/** paths mark the fields in the editor; text is what agent/settings.py would say. */
export interface Problem { paths: string[]; text: string }

const schemaCheck = new Ajv2020({ allErrors: true, strict: false }).compile(schema);

export function validate(data: unknown): Problem[] {
  if (!schemaCheck(data)) {
    return schemaCheck.errors!.map((e) => {
      const path = e.instancePath.slice(1) || "(root)";
      const extra = e.params as { additionalProperty?: string; missingProperty?: string };
      const field = extra.additionalProperty ?? extra.missingProperty;
      return { paths: [field && path !== "(root)" ? `${path}/${field}` : path], text: `${path}: ${e.message}` };
    });
  }
  return crossCheck(data as unknown as Settings);
}

/** Python repr() of a str, which agent/settings.py puts in its messages. */
export function pyRepr(s: string) {
  const q = s.includes("'") && !s.includes('"') ? '"' : "'";
  const body = s.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t");
  return q + (q === "'" ? body.replace(/'/g, "\\'") : body) + q;
}

const NO_TEAM = "No enabled team: set up a team in the settings GUI first.";

export function crossCheck(data: Settings): Problem[] {
  const errors: Problem[] = [];

  const dupes = (path: string, values: string[], what: string, field: string) => {
    const counts = new Map<string, number>();
    for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
    for (const [v, n] of counts) {
      if (n < 2) continue;
      const paths = values.flatMap((x, i) => (x === v ? [`${path}/${i}/${field}`] : []));
      errors.push({ paths, text: `${path}: ${what} ${pyRepr(v)} appears ${n} times` });
    }
  };

  const planKeys = ["deployment_order_plans", "starlight_plans", "theme_pack_plans"] as const;
  const planIds: Record<string, Set<string>> = {};
  for (const key of planKeys) {
    planIds[key] = new Set(data[key].map((p) => p.id));
    dupes(key, data[key].map((p) => p.id), "id", "id");
    dupes(key, data[key].map((p) => p.name), "name", "name");
  }
  const teams = data.teams;
  dupes("teams", teams.map((t) => t.id), "id", "id");

  const enabled = teams.filter((t) => t.enabled);
  if (!enabled.length) errors.push({ paths: ["teams"], text: NO_TEAM });
  const slots = [...new Set(enabled.map((t) => t.game_team))];
  for (const slot of slots) {
    const using = teams.flatMap((t, i) => (t.enabled && t.game_team === slot ? [i] : []));
    if (using.length < 2) continue;
    const names = using.map((i) => pyRepr(teams[i].name)).join(", ");
    errors.push({ paths: using.map((i) => `teams/${i}/game_team`), text: `teams: enabled teams ${names} all use TEAMS #${slot}` });
  }

  teams.forEach((t, i) => {
    const plan = (r: object) => ("plan" in r ? (r.plan as string) : null);
    const refs: [string, string | null, string][] = [
      ["deployment_order", plan(t.deployment_order), "deployment_order_plans"],
      ["starlight", plan(t.starlight), "starlight_plans"],
      ["theme_pack_plan", t.theme_pack_plan === "default" ? null : t.theme_pack_plan, "theme_pack_plans"],
    ];
    for (const [field, ref, key] of refs) {
      if (ref !== null && !planIds[key].has(ref)) {
        const path = `teams/${i}/${field}`;
        errors.push({ paths: [path], text: `${path}: team ${pyRepr(t.name)} uses missing plan ${pyRepr(ref)} (not in ${key})` });
      }
    }
  });

  dupes("event_overrides", data.event_overrides.map((o) => o.question), "question", "question");
  dupes("trial_risk_overrides", data.trial_risk_overrides.map((o) => o.trial), "trial", "trial");
  return errors;
}
