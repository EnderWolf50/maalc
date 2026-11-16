import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";

test("a problem in any settings section marks the tab that edits it", () => {
  // run, luxcavation, charge_enkephalin: no tab edits them since their options went to the client (#779, #780, #781); the
  // file keeps them, unread, until #782 drops them
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  const unread = ["version", "language", "run", "luxcavation", "charge_enkephalin"];
  expect(marked).toEqual(schema.required.filter((k) => !unread.includes(k)).sort());
});
