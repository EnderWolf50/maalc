import { expect, test } from "vitest";
import schema from "../../agent/settings.schema.json";
import { TABS } from "./App";

test("a problem in any settings section marks the tab that edits it", () => {
  const marked = TABS.flatMap((tab) => [...tab[3]]).sort();
  expect(marked).toEqual(schema.required.filter((k) => k !== "version" && k !== "language").sort());
});
