// The trial score overrides tab (#381): a score in pt, decimals and past the old 0-5 scale, typed as the user types it.
import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { TABS } from "./App";
import { TEXT } from "./i18n";
import { newSettings } from "./model";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const TrialsTab = TABS.find((tab) => tab[0] === "trials")![2];

test("a trial's score takes decimals, typed digit by digit", async () => {
  const { user, settings } = renderEditor(<TrialsTab />, newSettings());
  await user.click(screen.getByRole("button", { name: `+ ${zh.add}` }));
  const [trial, score] = screen.getAllByRole("textbox");
  await user.type(trial, "Brutality");
  await user.clear(score);
  await user.type(score, "0.75");
  expect(score).toHaveValue("0.75");
  expect(settings().trial_risk_overrides).toEqual([{ trial: "Brutality", risk: 0.75 }]);
  await user.clear(score);
  await user.type(score, "12.5"); // past the old 0-5 risk
  expect(settings().trial_risk_overrides[0].risk).toBe(12.5);
});

test("a score that is no number or below 0 leaves the last one, and the field shows it again once left", async () => {
  const { user, settings } = renderEditor(<TrialsTab />, { ...newSettings(), trial_risk_overrides: [{ trial: "Growth II", risk: 1.5 }] });
  const score = screen.getAllByRole("textbox")[1];
  await user.clear(score);
  await user.type(score, "-2");
  expect(settings().trial_risk_overrides[0].risk).toBe(1.5);
  await user.tab();
  expect(score).toHaveValue("1.5");
});

test("the tab says what a score means", () => {
  renderEditor(<TrialsTab />, newSettings());
  expect(screen.getByText(zh["trial.note"])).toBeInTheDocument();
});
