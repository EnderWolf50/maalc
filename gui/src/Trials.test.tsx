// The trial score overrides tab (#381): a score in pt, decimals and past the old 0-5 scale, typed as the user types it.
import { screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { TABS } from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings } from "./model";
import { expectLines, renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const TrialsTab = TABS.find((tab) => tab[0] === "trials")![2];

test("a trial's score takes decimals, typed digit by digit", async () => {
  const { user, settings } = renderEditor(<TrialsTab />, newSettings());
  await user.click(screen.getByRole("button", { name: `+ ${zh.add}` }));
  const trial = screen.getByRole("combobox"), score = screen.getByRole("textbox");
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
  const score = screen.getByRole("textbox");
  await user.clear(score);
  await user.type(score, "-2");
  expect(settings().trial_risk_overrides[0].risk).toBe(1.5);
  await user.tab();
  expect(score).toHaveValue("1.5");
});

test("the tab says what a score means, each paragraph on a line of its own", () => {
  renderEditor(<TrialsTab />, newSettings());
  expectLines(zh["trial.note"]);
});

test("a trial in the table shows its table score; a name the table lacks says the row is not used", () => {
  renderEditor(<TrialsTab />, { ...newSettings(), trial_risk_overrides: [{ trial: "Growth II", risk: 1.5 }, { trial: "Growht II", risk: 1 }] });
  const [growth, typo] = screen.getAllByRole("row").slice(1);
  expect(within(growth).getByText(fill(zh["trial.inTable"], { score: 0.05 }))).toBeInTheDocument(); // trials.yaml: Growth II 0.05
  expect(within(growth).queryByText(zh["trial.unknown"])).toBeNull();
  expect(within(typo).getByText(zh["trial.unknown"])).toBeInTheDocument();
});

test("the trial field offers the table's names, and each field is named by its column and row", () => {
  renderEditor(<TrialsTab />, { ...newSettings(), trial_risk_overrides: [{ trial: "", risk: 1 }] });
  const trial = screen.getByRole("combobox", { name: `${zh["trial.trial"]} 1` });
  const options = [...document.getElementById(trial.getAttribute("list")!)!.querySelectorAll("option")].map((o) => o.value);
  expect(options).toContain("Growth II");
  expect(options).toContain("Offense Level Up I");
  expect(screen.getByRole("textbox", { name: `${zh["trial.risk"]} 1` })).toBeInTheDocument();
});

test("a name like an object's own method (toString) is no trial: the row says it is not in the table", () => {
  renderEditor(<TrialsTab />, { ...newSettings(), trial_risk_overrides: [{ trial: "toString", risk: 1 }] });
  expect(screen.getByText(zh["trial.unknown"])).toBeInTheDocument();
});
