// The window's frame (frame.tsx, #664): the rail goes through the pages by keyboard and folds to its icons, the team
// list takes the keyboard, and a folded section says what is set inside.
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { SINNERS, newSettings, newTeam, type Settings } from "./model";

const file = vi.hoisted(() => ({ text: "" }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: () => Promise.resolve(),
  rootDir: () => Promise.resolve("root"),
}));

const zh = TEXT.zh_tw;
const settings = (): Settings => ({
  ...newSettings(), language: "zh_tw",
  teams: ["a", "b", "c"].map((id, i) => ({ ...newTeam(i + 1, `T${id}`), id })),
});
const tab = (name: string) => screen.getByRole("tab", { name });
const nameBox = () => screen.getByRole("textbox", { name: zh.name });
const rows = () => within(document.querySelector("aside")!).getAllByRole("listitem");
const queue = () => rows().map((li) => li.textContent!.match(/T\w/)![0]);

beforeEach(() => { file.text = JSON.stringify(settings()); });

describe("the rail", () => {
  test("the arrow keys, Home and End open the page they reach and keep the focus on it", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("tab", { name: zh["tab.teams"] }));
    await user.keyboard("{ArrowDown}");
    expect(tab(zh["tab.gifts"])).toHaveAttribute("aria-selected", "true");
    expect(tab(zh["tab.gifts"])).toHaveFocus();
    await user.keyboard("{ArrowUp}{ArrowUp}");
    expect(tab(zh["tab.run"])).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(tab(zh["tab.daily"])).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { level: 2, name: zh["tab.daily"] })).toBeInTheDocument();
  });

  test("only the open page is a Tab stop", async () => {
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.teams"] });
    const stops = within(document.querySelector("nav.rail") as HTMLElement).getAllByRole("tab").filter((x) => x.tabIndex === 0);
    expect(stops).toEqual([tab(zh["tab.teams"])]);
  });

  test("folds to its icons and back; the pages keep their names", async () => {
    const user = userEvent.setup();
    render(<App />);
    const toggle = await screen.findByRole("button", { name: zh["nav.toggle"] });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector("nav.rail")).toHaveClass("compact");
    expect(tab(zh["tab.teams"])).toHaveAttribute("title", zh["tab.teams"]);
    await user.click(toggle);
    expect(document.querySelector("nav.rail")).not.toHaveClass("compact");
  });
});

describe("the team list", () => {
  test("the arrow keys select the team above or below", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.teams"] });
    expect(nameBox()).toHaveValue("Ta");
    rows()[0].focus();
    await user.keyboard("{ArrowDown}");
    expect(nameBox()).toHaveValue("Tb");
    expect(rows()[1]).toHaveFocus();
    await user.keyboard("{End}");
    expect(nameBox()).toHaveValue("Tc");
  });

  test("Alt and the arrow keys move the team in the queue, and it keeps the focus", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.teams"] });
    rows()[0].focus();
    await user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(queue()).toEqual(["Tb", "Ta", "Tc"]);
    expect(rows()[1]).toHaveFocus();
    expect(nameBox()).toHaveValue("Ta");
    await user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(queue()).toEqual(["Tb", "Tc", "Ta"]);
    expect(screen.getByText(zh.unsaved)).toBeInTheDocument();
  });

  test("a team dragged onto another takes its place in the queue", async () => {
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.teams"] });
    const dataTransfer = { setData() {}, effectAllowed: "", dropEffect: "" };
    const [a, b] = rows();
    fireEvent.dragStart(b, { dataTransfer });
    fireEvent.dragOver(a, { dataTransfer });
    fireEvent.drop(a, { dataTransfer });
    fireEvent.dragEnd(b, { dataTransfer });
    expect(queue()).toEqual(["Tb", "Ta", "Tc"]);
  });

  test("only the selected team is a Tab stop", async () => {
    render(<App />);
    await screen.findByRole("tab", { name: zh["tab.teams"] });
    expect(rows().map((li) => li.tabIndex)).toEqual([0, -1, -1]);
  });
});

test("a refused save says so in the title bar, with the number of problems", async () => {
  const s = settings();
  s.teams[1].game_team = s.teams[0].game_team; // two enabled teams on one TEAMS slot (validate.ts crossCheck)
  file.text = JSON.stringify(s);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: zh.save }));
  expect(document.querySelector("header .status")).toHaveTextContent(zh.blockedCount.replace("{n}", "1"));
  expect(tab(zh["tab.teams"])).toHaveAttribute("aria-describedby", "problem-hint");
  expect(document.getElementById("problem-hint")).toHaveTextContent(zh.hasProblem);
});

