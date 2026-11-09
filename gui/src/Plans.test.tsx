// The theme pack tab's filter (#387): floors 1-15 of the data file, INFINITY and EXTREME among the difficulties.
import { screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { TEXT } from "./i18n";
import { newSettings } from "./model";
import { ThemePackTab } from "./Plans";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const chip = (name: string) => screen.getByRole("button", { name });
const floorChip = (n: number) => chip(zh["packs.floor"].replace("{n}", String(n)));
const shown = (pack: string) => screen.queryByText(pack) !== null;

test("the floor filter reaches floor 15: an EXTREME-only pack shows on floors 11-15, not on 1-5", async () => {
  const { user } = renderEditor(<ThemePackTab />, newSettings());
  await waitFor(() => expect(shown("Chachihu")).toBe(true)); // the bundled data file, every floor: 1519, EXTREME only
  await user.click(floorChip(5));
  expect(shown("Chachihu")).toBe(false);
  expect(shown("The Heartbreaking")).toBe(true); // HARD 5
  await user.click(floorChip(12));
  expect(shown("Chachihu")).toBe(true);
  expect(shown("Line 3")).toBe(true); // HARD 5, INFINITY and EXTREME
  expect(shown("The Heartbreaking")).toBe(false); // HARD 5 and INFINITY: not on an EXTREME floor
  await user.click(floorChip(7));
  expect(shown("The Heartbreaking")).toBe(true);
  expect(shown("Chachihu")).toBe(false);
});

test("INFINITY and EXTREME are choices of the filter and badges of a pack", async () => {
  const { user } = renderEditor(<ThemePackTab />, newSettings());
  await waitFor(() => expect(shown("Chachihu")).toBe(true));
  await user.click(chip("EXTREME"));
  expect(shown("Chachihu")).toBe(true);
  expect(shown("The Forgotten")).toBe(false);
  await user.click(chip("INFINITY"));
  expect(shown("Chachihu")).toBe(false);
  expect(shown("The Heartbreaking")).toBe(true);
  expect(screen.getAllByRole("img", { name: `${zh["packs.floorsInfinity"]} 6–10` }).length).toBeGreaterThan(0);
});
