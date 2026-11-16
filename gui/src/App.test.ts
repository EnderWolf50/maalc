import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";

test("a problem in any settings section marks the tab that edits it", () => {
  // run, charge_enkephalin: no tab edits them since their options went to the client (#779, #781); the file keeps them,
  // unread, until #782 drops them
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  expect(marked).toEqual(schema.required.filter((k) => !["version", "language", "run", "charge_enkephalin"].includes(k)).sort());
});
