// The Daily tab's Luxcavation modes (#431): daily fights what the day still needs, count fights the number set.
import { fireEvent, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { TABS } from "./App";
import { TEXT } from "./i18n";
import { newSettings } from "./model";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const DailyTab = TABS.find((tab) => tab[0] === "daily")![2];

test("each Luxcavation task opens in daily mode, its count disabled and marked unused", () => {
  renderEditor(<DailyTab />, newSettings());
  const modes = screen.getAllByRole("combobox", { name: zh["lux.mode"] });
  expect(modes.map((m) => (m as HTMLSelectElement).value)).toEqual(["daily", "daily"]);
  expect(screen.getAllByRole("option", { name: zh["lux_mode.daily"] })).toHaveLength(2);
  const counts = screen.getAllByRole("spinbutton", { name: new RegExp(zh["lux.count"]) });
  expect(counts).toHaveLength(2);
  for (const c of counts) expect(c).toBeDisabled();
  expect(screen.getAllByText(zh["lux.count_unused"])).toHaveLength(2);
});

test("count mode enables that task's count alone, and the number typed is saved", async () => {
  const { user, settings } = renderEditor(<DailyTab />, newSettings());
  const [, thread] = screen.getAllByRole("combobox", { name: zh["lux.mode"] });
  await user.selectOptions(thread, "count");
  expect(settings().luxcavation.thread.mode).toBe("count");
  expect(settings().luxcavation.exp.mode).toBe("daily");
  const [exp, threadCount] = screen.getAllByRole("spinbutton", { name: new RegExp(zh["lux.count"]) });
  expect(exp).toBeDisabled();
  expect(threadCount).toBeEnabled();
  fireEvent.change(threadCount, { target: { value: "5" } });
  expect(settings().luxcavation.thread.count).toBe(5);
  expect(screen.getAllByText(zh["lux.count_unused"])).toHaveLength(1);
});
