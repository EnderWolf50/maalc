// Component tests of the teams tab's skill replacement panel (#454, spec 04 section 9; the layout the user adopted on 2026-11-06):
// collapsed by default; only the sinners to change are listed, in priority order (drag or buttons), each with S1 worked out from
// the S2 and S3 steppers, the swaps the target needs and, when it needs two kinds, which to try first; ID Skill Search's switch
// and payment below.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { SINNERS, newSettings, newTeam, type Settings, type SkillSinner } from "./model";
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
const entry = (sinner: string, s1: number, s2: number, s3: number, s1_s3_first = true): SkillSinner =>
  ({ sinner, target: { s1, s2, s3 }, s1_s3_first });
const settings = (sinners: SkillSinner[] = [], language: Settings["language"] = "zh_tw"): Settings => {
  const team = newTeam(1, "T1");
  team.skill_replacement.sinners = sinners;
  return { ...newSettings(), language, teams: [team] };
};
const panel = () => screen.getByText(zh["skill.title"], { exact: false, selector: "summary" }).closest("details")!;
const listed = () => [...panel().querySelectorAll("li[data-sinner]")].map((li) => li.getAttribute("data-sinner"));
const row = (name: string) => panel().querySelector<HTMLElement>(`li[data-sinner="${name}"]`)!;
const stored = (r: ReturnType<typeof renderEditor>, i = 0) => r.settings().teams[i].skill_replacement.sinners;
const expand = (r: ReturnType<typeof renderEditor>) => r.user.click(within(panel()).getByText(zh["skill.title"], { exact: false, selector: "summary" }));
const add = (r: ReturnType<typeof renderEditor>, name: string) => r.user.selectOptions(screen.getByRole("combobox", { name: zh["skill.add"] }), name);
const step = (name: string, k: "S2" | "S3", d: "dec" | "inc") => within(row(name)).getByRole("button", { name: `${name} ${k} ${zh[`skill.${d}`]}` });
const s1 = (name: string) => within(row(name)).getByLabelText(`${name} S1`);
const pill = (name: string) => row(name).querySelector<HTMLElement>(".skill-pill")!;
const order = (name: string) => within(row(name)).getByRole<HTMLSelectElement>("combobox", { name: `${name} ${zh["skill.order"]}` });
const rest = () => panel().querySelector<HTMLElement>(".skill-rest")!;
const dt = () => ({ setData() {}, effectAllowed: "", dropEffect: "" });
function drag(from: Element, to: Element) {
  fireEvent.dragStart(from, { dataTransfer: dt() });
  fireEvent.dragOver(to, { dataTransfer: dt() });
  fireEvent.drop(to, { dataTransfer: dt() });
  fireEvent.dragEnd(from, { dataTransfer: dt() });
}

