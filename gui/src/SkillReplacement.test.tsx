// Component tests of the teams tab's skill replacement panel (#454, spec 04 section 9): collapsed by default, the 12 sinners in
// priority order (drag or buttons), S1/S2/S3 targets that must total 6, each sinner's swaps with the Replace cell's price, and ID
// Skill Search's switch and payment.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { SINNERS, newSettings, newTeam, type Settings } from "./model";
import { renderEditor } from "./testing";
import { TeamsTab } from "./Teams";

const file = vi.hoisted(() => ({ text: "", saved: [] as string[] }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: (text: string) => { file.saved.push(text); return Promise.resolve(); },
  rootDir: () => Promise.resolve("root"),
}));

const zh = TEXT.zh_tw;
const settings = (language: Settings["language"] = "zh_tw"): Settings => ({ ...newSettings(), language, teams: [newTeam(1, "T1")] });
const panel = () => screen.getByText(zh["skill.title"], { exact: false, selector: "summary" }).closest("details")!;
const sinnerOrder = () => [...panel().querySelectorAll("li[data-sinner]")].map((li) => li.getAttribute("data-sinner"));
const row = (name: string) => panel().querySelector<HTMLElement>(`li[data-sinner="${name}"]`)!;
const target = (name: string) => (r: ReturnType<typeof renderEditor>, i = 0) => r.settings().teams[i].skill_replacement.sinners.find((x) => x.sinner === name)!;
const yi = target("Yi Sang");
const swapsOf = (name: string) => [...row(name).querySelectorAll("li[data-swap]")].map((li) => li.getAttribute("data-swap"));
const expand = (r: ReturnType<typeof renderEditor>) => r.user.click(within(panel()).getByText(zh["skill.title"], { exact: false, selector: "summary" }));
const dt = () => ({ setData() {}, effectAllowed: "", dropEffect: "" });
function drag(from: Element, to: Element) {
  fireEvent.dragStart(from, { dataTransfer: dt() });
  fireEvent.dragOver(to, { dataTransfer: dt() });
  fireEvent.drop(to, { dataTransfer: dt() });
  fireEvent.dragEnd(from, { dataTransfer: dt() });
}

describe("the panel", () => {
  test("is collapsed until opened, and lists the 12 sinners in the team's priority order", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    expect(panel().open).toBe(false);
    await expand(r);
    expect(panel().open).toBe(true);
    expect(sinnerOrder()).toEqual(SINNERS);
  });

  test("a row has S1, S2 and S3 fields with the team's targets, and says 不換 while the deck is the game's 3/2/1", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const field = (k: string) => screen.getByRole("spinbutton", { name: `Yi Sang ${k}` });
    expect([field("S1"), field("S2"), field("S3")].map((f) => (f as HTMLInputElement).value)).toEqual(["3", "2", "1"]);
    expect(within(row("Yi Sang")).getByText(zh["skill.untouched"])).toBeInTheDocument();
    expect(panel().querySelectorAll("li[data-sinner]")).toHaveLength(12);
    expect(within(panel()).getAllByText(zh["skill.untouched"])).toHaveLength(12);
  });

  test("the note says skill 3 needs Uptie 3 and that the skills gained only last this run", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    expect(within(panel()).getByText(zh["skill.note"])).toHaveTextContent("Uptie 3");
    expect(zh["skill.note"]).toContain("這一局");
  });
});

describe("targets", () => {
  test("a number typed in a field is stored, and the row no longer says 不換", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const s2 = screen.getByRole("spinbutton", { name: "Yi Sang S2" });
    await r.user.clear(s2);
    await r.user.type(s2, "3");
    await r.user.clear(screen.getByRole("spinbutton", { name: "Yi Sang S1" }));
    await r.user.type(screen.getByRole("spinbutton", { name: "Yi Sang S1" }), "2");
    expect(yi(r).target).toEqual({ s1: 2, s2: 3, s3: 1 });
    expect(within(row("Yi Sang")).queryByText(zh["skill.untouched"])).not.toBeInTheDocument();
    expect(within(row("Faust")).getByText(zh["skill.untouched"])).toBeInTheDocument(); // another sinner's row is its own
  });

  test("a total other than 6 shows an error on that row alone, and 6 clears it", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const s3 = screen.getByRole("spinbutton", { name: "Yi Sang S3" });
    await r.user.clear(s3);
    await r.user.type(s3, "3");
    const error = within(row("Yi Sang")).getByRole("alert");
    expect(error).toHaveTextContent("8");
    expect(error).toHaveTextContent("6");
    expect(within(panel()).getAllByRole("alert")).toHaveLength(1);
    await r.user.clear(screen.getByRole("spinbutton", { name: "Yi Sang S1" }));
    await r.user.type(screen.getByRole("spinbutton", { name: "Yi Sang S1" }), "1");
    expect(within(row("Yi Sang")).queryByRole("alert")).not.toBeInTheDocument();
    expect(yi(r).target).toEqual({ s1: 1, s2: 2, s3: 3 });
  });

  test("the fields stay within 0 to 6", async () => {
    renderEditor(<TeamsTab />, settings());
    const f = screen.getByRole("spinbutton", { name: "Yi Sang S1" });
    expect([f.getAttribute("min"), f.getAttribute("max")]).toEqual(["0", "6"]);
  });
});

