import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";
import { cases } from "./settingsCases";

test("a problem in any settings section marks the tab that edits it", () => {
  // the header edits the language; the sections version 23 added have no tab until the runner's (#811, #813)
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  expect(marked).toEqual(schema.required.filter((k) => !["version", "language", ...cases.added_v23].includes(k)).sort());
});