describe("the list", () => {
  test("is collapsed until opened; with nobody listed it says every deck stays 3/2/1 and names all 12 as unchanged", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    expect(panel().open).toBe(false);
    await expand(r);
    expect(panel().open).toBe(true);
    expect(listed()).toEqual([]);
    expect(within(panel()).getByText(zh["skill.empty"])).toBeInTheDocument();
    expect(rest()).toHaveTextContent(zh["skill.rest"] + SINNERS.join(zh["skill.sep"]));
  });

  test("the add select offers the unlisted sinners; picking one lists them last at 3/2/1, S1→S3 first", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Faust", 2, 2, 2)]));
    await expand(r);
    const select = screen.getByRole<HTMLSelectElement>("combobox", { name: zh["skill.add"] });
    expect([...select.options].slice(1).map((o) => o.value)).toEqual(SINNERS.filter((s) => s !== "Faust"));
    await add(r, "Yi Sang");
    await add(r, "Ryōshū");
    expect(stored(r)).toEqual([entry("Faust", 2, 2, 2), entry("Yi Sang", 3, 2, 1), entry("Ryōshū", 3, 2, 1)]);
    expect(listed()).toEqual(["Faust", "Yi Sang", "Ryōshū"]);
    expect([...select.options].map((o) => o.value)).not.toContain("Yi Sang");
    expect(select).toHaveValue("");
    expect(within(panel()).queryByText(zh["skill.empty"])).not.toBeInTheDocument();
    expect(rest()).not.toHaveTextContent("Yi Sang");
    expect(rest()).toHaveTextContent("Don Quixote");
    expect(pill("Yi Sang")).toHaveTextContent(zh["skill.unchanged"]);
  });

  test("with all 12 listed the add select has nobody left and the unchanged line says none", async () => {
    const r = renderEditor(<TeamsTab />, settings(SINNERS.map((s) => entry(s, 3, 2, 1))));
    await expand(r);
    expect(screen.getByRole("combobox", { name: zh["skill.add"] })).toBeDisabled();
    expect(rest()).toHaveTextContent(zh["skill.rest"] + zh["skill.rest_none"]);
  });

  test("✕ takes a sinner off the list, back to unchanged", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 2, 2), entry("Ryōshū", 1, 3, 2)]));
    await expand(r);
    await r.user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh["skill.remove"]} Yi Sang` }));
    expect(stored(r)).toEqual([entry("Ryōshū", 1, 3, 2)]);
    expect(listed()).toEqual(["Ryōshū"]);
    expect(rest()).toHaveTextContent("Yi Sang");
  });

  test("the notes: the shop cell's name, Uptie 3 for skill 3, and no price anywhere", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 1, 3, 2)]));
    await expand(r);
    expect(zh["skill.note"]).toContain("替換○○的技能（Replace ○○'s Skill）");
    expect(within(panel()).getByText(zh["skill.uptie"])).toHaveTextContent("Uptie 3");
    expect(zh["skill.uptie"]).toContain("這一局");
    // the Replace cell's prices are 45, 75 and 120 Cost, ID Skill Search's 90, 150 and 240 Cost or 25, 50 and 75 starlight
    expect(panel().querySelector("ol.skill-sinners")).not.toHaveTextContent(/Cost|25|45|50|75|90|120|150|240/);
    expect(within(panel()).queryByTestId("id-search-prices")).not.toBeInTheDocument();
  });
});

describe("targets", () => {
  test("S1 is read-only and follows S2 and S3; a + on S2 or S3 takes a card from S1, a − gives it back", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 3, 2, 1)]));
    await expand(r);
    expect(s1("Yi Sang")).toHaveTextContent("3");
    expect(within(row("Yi Sang")).queryByRole("spinbutton")).not.toBeInTheDocument();
    await r.user.click(step("Yi Sang", "S3", "inc"));
    expect(stored(r)[0].target).toEqual({ s1: 2, s2: 2, s3: 2 });
    expect(s1("Yi Sang")).toHaveTextContent("2");
    await r.user.click(step("Yi Sang", "S2", "inc"));
    expect(stored(r)[0].target).toEqual({ s1: 1, s2: 3, s3: 2 });
    await r.user.click(step("Yi Sang", "S2", "dec"));
    expect(stored(r)[0].target).toEqual({ s1: 2, s2: 2, s3: 2 });
  });

  test("a button greys out at its limit, so every target stays reachable: S1 0..3, S2 0 and up, S3 1 and up", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 3, 2, 1)]));
    await expand(r);
    // at 3/2/1, S1 is at its most: neither − can give it a card back
    expect([step("Yi Sang", "S2", "dec"), step("Yi Sang", "S3", "dec")].map((b) => (b as HTMLButtonElement).disabled)).toEqual([true, true]);
    expect([step("Yi Sang", "S2", "inc"), step("Yi Sang", "S3", "inc")].map((b) => (b as HTMLButtonElement).disabled)).toEqual([false, false]);
    for (let n = 0; n < 3; n++) await r.user.click(step("Yi Sang", "S3", "inc"));
    expect(stored(r)[0].target).toEqual({ s1: 0, s2: 2, s3: 4 });
    // S1 at 0: no + is left
    expect(step("Yi Sang", "S2", "inc")).toBeDisabled();
    expect(step("Yi Sang", "S3", "inc")).toBeDisabled();
    await r.user.click(step("Yi Sang", "S2", "dec"));
    await r.user.click(step("Yi Sang", "S2", "dec"));
    expect(stored(r)[0].target).toEqual({ s1: 2, s2: 0, s3: 4 });
    expect(step("Yi Sang", "S2", "dec")).toBeDisabled(); // S2 at 0
    for (let n = 0; n < 3; n++) await r.user.click(step("Yi Sang", "S3", "dec"));
    expect(stored(r)[0].target).toEqual({ s1: 3, s2: 0, s3: 3 });
    expect(step("Yi Sang", "S3", "dec")).toBeDisabled(); // S1 back at 3
  });

  test("S3 does not go below 1", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 3, 1)]));
    await expand(r);
    expect(step("Yi Sang", "S3", "dec")).toBeDisabled();
    expect(step("Yi Sang", "S2", "dec")).toBeEnabled();
  });

  test("the pill shows the swaps the target needs, or 還沒變更 at 3/2/1", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 2, 2), entry("Ryōshū", 1, 3, 2), entry("Faust", 3, 2, 1)]));
    await expand(r);
    expect(pill("Yi Sang")).toHaveTextContent(/^S1→S3 ×1$/);
    expect(pill("Ryōshū")).toHaveTextContent(/^S1→S2 ×1、S1→S3 ×1$/);
    expect(pill("Faust")).toHaveTextContent(zh["skill.unchanged"]);
    expect(pill("Faust")).toHaveClass("off");
  });

  test("the order select is open only for a target that needs two kinds of swap, and stores s1_s3_first", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 2, 2), entry("Ryōshū", 1, 3, 2), entry("Faust", 3, 2, 1)]));
    await expand(r);
    for (const name of ["Yi Sang", "Faust"]) {
      expect(order(name)).toBeDisabled();
      expect(order(name).selectedOptions[0]).toHaveTextContent("—");
    }
    const two = order("Ryōshū");
    expect(two).toBeEnabled();
    expect([...two.options].map((o) => o.textContent)).toEqual(["先換 S1→S3", "先換 S1→S2"]);
    expect(two).toHaveValue("s1_s3");
    await r.user.selectOptions(two, "s1_s2");
    expect(stored(r)[1]).toEqual(entry("Ryōshū", 1, 3, 2, false));
    expect(order("Ryōshū")).toHaveValue("s1_s2");
    await r.user.selectOptions(order("Ryōshū"), "s1_s3");
    expect(stored(r)[1].s1_s3_first).toBe(true);
  });

  test("a target below S2 2 that needs two kinds offers S2→S3 as the other", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 1, 3, false)]));
    await expand(r);
    expect(pill("Yi Sang")).toHaveTextContent(/^S2→S3 ×1、S1→S3 ×1$/);
    expect([...order("Yi Sang").options].map((o) => o.textContent)).toEqual(["先換 S1→S3", "先換 S2→S3"]);
    expect(order("Yi Sang")).toHaveValue("s2_s3");
  });
});

describe("priority order", () => {
  test("↓ moves a sinner one place down, ↑ moves it back, the ends have no way out", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 2, 2), entry("Faust", 3, 2, 1), entry("Gregor", 1, 1, 4)]));
    await expand(r);
    await r.user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh.down} Yi Sang` }));
    expect(stored(r).map((x) => x.sinner)).toEqual(["Faust", "Yi Sang", "Gregor"]);
    expect(listed()).toEqual(["Faust", "Yi Sang", "Gregor"]);
    await r.user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh.up} Yi Sang` }));
    expect(listed()).toEqual(["Yi Sang", "Faust", "Gregor"]);
    expect(within(row("Yi Sang")).getByRole("button", { name: `${zh.up} Yi Sang` })).toBeDisabled();
    expect(within(row("Gregor")).getByRole("button", { name: `${zh.down} Gregor` })).toBeDisabled();
  });

  test("dragging a sinner onto another moves it there, with its target and order", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 2, 2, 2), entry("Faust", 3, 2, 1), entry("Gregor", 1, 3, 2, false)]));
    await expand(r);
    drag(row("Gregor"), row("Yi Sang"));
    expect(listed()).toEqual(["Gregor", "Yi Sang", "Faust"]);
    expect(stored(r)).toEqual([entry("Gregor", 1, 3, 2, false), entry("Yi Sang", 2, 2, 2), entry("Faust", 3, 2, 1)]);
    expect(row("Gregor").querySelector(".skill-rank")).toHaveTextContent(/^1$/);
  });
});

describe("a target a hand-edited file made unreachable", () => {
  test("outlines its row with what is wrong, and leaves every stepper and the order select off", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 4, 1, 1), entry("Faust", 2, 2, 2)]));
    await expand(r);
    // not the editor's generic "bad", whose `.bad select` rule would outline the row's disabled order select too
    expect(row("Yi Sang")).toHaveClass("faulty");
    expect(row("Yi Sang")).not.toHaveClass("bad");
    expect(row("Faust")).not.toHaveClass("faulty");
    expect(within(row("Yi Sang")).getByRole("alert")).toHaveTextContent(zh["skill.fault_s1"]);
    expect(within(panel()).getAllByRole("alert")).toHaveLength(1);
    expect(s1("Yi Sang")).toHaveTextContent("4");
    for (const k of ["S2", "S3"] as const) for (const d of ["dec", "inc"] as const) expect(step("Yi Sang", k, d)).toBeDisabled();
    expect(order("Yi Sang")).toBeDisabled();
    expect(step("Faust", "S3", "inc")).toBeEnabled();
  });

  test("a count outside 0 to 6 is a fault too, though it totals 6", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 3, -1, 4)]));
    await expand(r);
    expect(within(row("Yi Sang")).getByRole("alert")).toHaveTextContent(zh["skill.fault_range"]);
    expect(step("Yi Sang", "S3", "inc")).toBeDisabled();
    expect(order("Yi Sang")).not.toHaveAttribute("title");
  });

  test("names each fault, the total among them", async () => {
    const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 5, 2, 0)]));
    await expand(r);
    const alert = within(row("Yi Sang")).getByRole("alert");
    expect(alert).toHaveTextContent("7");
    expect(alert).toHaveTextContent(zh["skill.fault_s1"]);
    expect(alert).toHaveTextContent(zh["skill.fault_s3"]);
  });
});

describe("ID Skill Search", () => {
  const pay = () => screen.getByRole("combobox", { name: zh["skill.pay"] });
  const enable = () => screen.getByRole("checkbox", { name: zh["skill.id_search"] });

  test("goes by its community Chinese name, and is off and paid in Cost to begin with; the payment opens once it is on", async () => {
    const r = renderEditor(<TeamsTab />, settings());
    await expand(r);
    expect(zh["skill.id_search"]).toBe("人格技能觀測（ID Skill Search，特殊商店）");
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
});

test("a team's panel edits that team alone", async () => {
  const s = { ...settings(), teams: [newTeam(1, "T1"), newTeam(2, "T2")] };
  const r = renderEditor(<TeamsTab />, s);
  await expand(r);
  await add(r, "Outis");
  await r.user.click(screen.getByRole("checkbox", { name: zh["skill.id_search"] }));
  expect(r.settings().teams.map((t) => t.skill_replacement.sinners.length)).toEqual([1, 0]);
  expect(r.settings().teams.map((t) => t.skill_replacement.id_skill_search.enabled)).toEqual([true, false]);
});

test("the panel reads in English", async () => {
  const r = renderEditor(<TeamsTab />, settings([entry("Yi Sang", 3, 2, 1)], "en_us"));
  const en = TEXT.en_us;
  await r.user.click(screen.getByText(en["skill.title"], { exact: false, selector: "summary" }));
  expect(en["skill.id_search"]).toBe("ID Skill Search (Super Shop)");
  expect(screen.getByText(en["skill.unchanged"])).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: en["skill.add"] })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: `Yi Sang S2 ${en["skill.inc"]}` })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: en["skill.id_search"] })).toBeInTheDocument();
});

describe("in the whole editor", () => {
  beforeEach(() => { file.text = JSON.stringify(settings()); file.saved = []; });

  test("the list, the targets and s1_s3_first are saved", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByText(zh["skill.title"], { exact: false, selector: "summary" }));
    await user.selectOptions(screen.getByRole("combobox", { name: zh["skill.add"] }), "Ryōshū");
    await user.click(step("Ryōshū", "S2", "inc"));
    await user.click(step("Ryōshū", "S3", "inc"));
    await user.selectOptions(order("Ryōshū"), "s1_s2");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).teams[0].skill_replacement.sinners).toEqual([entry("Ryōshū", 1, 3, 2, false)]);
  });

  test("a file holding an unreachable target blocks the save and names the sinner; removing it saves", async () => {
    file.text = JSON.stringify(settings([entry("Yi Sang", 4, 1, 1)]));
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByText(zh["skill.title"], { exact: false, selector: "summary" }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    expect(file.saved).toEqual([]);
    expect(screen.getAllByRole("alert").map((a) => a.textContent).join("\n")).toContain("'Yi Sang' targets 4 of skill 1");
    await user.click(within(row("Yi Sang")).getByRole("button", { name: `${zh["skill.remove"]} Yi Sang` }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).teams[0].skill_replacement.sinners).toEqual([]);
  });

  test("a file from before version 19 opens with nobody listed and is written back migrated", async () => {
    const old = JSON.parse(file.text);
    old.version = 18;
    delete old.teams[0].skill_replacement;
    file.text = JSON.stringify(old);
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByText(zh["skill.title"], { exact: false, selector: "summary" }));
    expect(within(panel()).getByText(zh["skill.empty"])).toBeInTheDocument();
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).version).toBe(19);
    expect(JSON.parse(file.saved[0]).teams[0].skill_replacement.sinners).toEqual([]);
  });
});
