// The two layers of checks of docs/spec/04-settings.md section 2, run before every save.
// crossCheck mirrors cross_check in agent/settings.py message for message;
// tests/settings_cases.json holds the cases both test suites run.
// The schema layer is compiled at build time (settingsValidator.ts): the built GUI's CSP allows no run-time compile (#220).
import { settings as schemaCheck } from "virtual:settings-validator";
import { GIFT_BY_ID } from "./giftCatalog";
import { TEXT, fill, localName, type Key } from "./i18n";
import { skillPlan, type Settings, type SkillFault } from "./model";

/** What the editor says of a problem, in its own language: a TEXT key and what fills it. A value that is a TEXT key ({ key })
 * is said in that language too, a gift ({ gift }) by its name there, team names ({ names }) as that language lists them. */
export interface Say { key: Key; vars?: Record<string, string | number | { key: Key } | { gift: number } | { names: string[] }> }
/** paths mark the fields in the editor; text is what agent/settings.py would say (the parity cases compare it); say is what
 * the editor shows: the names and the way out, not a settings path (#664). */
export interface Problem { paths: string[]; text: string; say: Say }

/** A problem's words in the editor's language. */
export function sayProblem(p: Problem, lang: Settings["language"]) {
  const zh = lang === "zh_tw", text = TEXT[lang];
  const vars = Object.fromEntries(Object.entries(p.say.vars ?? {}).map(([k, v]) => {
    if (typeof v !== "object") return [k, v];
    if ("key" in v) return [k, text[v.key]];
    if ("names" in v) return [k, v.names.map((n) => (zh ? `「${n}」` : `"${n}"`)).join(zh ? "、" : ", ")];
    const g = GIFT_BY_ID.get(v.gift);
    return [k, g ? localName(g, zh) : `#${v.gift}`];
  }));
  return fill(text[p.say.key], vars);
}

/** A team or list name as the messages show it: an empty one still shows. */
const named = (name: string) => name || "—";
/** The tab that holds each kind of plan, which names that kind in a message. */
const KIND: Record<string, Key> = {
  deployment_order_plans: "tab.deployment", starlight_plans: "tab.starlight", theme_pack_plans: "tab.themepacks", gift_lists: "tab.gifts",
  teams: "tab.teams",
};

