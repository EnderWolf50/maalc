// Component tests of the plan tabs: the theme pack screen's "含想要" mark (#421, spec 04 section 8), its filters, badges and
// weights typed in place, and for every plan tab which teams use a plan and how a deleted one comes back (#679).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, onTestFinished, test, vi } from "vitest";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import { GIFT_BY_ID } from "./giftCatalog";
import { TEXT, fill } from "./i18n";
import {
  GIFT_KEYWORDS, GRACES, SINNERS, defaultGorder, defaultStarlight, newSettings, newTeam, type GiftList, type Settings,
} from "./model";
import { DeploymentTab, StarlightTab, ThemePackTab } from "./Plans";
import { expectLines, renderEditor } from "./testing";
import { useEditor } from "./ui";

const zh = TEXT.zh_tw;
const mine = (want: number[]): GiftList => ({
  id: "mine", name: "Mine", order: [...GIFT_KEYWORDS], want, keep: [], gorder: defaultGorder(), fusion_condition: "any",
});
const settings = (patch: Partial<Settings> = {}): Settings => ({ ...newSettings(), language: "zh_tw", ...patch });

/** The mark on a pack's chip, or null; the chips load with the data file, so wait for the chip. */
async function markOf(pack: string) {
  const chip = (await screen.findByText(pack, { selector: ".nm" })).closest(".pk") as HTMLElement;
  return chip.querySelector<HTMLElement>(".wk");
}

describe("the 含想要 mark", () => {
  test("the default list marks LCB Regular Check-up and lists the two materials of 9780", async () => {
    renderEditor(<ThemePackTab />, settings());
    const mark = await markOf("LCB Regular Check-up");
    expect(mark?.textContent).toBe(zh["packs.wanted"]);
    expect(mark?.getAttribute("title")).toBe(zh["packs.wantedTip"].replace("{names}", "常規作戰用裝備、作戰批准卡"));
  });

  test("a pack whose own gifts none is wanted shows no mark", async () => {
    renderEditor(<ThemePackTab />, settings());
    expect(await markOf("The Outcast")).toBeNull();
  });

  test("wanting one of a pack's own gifts in the list a team of the plan holds marks that pack", async () => {
    const own = recipes.pack_gifts["1002"][0]; // The Outcast
    const team = { ...newTeam(1, "T1"), gift_list: "mine", theme_pack_plan: "default" };
    renderEditor(<ThemePackTab />, settings({ gift_lists: [mine([own])], teams: [team] }));
    const mark = await markOf("The Outcast");
    expect(mark?.getAttribute("title")).toBe(zh["packs.wantedTip"].replace("{names}", GIFT_BY_ID.get(own)!.zh));
  });

  test("changing a pack's own gift to wanted in the list shows the mark on that pack", async () => {
    // #421: the edit goes through the same settings update the gift list editor uses
    const own = recipes.pack_gifts["1002"][0];
    const team = { ...newTeam(1, "T1"), gift_list: "mine", theme_pack_plan: "default" };
    function WantIt() {
      const { update } = useEditor();
      return <button onClick={() => update((s) => { s.gift_lists[0].want = [own]; })}>want it</button>;
    }
    const r = renderEditor(<><ThemePackTab /><WantIt /></>, settings({ gift_lists: [mine([])], teams: [team] }));
    expect(await markOf("The Outcast")).toBeNull();
    await r.user.click(screen.getByRole("button", { name: "want it" }));
    const mark = await markOf("The Outcast");
    expect(mark?.getAttribute("title")).toBe(zh["packs.wantedTip"].replace("{names}", GIFT_BY_ID.get(own)!.zh));
  });

  test("a list only a team of another plan holds does not count, and a plan no team uses reads the default list", async () => {
    const own = recipes.pack_gifts["1002"][0];
    const team = { ...newTeam(1, "T1"), gift_list: "mine", theme_pack_plan: "someone-else" };
    renderEditor(<ThemePackTab />, settings({ gift_lists: [mine([own])], teams: [team] }));
    expect(await markOf("The Outcast")).toBeNull();
    expect(await markOf("LCB Regular Check-up")).not.toBeNull();
  });
});

