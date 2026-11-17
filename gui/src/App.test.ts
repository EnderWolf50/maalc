import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";

test("a problem in any settings section marks the tab that edits it", () => {
  // the header edits the language; the schedules have no tab until the scheduling ticket's (#811)
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  expect(marked).toEqual(schema.required.filter((k) => !["version", "language", "schedules"].includes(k)).sort());
});