test("a long help text shows its first sentence and a button for the rest; a caution shows whole", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("tab", { name: zh["tab.daily"] }));
  const note = screen.getByText((_, el) => el?.textContent === zh["daily.note"].replace(/\n/g, ""), { selector: "p" });
  expect(note).toHaveClass("sr-only"); // hidden from the eye only: a screen reader reads it whole
  const preview = note.parentElement!.querySelector(".preview")!;
  expect(preview.textContent).toBe(zh["daily.note"].split("\n")[0]); // a whole sentence, never cut inside one
  const more = note.parentElement!.querySelector("button.more")!;
  await user.click(more);
  expect(more).toHaveAttribute("aria-expanded", "true");
  expect(note).not.toHaveClass("sr-only");
  expect(note.parentElement!.querySelector(".preview")).toBeNull();
  const caution = screen.getByText((_, el) => el?.textContent === zh["charge.note"].replace(/\n/g, ""), { selector: "p" });
  expect(caution).toHaveClass("caution");
  expect(caution).not.toHaveClass("sr-only");
});

test("a problem marks its page while the player edits, before any save; the banner waits for a save", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  expect(tab(zh["tab.teams"])).not.toHaveClass("bad");
  fireEvent.change(screen.getByRole("spinbutton", { name: zh["team.game_team"] }), { target: { value: "2" } }); // Tb holds TEAMS #2
  expect(tab(zh["tab.teams"])).toHaveClass("bad");
  await user.click(tab(zh["tab.run"]));
  expect(tab(zh["tab.teams"])).toHaveClass("bad");
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a row with a long help names its switch by the label alone, and a click on the label works the switch", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("tab", { name: zh["tab.daily"] }));
  const [exp] = screen.getAllByRole("checkbox", { name: zh["lux.consecutive"] }); // the help's 顯示全部 button is outside the <label>
  const was = (exp as HTMLInputElement).checked;
  await user.click(screen.getAllByText(zh["lux.consecutive"])[0]);
  expect(exp).toHaveProperty("checked", !was);
});

test("a team's plan opens on its own page, and the plan's team list leads back to the team", async () => {
  const s = settings();
  s.deployment_order_plans = [{ id: "d1", name: "Bleed order", order: [...SINNERS] }];
  s.teams[1].deployment_order = { plan: "d1" };
  file.text = JSON.stringify(s);
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByText("Tb"));
  await user.click(screen.getByRole("button", { name: `${zh["plan.edit"]}${zh["sum.sep"]}${zh["team.deployment_order"]}` }));
  expect(tab(zh["tab.deployment"])).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Bleed order");
  await user.click(screen.getByRole("button", { name: "Tb" }));
  expect(tab(zh["tab.teams"])).toHaveAttribute("aria-selected", "true");
  expect(nameBox()).toHaveValue("Tb");
});

test("moving a team from its own order to a plan can be undone", async () => {
  const s = settings();
  s.deployment_order_plans = [{ id: "d1", name: "Bleed order", order: [...SINNERS] }];
  s.teams[0].deployment_order = { custom: ["Faust", "Yi Sang"] };
  file.text = JSON.stringify(s);
  const user = userEvent.setup();
  render(<App />);
  const pickPlan = await screen.findByRole("combobox", { name: zh["team.deployment_order"] });
  await user.selectOptions(pickPlan, "d1");
  expect(pickPlan).toHaveValue("d1");
  await user.click(screen.getByRole("button", { name: zh.undo }));
  expect(pickPlan).toHaveValue("");
  expect(screen.getByText(zh["sum.order"].replace("{d}", "2").replace("{b}", "0"))).toBeInTheDocument();
  const titles = [...document.querySelectorAll("details.exp > summary")].map((x) => x.firstChild?.textContent);
  expect(titles.filter((x) => x === zh["team.deployment_order"] || x === zh["team.starlight"])).toEqual([zh["team.deployment_order"], zh["team.starlight"]]);
});

test("Revert goes back to the saved settings after a confirm", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  expect(screen.queryByRole("button", { name: zh.revert })).toBeNull();
  await user.type(nameBox(), "!");
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  await user.click(screen.getByRole("button", { name: zh.revert }));
  expect(confirm).toHaveBeenCalledWith(zh.revertConfirm);
  expect(nameBox()).toHaveValue("Ta");
  expect(screen.queryByRole("button", { name: zh.revert })).toBeNull();
  confirm.mockRestore();
});

test("a folded section's header says what is set inside", async () => {
  const s = settings();
  s.teams[0].gift_search = { enabled: true, gifts: [{ keyword: "Burn", tier: 1, name: "Ashes to Ashes" }] };
  file.text = JSON.stringify(s);
  render(<App />);
  const summary = (await screen.findByText(zh["gift.title"], { selector: "summary" }));
  expect(summary.closest("details")).not.toHaveAttribute("open");
  expect(summary).toHaveTextContent(zh["sum.gifts"].replace("{n}", "1"));
});