describe("a pack's weight, typed in place (no prompt dialog)", () => {
  const plan = () => ({ id: "p1", name: "Mine", weights: { "The Outcast": -1 }, threshold: 0, unlisted: 0, event_packs: "weight" });
  /** The theme pack tab on plan Mine; window.prompt only counts calls. */
  async function open() {
    const asked = vi.spyOn(window, "prompt").mockReturnValue(null);
    onTestFinished(() => asked.mockRestore());
    const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [plan()] }));
    await r.user.click(await screen.findByText("Mine"));
    return { ...r, asked, weights: () => r.settings().theme_pack_plans[0].weights };
  }
  const chipOf = async (name: string) => (await screen.findByText(name, { selector: ".nm" })).closest(".pk") as HTMLElement;
  const box = () => screen.getByRole("spinbutton", { name: zh["packs.weightPrompt"] });

  test("clicking a pack opens a box on it with its weight; Enter keeps the new one", async () => {
    const r = await open();
    await r.user.click(await chipOf("The Forgotten"));
    expect(box()).toHaveFocus();
    expect(box()).toHaveValue(0);
    await r.user.clear(box());
    await r.user.type(box(), "3{Enter}");
    expect(r.weights()["The Forgotten"]).toBe(3);
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(r.asked).not.toHaveBeenCalled();
  });

  test("Esc leaves the weight as it was", async () => {
    const r = await open();
    await r.user.click(await chipOf("The Outcast"));
    await r.user.clear(box());
    await r.user.type(box(), "5{Escape}");
    expect(r.weights()).toEqual({ "The Outcast": -1 });
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  test("a weight outside -10..10 says so beside the box and keeps the old one", async () => {
    const r = await open();
    await r.user.click(await chipOf("The Outcast"));
    await r.user.clear(box());
    await r.user.type(box(), "11{Enter}");
    expect(screen.getByText(zh["packs.weightRange"])).toBeInTheDocument();
    expect(box()).toBeInTheDocument();
    expect(r.weights()).toEqual({ "The Outcast": -1 });
  });

  test("a pack dropped on + asks for the new lane's weight in that lane", async () => {
    const r = await open();
    const lane = screen.getByText(new RegExp(zh["packs.newLane"])).closest(".lane")!;
    const dataTransfer = { setData() {}, effectAllowed: "", dropEffect: "" };
    const chip = await chipOf("The Forgotten");
    fireEvent.dragStart(chip, { dataTransfer });
    fireEvent.dragOver(lane, { dataTransfer });
    fireEvent.drop(lane, { dataTransfer });
    fireEvent.dragEnd(chip, { dataTransfer });
    expect(lane).toContainElement(box());
    await r.user.type(box(), "-2{Enter}");
    expect(r.weights()["The Forgotten"]).toBe(-2);
    expect(r.asked).not.toHaveBeenCalled();
  });

  test("Enter on a focused pack opens the box too, and the unlisted packs' chip has one", async () => {
    const r = await open();
    (await chipOf("The Forgotten")).focus();
    await r.user.keyboard("{Enter}");
    expect(box()).toHaveFocus();
    await r.user.keyboard("{Escape}");
    await r.user.click(await chipOf(zh["packs.unlisted"]));
    await r.user.clear(box());
    await r.user.type(box(), "-4{Enter}");
    expect(r.settings().theme_pack_plans[0].unlisted).toBe(-4);
  });

  test("keys the box does not use still reach the window: Ctrl+S saves from it", async () => {
    const r = await open();
    const heard: string[] = [];
    const listen = (e: KeyboardEvent) => { heard.push(e.key); };
    window.addEventListener("keydown", listen);
    onTestFinished(() => window.removeEventListener("keydown", listen));
    await r.user.click(await chipOf("The Outcast"));
    await r.user.keyboard("{Control>}s{/Control}");
    expect(heard).toContain("s");
  });

  test("a click on the chip around the box keeps the box and what was typed", async () => {
    const r = await open();
    const chip = await chipOf("The Outcast");
    await r.user.click(chip);
    await r.user.clear(box());
    await r.user.type(box(), "7");
    await r.user.click(within(chip).getByText("The Outcast"));
    expect(box()).toHaveValue(7);
    expect(box()).toHaveFocus();
  });
});

describe("dragging a pack chip", () => {
  test("onto another weight's lane sets that weight, whatever the marks beside the chips", async () => {
    const plan = { id: "p1", name: "Mine", weights: { "The Outcast": -1 }, threshold: 0, unlisted: 0, event_packs: "weight" };
    const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [plan] }));
    await r.user.click(await screen.findByText("Mine"));
    const chip = (await screen.findByText("The Forgotten", { selector: ".nm" })).closest(".pk")!;
    const lane = (await screen.findByText("The Outcast", { selector: ".nm" })).closest(".lane")!;
    const dataTransfer = { setData() {}, effectAllowed: "", dropEffect: "" };
    fireEvent.dragStart(chip, { dataTransfer });
    fireEvent.dragOver(lane, { dataTransfer });
    fireEvent.drop(lane, { dataTransfer });
    fireEvent.dragEnd(chip, { dataTransfer });
    expect(r.settings().theme_pack_plans[0].weights).toEqual({ "The Outcast": -1, "The Forgotten": -1 });
  });
});

// The theme pack tab's filter and badges (#387).
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

