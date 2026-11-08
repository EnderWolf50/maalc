// The Run tab's target floor (#385): 5, 10 or 15; a target above 5 shows that the whole run must be HARD,
// and, until #434 switches Parallel Superposition on at the entrance, that each run still stops at floor 5.
import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { TABS } from "./App";
import { TEXT } from "./i18n";
import { newSettings } from "./model";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const RunTab = TABS.find((tab) => tab[0] === "run")![2];

test("the target floor offers 5, 10 and 15, opens on 5 and shows no note there", () => {
  renderEditor(<RunTab />, newSettings());
  const select = screen.getByRole("combobox", { name: new RegExp(zh["run.target_floor"]) }) as HTMLSelectElement;
  expect(select.value).toBe("5");
  expect(screen.getAllByRole("option").filter((o) => (o as HTMLOptionElement).parentElement === select).map((o) => o.textContent))
    .toEqual([zh["target_floor.5"], zh["target_floor.10"], zh["target_floor.15"]]);
  expect(screen.queryByText(zh["run.target_floor_note"])).toBeNull();
});

test("picking 10 or 15 saves the number and shows the whole-run-HARD note; picking 5 hides it", async () => {
  const { user, settings } = renderEditor(<RunTab />, newSettings());
  const select = screen.getByRole("combobox", { name: new RegExp(zh["run.target_floor"]) });
  await user.selectOptions(select, "10");
  expect(settings().run.target_floor).toBe(10);
  expect(screen.getByText(zh["run.target_floor_note"])).toBeVisible();
  await user.selectOptions(select, "15");
  expect(settings().run.target_floor).toBe(15);
  expect(screen.getByText(zh["run.target_floor_note"])).toBeVisible();
  await user.selectOptions(select, "5");
  expect(settings().run.target_floor).toBe(5);
  expect(screen.queryByText(zh["run.target_floor_note"])).toBeNull();
});

test("a target of 10 or 15 says each run still stops at floor 5; 5 does not", async () => {
  const { user } = renderEditor(<RunTab />, newSettings());
  const select = screen.getByRole("combobox", { name: new RegExp(zh["run.target_floor"]) });
  expect(screen.queryByText(zh["run.target_floor_entry_note"])).toBeNull();
  await user.selectOptions(select, "10");
  expect(screen.getByText(zh["run.target_floor_entry_note"])).toBeVisible();
  await user.selectOptions(select, "15");
  expect(screen.getByText(zh["run.target_floor_entry_note"])).toBeVisible();
  await user.selectOptions(select, "5");
  expect(screen.queryByText(zh["run.target_floor_entry_note"])).toBeNull();
});
