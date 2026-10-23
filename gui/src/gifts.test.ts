// Runs tests/gift_list_cases.json, which tests/test_gifts.py runs against agent/gifts.py too.
import { describe, expect, test } from "vitest";
import cases from "../../tests/gift_list_cases.json";
import { effective, lockers, mainKeyword, queue, recipeFusion, resolveList, state, teamKeyword, type GiftTables } from "./gifts";
import type { GiftList } from "./model";

type Case = { name: string; fn: string; list: string; args: Record<string, any>; expect: unknown };

function run(c: Case) {
  const lists = Object.entries(cases.lists).map(([id, body]) => ({ id, name: id, ...body, fusion_condition: "any" }) as GiftList);
  const list = resolveList(c.list, lists);
  if (!list) return null;
  const tables: GiftTables | undefined = c.args.data === "real" ? undefined : cases.data;
  const packs: number[] | null = c.args.run_packs ?? null;
  const each = (f: (id: number) => unknown) => Object.fromEntries((c.args.ids as number[]).map((id) => [String(id), f(id)]));
  switch (c.fn) {
    case "main_keyword": return mainKeyword(list);
    case "state": return each((id) => state(list, id));
    case "effective": return each((id) => effective(list, id, packs, tables));
    case "lockers": return each((id) => lockers(list, id, packs, tables));
    case "queue": return queue(list, tables);
    case "queue_summary": {
      const q = queue(list, tables);
      return { first: q.slice(0, 3), has_9083: q.includes(9083) };
    }
    case "recipe_fusion": return recipeFusion(list, c.args.owned, tables);
  }
  throw new Error(c.fn);
}

describe("tests/gift_list_cases.json", () => {
  for (const c of cases.cases as Case[]) test(c.name, () => expect(run(c)).toEqual(c.expect));
});

test("a team's main keyword is the first of its list's order, Burn on the default list (#305)", () => {
  const bleed = { id: "g", name: "G", order: ["Keywordless", "Bleed", "Burn"], want: [], keep: [], gorder: {}, fusion_condition: "any" } as unknown as GiftList;
  expect(teamKeyword("g", [bleed])).toBe("Bleed");
  expect(teamKeyword("default", [])).toBe("Burn");
  expect(teamKeyword("gone", [bleed])).toBeUndefined();
});