test("the difficulty filter names the difficulties as the floor badges do: 普通 and 困難 in Chinese, NORMAL and HARD in English", async () => {
  const { user, unmount } = renderEditor(<ThemePackTab />, newSettings());
  await waitFor(() => expect(shown("Chachihu")).toBe(true));
  expect(screen.queryByRole("button", { name: "NORMAL" })).toBeNull();
  await user.click(chip(zh["packs.floorsHard"]));
  expect(chip(zh["packs.floorsHard"])).toHaveAttribute("aria-pressed", "true");
  expect(shown("Chachihu")).toBe(false); // EXTREME only
  expect(chip(zh["packs.floorsNormal"])).toBeInTheDocument();
  unmount();
  renderEditor(<ThemePackTab />, { ...newSettings(), language: "en_us" });
  expect(chip("NORMAL")).toBeInTheDocument();
  expect(chip("HARD")).toBeInTheDocument();
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

describe("deleting a plan", () => {
  test("can be undone: the plan comes back in its place, in the editor", async () => {
    const plans = ["D1", "D2", "D3"].map((name) => ({ id: name.toLowerCase(), name, order: [...SINNERS] }));
    const r = renderEditor(<DeploymentTab />, settings({ deployment_order_plans: plans }));
    await r.user.click(within(document.querySelector("aside")!).getByText("D2"));
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    expect(r.settings().deployment_order_plans.map((p) => p.name)).toEqual(["D1", "D3"]);
    expect(screen.getByRole("status")).toHaveTextContent(fill(zh["undo.deleted"], { name: "D2" }));
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect(r.settings().deployment_order_plans).toEqual(plans);
    expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("D2");
    expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
  });
});

describe("which teams use a plan", () => {
  const teams = () => [
    { ...newTeam(1, "Ta"), deployment_order: { plan: "d1" } },
    { ...newTeam(2, "Tb"), theme_pack_plan: "p1" },
    { ...newTeam(3, "Tc"), deployment_order: { plan: "d1" } },
  ];
  const plans = ["D1", "D2"].map((name) => ({ id: name.toLowerCase(), name, order: [...SINNERS] }));

  test("a plan lists the teams that use it, and says so when none does", async () => {
    const r = renderEditor(<DeploymentTab />, settings({ deployment_order_plans: plans, teams: teams() }));
    expect(screen.getByText(fill(zh["plan.usedBy"], { names: "Ta、Tc" }))).toBeInTheDocument();
    await r.user.click(within(document.querySelector("aside")!).getByText("D2"));
    expect(screen.getByText(zh["plan.unused"])).toBeInTheDocument();
  });

  test("a starlight plan and a named theme pack plan list theirs too", async () => {
    const star = { ...defaultStarlight(), id: "s1", name: "S1" };
    const t = teams();
    t[2].starlight = { plan: "s1" };
    renderEditor(<StarlightTab />, settings({ starlight_plans: [star], teams: t }));
    expect(screen.getByText(fill(zh["plan.usedBy"], { names: "Tc" }))).toBeInTheDocument();
    cleanup();
    const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [{ id: "p1", name: "P1", weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" }], teams: teams() }));
    await r.user.click(await screen.findByText("P1"));
    expect(screen.getByText(fill(zh["plan.usedBy"], { names: "Tb" }))).toBeInTheDocument();
  });

  test("the theme packs' default plan lists the teams on the default", async () => {
    renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [{ id: "p1", name: "P1", weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" }], teams: teams() }));
    expect(await screen.findByText(fill(zh["plan.usedBy"], { names: "Ta、Tc" }))).toBeInTheDocument();
  });
});

test("a plan's hint and the event pack note show one topic to a line", async () => {
  const plan = { id: "p1", name: "Mine", weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" };
  const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [plan] }));
  await r.user.click(await screen.findByText("Mine"));
  await screen.findByText(zh["packs.eventPacks"]);
  expectLines(zh["packs.hint"]);
  expectLines(zh["packs.eventPacksNote"]);
});

test("a grace's + and ++ take Enter and Space from the keyboard, as a click, and the card's own keys still pick it", async () => {
  const r = renderEditor(<StarlightTab />, settings({ starlight_plans: [{ id: "s1", name: "Plan", ...defaultStarlight() }] }));
  const name = GRACES[0].zh;
  const levels = () => r.settings().starlight_plans[0].levels;
  screen.getByRole("button", { name: `${name} +` }).focus();
  await r.user.keyboard("{Enter}");
  expect(levels()[0]).toBe("plus");
  screen.getByRole("button", { name: `${name} ++` }).focus();
  await r.user.keyboard(" ");
  expect(levels()[0]).toBe("plus2");
  (document.querySelectorAll(".grace")[1] as HTMLElement).focus();
  await r.user.keyboard("{Enter}");
  expect(levels()[1]).toBe("base");
});