describe("priority order", () => {
  test("the ↓ button moves a sinner one place down, ↑ moves it back, the ends have no way out", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    await r.user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh.down} Yi Sang` }));
    expect(r.settings().teams[0].skill_replacement.sinners.slice(0, 3).map((x) => x.sinner)).toEqual(["Faust", "Yi Sang", "Don Quixote"]);
    expect(sinnerOrder().slice(0, 3)).toEqual(["Faust", "Yi Sang", "Don Quixote"]);
    await r.user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh.up} Yi Sang` }));
    expect(sinnerOrder()).toEqual(SINNERS);
    expect(within(row("Yi Sang")).getByRole("button", { name: `${zh.up} Yi Sang` })).toBeDisabled();
    expect(within(row("Gregor")).getByRole("button", { name: `${zh.down} Gregor` })).toBeDisabled();
  });

  test("dragging a sinner onto another moves it there, with its target and swaps", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    await r.user.clear(screen.getByRole("spinbutton", { name: "Gregor S1" }));
    await r.user.type(screen.getByRole("spinbutton", { name: "Gregor S1" }), "0");
    await r.user.clear(screen.getByRole("spinbutton", { name: "Gregor S3" }));
    await r.user.type(screen.getByRole("spinbutton", { name: "Gregor S3" }), "4");
    drag(row("Gregor"), row("Yi Sang"));
    expect(sinnerOrder().slice(0, 2)).toEqual(["Gregor", "Yi Sang"]);
    expect(r.settings().teams[0].skill_replacement.sinners[0]).toMatchObject({ sinner: "Gregor", target: { s1: 0, s2: 2, s3: 4 } });
    expect(r.settings().teams[0].skill_replacement.sinners).toHaveLength(12);
  });
});

