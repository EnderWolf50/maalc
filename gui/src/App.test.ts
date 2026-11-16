import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";

test("a problem in any settings section marks the tab that edits it", () => {
  // the header edits the language; how each task runs is the client's since version 21 (#782)
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  expect(marked).toEqual(schema.required.filter((k) => !["version", "language"].includes(k)).sort());
});
