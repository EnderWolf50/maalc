// The editor shell (App.tsx) around the tabs: what a tab switch keeps.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { defaultStarlight, newPackPlan, newSettings, newTeam, SINNERS, type Settings } from "./model";

const file = vi.hoisted(() => ({ text: "" }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: () => Promise.resolve(),
  rootDir: () => Promise.resolve("root"),
}));

const zh = TEXT.zh_tw;
const two = (prefix: string) => [1, 2].map((n) => ({ id: `${prefix}${n}`, name: `${prefix.toUpperCase()}${n}` }));
const settings = (): Settings => ({
  ...newSettings(), language: "zh_tw",
  teams: [{ ...newTeam(1, "Ta"), id: "a" }, { ...newTeam(2, "Tb"), id: "b" }],
  deployment_order_plans: two("d").map((p) => ({ ...p, order: [...SINNERS] })),
  starlight_plans: two("s").map((p) => ({ ...p, ...defaultStarlight() })),
  theme_pack_plans: two("p").map((p) => ({ ...p, ...newPackPlan() })),
});

const tab = (name: string) => screen.getByRole("tab", { name });
const nameBox = () => screen.getByRole("textbox", { name: zh.name });
const pickInList = async (user: ReturnType<typeof userEvent.setup>, name: string) =>
  user.click(within(document.querySelector("aside")!).getByText(name));

describe("a tab switch", () => {
  beforeEach(() => { file.text = JSON.stringify(settings()); });

  test("keeps the team the user picked", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    await pickInList(user, "Tb");
    expect(nameBox()).toHaveValue("Tb");
    await user.click(tab(zh["tab.run"]));
    await user.click(tab(zh["tab.teams"]));
    expect(nameBox()).toHaveValue("Tb");
  });

  test.each([
    ["tab.deployment", "D2"],
    ["tab.starlight", "S2"],
    ["tab.themepacks", "P2"],
  ] as const)("keeps the plan the user picked in %s", async (label, plan) => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.run"] });
    await user.click(tab(zh[label]));
    await pickInList(user, plan);
    expect(nameBox()).toHaveValue(plan);
    await user.click(tab(zh["tab.teams"]));
    await user.click(tab(zh[label]));
    expect(nameBox()).toHaveValue(plan);
  });
});
