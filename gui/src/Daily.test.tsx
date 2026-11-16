// The Daily tab: each Luxcavation task's team (#366). Their mode, count, retries and Consecutive Battle, and Charge
// Enkephalin's Daily Count, are the client's task options since #781.
import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { TABS } from "./App";
import { TEXT } from "./i18n";
import { newSettings, newTeam } from "./model";
import { expectLines, renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const DailyTab = TABS.find((tab) => tab[0] === "daily")![2];

test("the tab shows each Luxcavation task's team alone: the rest are the client's task options (#781)", () => {
  renderEditor(<DailyTab />, newSettings());
  expect(screen.getAllByRole("combobox")).toEqual(screen.getAllByRole("combobox", { name: new RegExp(zh["lux.team"]) }));
  expect(screen.getAllByRole("combobox")).toHaveLength(2);
  expect(screen.queryAllByRole("spinbutton")).toEqual([]);
  expect(screen.queryAllByRole("checkbox")).toEqual([]);
  expect(screen.queryByText(/Lunacy|Daily Count/)).toBeNull();
});

test("a team picked is saved for that task alone", async () => {
  const s = newSettings();
  s.teams = [newTeam(1, "Ta"), newTeam(3, "Tb")];
  const { user, settings } = renderEditor(<DailyTab />, s);
  const [, thread] = screen.getAllByRole("combobox", { name: new RegExp(zh["lux.team"]) });
  await user.selectOptions(thread, s.teams[1].id);
  expect(settings().luxcavation.thread.team).toBe(s.teams[1].id);
  expect(settings().luxcavation.exp.team).toBeNull();
});

test("the tab's note shows one topic to a line and says where the rest went", () => {
  renderEditor(<DailyTab />, newSettings());
  expectLines(zh["daily.note"]);
  expect(zh["daily.note"]).toContain("MXU");
});