export function validate(data: unknown): Problem[] {
  if (!schemaCheck(data)) {
    return schemaCheck.errors!.map((e) => {
      const path = e.instancePath.slice(1) || "(root)";
      const extra = e.params as { additionalProperty?: string; missingProperty?: string };
      const field = extra.additionalProperty ?? extra.missingProperty;
      const text = `${path}: ${e.message}`;
      return { paths: [field && path !== "(root)" ? `${path}/${field}` : path], text, say: { key: "problem.schema", vars: { text } } };
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

export function crossCheck(data: Settings): Problem[] {
  const errors: Problem[] = [];

  const dupes = (path: string, values: string[], what: string, field: string, say: (v: string, n: number) => Say) => {
    const counts = new Map<string, number>();
    for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
    for (const [v, n] of counts) {
      if (n < 2) continue;
      const paths = values.flatMap((x, i) => (x === v ? [`${path}/${i}/${field}`] : []));
      errors.push({ paths, text: `${path}: ${what} ${pyRepr(v)} appears ${n} times`, say: say(v, n) });
    }
  };
  const twice = (key: Key, kind?: string) => (name: string, n: number): Say =>
    ({ key, vars: { name, n, ...(kind && { kind: { key: KIND[kind] } }) } });

  const planKeys = ["deployment_order_plans", "starlight_plans", "theme_pack_plans", "gift_lists"] as const;
  const planIds: Record<string, Set<string>> = {};
  for (const key of planKeys) {
    planIds[key] = new Set(data[key].map((p) => p.id));
    dupes(key, data[key].map((p) => p.id), "id", "id", twice("problem.dupeId", key));
    dupes(key, data[key].map((p) => p.name), "name", "name", twice("problem.dupeName", key));
  }
  const teams = data.teams;
  dupes("teams", teams.map((t) => t.id), "id", "id", twice("problem.dupeId", "teams"));

  const enabled = teams.filter((t) => t.enabled);
  const slots = [...new Set(enabled.map((t) => t.game_team))];
  for (const slot of slots) {
    const using = teams.flatMap((t, i) => (t.enabled && t.game_team === slot ? [i] : []));
    if (using.length < 2) continue;
    const names = using.map((i) => pyRepr(teams[i].name)).join(", ");
    errors.push({
      paths: using.map((i) => `teams/${i}/game_team`), text: `teams: enabled teams ${names} all use TEAMS #${slot}`,
      say: { key: "problem.slot", vars: { names: { names: using.map((i) => named(teams[i].name)) }, slot } },
    });
  }

  teams.forEach((t, i) => {
    const plan = (r: object) => ("plan" in r ? (r.plan as string) : null);
    const refs: [string, string | null, string][] = [
      ["deployment_order", plan(t.deployment_order), "deployment_order_plans"],
      ["starlight", plan(t.starlight), "starlight_plans"],
      ["theme_pack_plan", t.theme_pack_plan === "default" ? null : t.theme_pack_plan, "theme_pack_plans"],
      ["gift_list", t.gift_list === "default" ? null : t.gift_list, "gift_lists"],
    ];
    for (const [field, ref, key] of refs) {
      if (ref !== null && !planIds[key].has(ref)) {
        const path = `teams/${i}/${field}`;
        errors.push({
          paths: [path], text: `${path}: team ${pyRepr(t.name)} uses missing plan ${pyRepr(ref)} (not in ${key})`,
          say: { key: "problem.missingPlan", vars: { team: named(t.name), kind: { key: KIND[key] } } },
        });
      }
    }
  });

  teams.forEach((t, i) => {
    const sinners = t.skill_replacement.sinners;
    dupes(`teams/${i}/skill_replacement/sinners`, sinners.map((x) => x.sinner), "sinner", "sinner",
      (sinner, n) => ({ key: "problem.dupeSinner", vars: { team: named(t.name), sinner, n } }));
    sinners.forEach((x, j) => {
      // the deck starts at the game's 3/2/1 and every swap moves a card up, so S1 above 3 or S3 below 1 is never reached
      const path = `teams/${i}/skill_replacement/sinners/${j}/target`, who = `team ${pyRepr(t.name)} sinner ${pyRepr(x.sinner)}`;
      const target = x.target;
      // "range" never gets here: the schema rejects it, and crossCheck runs only on a file the schema passed
      const text: Record<Exclude<SkillFault, "range">, [string, string, Key, number]> = {
        total: [path, `targets ${target.s1 + target.s2 + target.s3} skills, not 6`, "problem.skillTotal", target.s1 + target.s2 + target.s3],
        s1: [`${path}/s1`, `targets ${target.s1} of skill 1, but swaps only lower it from the game's 3`, "problem.skillS1", target.s1],
        s3: [`${path}/s3`, `targets ${target.s3} of skill 3, but swaps only raise it from the game's 1`, "problem.skillS3", target.s3],
      };
      for (const f of skillPlan(target).faults) {
        if (f === "range") continue;
        const [at, says, key, n] = text[f];
        errors.push({ paths: [at], text: `${at}: ${who} ${says}`, say: { key, vars: { team: named(t.name), sinner: x.sinner, n } } });
      }
    });
  });

  const targetFloor = data.run.target_floor;
  if (targetFloor > 5) {
    // floors 6+ open only when every floor of the run was HARD, and the rotation picks from the enabled teams (#385)
    const need = `but target_floor ${targetFloor} needs the whole run HARD`;
    if (data.run.difficulty === "normal") {
      errors.push({
        paths: ["run/difficulty"], text: `run/difficulty: difficulty is 'normal', ${need}`,
        say: { key: "problem.floorDifficulty", vars: { floor: targetFloor } },
      });
    }
    teams.forEach((t, i) => {
      if (!t.enabled) return;
      if (t.usage === "normal_only") {
        const path = `teams/${i}/usage`;
        errors.push({
          paths: [path], text: `${path}: team ${pyRepr(t.name)} is normal_only, ${need}`,
          say: { key: "problem.floorNormalOnly", vars: { floor: targetFloor, team: named(t.name) } },
        });
      }
      if (t.hard_from_floor !== 1) {
        const path = `teams/${i}/hard_from_floor`;
        const what = t.hard_from_floor === null ? "never switches to HARD" : `starts HARD at floor ${t.hard_from_floor}`;
        errors.push({
          paths: [path], text: `${path}: team ${pyRepr(t.name)} ${what}, ${need} (hard_from_floor 1)`,
          say: t.hard_from_floor === null
            ? { key: "problem.floorNeverHard", vars: { floor: targetFloor, team: named(t.name) } }
            : { key: "problem.floorHardFrom", vars: { floor: targetFloor, team: named(t.name), k: t.hard_from_floor } },
        });
      }
    });
  }

  data.gift_lists.forEach((list, i) => {
    for (const id of list.want.filter((g) => list.keep.includes(g))) {
      const path = `gift_lists/${i}`;
      errors.push({
        paths: [path], text: `${path}: list ${pyRepr(list.name)} has gift ${id} in both want and keep`,
        say: { key: "problem.wantKeep", vars: { list: named(list.name), gift: { gift: id } } },
      });
    }
  });

  const teamIds = new Set(teams.map((t) => t.id));
  for (const [task, opts] of Object.entries(data.luxcavation)) {
    if (opts.team !== null && !teamIds.has(opts.team)) {
      const path = `luxcavation/${task}/team`;
      errors.push({
        paths: [path], text: `${path}: team ${pyRepr(opts.team)} is not in teams`,
        say: { key: "problem.luxTeam", vars: { task: { key: `lux.${task}` as Key } } },
      });
    }
  }

  dupes("event_overrides", data.event_overrides.map((o) => o.question), "question", "question", twice("problem.dupeQuestion"));
  dupes("trial_risk_overrides", data.trial_risk_overrides.map((o) => o.trial), "trial", "trial", twice("problem.dupeTrial"));
  return errors;
}