describe("swaps", () => {
  test("each sinner lists the three swaps in order, named by the skills they trade, with the Replace cell's price", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    expect(swapsOf("Yi Sang")).toEqual(["s1_s3", "s2_s3", "s1_s2"]);
    const li = (k: string) => row("Yi Sang").querySelector<HTMLElement>(`li[data-swap="${k}"]`)!;
    expect(li("s1_s3")).toHaveTextContent("SKILL 1 → 3");
    expect(li("s1_s3")).toHaveTextContent("120");
    expect(li("s2_s3")).toHaveTextContent("SKILL 2 → 3");
    expect(li("s2_s3")).toHaveTextContent("75");
    expect(li("s1_s2")).toHaveTextContent("SKILL 1 → 2");
    expect(li("s1_s2")).toHaveTextContent("45");
  });

  test("a swap moves down by its button or by a drag, for that sinner only", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const swap = (name: string, k: string) => row(name).querySelector<HTMLElement>(`li[data-swap="${k}"]`)!;
    await r.user.click(within(swap("Yi Sang", "s1_s3")).getByRole("button", { name: `${zh.down} SKILL 1 → 3` }));
    expect(yi(r).options).toEqual(["s2_s3", "s1_s3", "s1_s2"]);
    drag(swap("Yi Sang", "s1_s2"), swap("Yi Sang", "s2_s3"));
    expect(yi(r).options).toEqual(["s1_s2", "s2_s3", "s1_s3"]);
    expect(swapsOf("Yi Sang")).toEqual(["s1_s2", "s2_s3", "s1_s3"]);
    expect(target("Faust")(r).options).toEqual(["s1_s3", "s2_s3", "s1_s2"]);
    expect(sinnerOrder()).toEqual(SINNERS); // the swap's drag did not move a sinner
  });

  test("a swap being dragged is marked in its own sinner's row alone, though every row has the same swaps", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const swap = row("Yi Sang").querySelector<HTMLElement>('li[data-swap="s1_s3"]')!;
    fireEvent.dragStart(swap, { dataTransfer: dt() });
    expect([...panel().querySelectorAll("[data-dragging]")]).toEqual([swap]);
    fireEvent.dragEnd(swap, { dataTransfer: dt() });
  });

  test("a swap can be taken out and put back at the end; the last one cannot be taken out", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const remove = (name: string, k: string) => within(row(name).querySelector<HTMLElement>(`li[data-swap="${k}"]`)!).getByRole("button", { name: zh["skill.remove_swap"] });
    await r.user.click(remove("Yi Sang", "s1_s3"));
    expect(yi(r).options).toEqual(["s2_s3", "s1_s2"]);
    await r.user.click(remove("Yi Sang", "s2_s3"));
    expect(yi(r).options).toEqual(["s1_s2"]);
    expect(remove("Yi Sang", "s1_s2")).toBeDisabled();
    await r.user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh["skill.add_swap"]} SKILL 1 → 3` }));
    expect(yi(r).options).toEqual(["s1_s2", "s1_s3"]);
    expect(target("Faust")(r).options).toHaveLength(3);
  });
});

describe("ID Skill Search", () => {
  const pay = () => screen.getByRole("combobox", { name: zh["skill.pay"] });
  const enable = () => screen.getByRole("checkbox", { name: zh["skill.id_search"] });

  test("is off and paid in Cost to begin with; the payment can only be chosen once it is on", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    expect(enable()).not.toBeChecked();
    expect(pay()).toBeDisabled();
    expect(pay()).toHaveValue("cost");
    await r.user.click(enable());
    expect(r.settings().teams[0].skill_replacement.id_skill_search).toEqual({ enabled: true, pay: "cost" });
    expect(pay()).toBeEnabled();
  });

  test("starlight is the owned starlight and says so; Cost does not", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    await r.user.click(enable());
    expect(within(panel()).queryByText(zh["skill.pay_starlight_note"])).not.toBeInTheDocument();
    await r.user.selectOptions(pay(), "starlight");
    expect(r.settings().teams[0].skill_replacement.id_skill_search).toEqual({ enabled: true, pay: "starlight" });
    expect(within(panel()).getByText(zh["skill.pay_starlight_note"])).toHaveTextContent("持有的星光");
  });

  test("shows its prices for the chosen payment", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    const prices = () => within(panel()).getByTestId("id-search-prices").textContent;
    expect(prices()).toMatch(/SKILL 1 → 3.*240/);
    expect(prices()).toMatch(/SKILL 2 → 3.*150/);
    expect(prices()).toMatch(/SKILL 1 → 2.*90/);
    await r.user.click(enable());
    await r.user.selectOptions(pay(), "starlight");
    expect(prices()).toMatch(/SKILL 1 → 3.*75/);
    expect(prices()).toMatch(/SKILL 2 → 3.*50/);
    expect(prices()).toMatch(/SKILL 1 → 2.*25/);
  });
});

test("a team's panel edits that team alone", async () => {
  const s = { ...settings(), teams: [newTeam(1, "T1"), newTeam(2, "T2")] };
  const r = renderEditor(<TeamsTab />, s);
  await expand(r);
  await r.user.click(screen.getByRole("checkbox", { name: zh["skill.id_search"] }));
  expect(r.settings().teams.map((t) => t.skill_replacement.id_skill_search.enabled)).toEqual([true, false]);
});

test("the panel reads in English", async () => {
  const r = renderEditor(<TeamsTab />, settings("en_us"));
  const en = TEXT.en_us;
  await r.user.click(screen.getByText(en["skill.title"], { exact: false, selector: "summary" }));
  expect(screen.getAllByText(en["skill.untouched"])).toHaveLength(12);
  expect(screen.getByRole("checkbox", { name: en["skill.id_search"] })).toBeInTheDocument();
});

describe("in the whole editor", () => {
  beforeEach(() => { file.text = JSON.stringify(settings()); file.saved = []; });

  test("targets that do not total 6 block the save and name the sinner; fixing them saves", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByText(zh["skill.title"], { exact: false, selector: "summary" }));
    const s3 = screen.getByRole("spinbutton", { name: "Yi Sang S3" });
    await user.clear(s3);
    await user.type(s3, "2");
    await user.click(screen.getByRole("button", { name: zh.save }));
    expect(file.saved).toEqual([]);
    expect(screen.getAllByRole("alert").map((a) => a.textContent).join("\n")).toContain("Yi Sang");
    await user.clear(s3);
    await user.type(s3, "1");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).teams[0].skill_replacement.sinners[0].target).toEqual({ s1: 3, s2: 2, s3: 1 });
  });

  test("a file from before version 19 opens with the default and is written back migrated", async () => {
    const old = JSON.parse(file.text);
    old.version = 18;
    delete old.teams[0].skill_replacement;
    file.text = JSON.stringify(old);
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByText(zh["skill.title"], { exact: false, selector: "summary" }));
    expect(within(panel()).getAllByText(zh["skill.untouched"])).toHaveLength(12);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).version).toBe(19);
  });
});
