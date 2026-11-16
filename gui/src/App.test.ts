import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";

test("a problem in any settings section marks the tab that edits it", () => {
  // run: no tab edits it since its options went to the client (#779); the file keeps it, unread, until #782 drops it
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  expect(marked).toEqual(schema.required.filter((k) => !["version", "language", "run"].includes(k)).sort());
});
