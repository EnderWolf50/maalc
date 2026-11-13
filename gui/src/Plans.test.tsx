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

const chipNamed = async (pack: string) => (await screen.findByText(pack, { selector: ".nm" })).closest(".pk") as HTMLElement;
/** The 含想要 mark on a pack's chip, by the name a screen reader reads, or null; the chips load with the data file. */
const markOf = async (pack: string) => within(await chipNamed(pack)).queryByRole("img", { name: zh["packs.wanted"] });

describe("the 含想要 mark", () => {
  test("the default list marks LCB Regular Check-up with a dot, which lists the two materials of 9780 on hover", async () => {
    renderEditor(<ThemePackTab />, settings());
    const tip = zh["packs.wantedTip"].replace("{names}", "常規作戰用裝備、作戰批准卡");
    const mark = await markOf("LCB Regular Check-up");
    expect(mark).toHaveAccessibleDescription(tip);
    expect(mark).toHaveTextContent(/^$/); // a dot in the corner (#720), not a word in the row
    const chip = await chipNamed("LCB Regular Check-up");
    expect(chip).not.toHaveTextContent(zh["packs.wanted"]);
    expect(chip).toHaveAttribute("title", tip); // the whole chip shows the gifts on hover, not just the dot
  });

  test("one line of the page says what the dot means, with the same dot", async () => {
    renderEditor(<ThemePackTab />, settings());
    const key = (await screen.findByText(zh["packs.wantedKey"])).closest("p")!;
    expect(key.querySelector(".wd")).not.toBeNull();
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
    expect(mark).toHaveAccessibleDescription(zh["packs.wantedTip"].replace("{names}", GIFT_BY_ID.get(own)!.zh));
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
    expect(mark).toHaveAccessibleDescription(zh["packs.wantedTip"].replace("{names}", GIFT_BY_ID.get(own)!.zh));
  });

  test("a list only a team of another plan holds does not count, and a plan no team uses reads the default list", async () => {
    const own = recipes.pack_gifts["1002"][0];
    const team = { ...newTeam(1, "T1"), gift_list: "mine", theme_pack_plan: "someone-else" };
    renderEditor(<ThemePackTab />, settings({ gift_lists: [mine([own])], teams: [team] }));
    expect(await markOf("The Outcast")).toBeNull();
    expect(await markOf("LCB Regular Check-up")).not.toBeNull();
  });
});

describe("finding a pack by name", () => {
  const plan = { id: "p1", name: "Mine", weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" };
  const open = async () => {
    const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [plan] }));
    await r.user.click(await screen.findByText("Mine"));
    return r;
  };
  const names = () => [...document.querySelectorAll(".pk .nm")].map((x) => x.textContent);
  const search = () => screen.getByRole("searchbox", { name: zh["packs.search"] });

  test("the search shows only the packs whose name holds what is typed, any case; Esc clears it", async () => {
    const r = await open();
    const all = names().length;
    await r.user.type(search(), "forg");
    expect(names()).toContain("The Forgotten");
    expect(names().every((n) => n!.toLowerCase().includes("forg"))).toBe(true);
    expect(names().length).toBeLessThan(all);
    await r.user.keyboard("{Escape}");
    expect(search()).toHaveValue("");
    expect(names().length).toBe(all);
  });

  test("/ jumps to the search from the page, and types a / in a field", async () => {
    const r = await open();
    (document.querySelector(".pk") as HTMLElement).focus();
    await r.user.keyboard("/");
    expect(search()).toHaveFocus();
    expect(search()).toHaveValue("");
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

  test("a pack dropped on the + below the lanes asks for the new lane's weight in that lane", async () => {
    const r = await open();
    const [, lane] = screen.getAllByText(new RegExp(zh["packs.newLane"])).map((x) => x.closest(".lane")!);
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

  test("a + above the lanes takes a pack too, so a score higher than every lane needs no drag past the list (#720)", async () => {
    const r = await open();
    const [top, bottom] = screen.getAllByText(new RegExp(zh["packs.newLane"])).map((x) => x.closest(".lane")!);
    const scored = [...document.querySelectorAll(".lane:not(.add)")];
    expect(top.compareDocumentPosition(scored[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(bottom.compareDocumentPosition(scored[scored.length - 1]) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    const dataTransfer = { setData() {}, effectAllowed: "", dropEffect: "" };
    const chip = await chipOf("The Forgotten");
    fireEvent.dragStart(chip, { dataTransfer });
    fireEvent.dragOver(top, { dataTransfer });
    fireEvent.drop(top, { dataTransfer });
    fireEvent.dragEnd(chip, { dataTransfer });
    expect(top).toContainElement(box());
    expect(bottom).not.toContainElement(box());
    await r.user.type(box(), "4{Enter}");
    expect(r.weights()["The Forgotten"]).toBe(4);
    expect(document.querySelector(".lane:not(.add) .w")).toHaveTextContent("+4");
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

test("INFINITY and EXTREME are choices of the filter and badges of a pack: 無限 and 極限 in Chinese", async () => {
  expect([zh["packs.floorsInfinity"], zh["packs.floorsExtreme"]]).toEqual(["無限", "極限"]); // the user's words, 2026-11-14
  const { user, unmount } = renderEditor(<ThemePackTab />, newSettings());
  await waitFor(() => expect(shown("Chachihu")).toBe(true));
  await user.click(chip("極限"));
  expect(shown("Chachihu")).toBe(true);
  expect(shown("The Forgotten")).toBe(false);
  await user.click(chip("無限"));
  expect(shown("Chachihu")).toBe(false);
  expect(shown("The Heartbreaking")).toBe(true);
  expect(screen.getAllByRole("img", { name: "無限 6–10" }).length).toBeGreaterThan(0);
  expect(document.querySelector(".floorkey")).toHaveTextContent(/無限.*極限/);
  unmount();
  renderEditor(<ThemePackTab />, { ...newSettings(), language: "en_us" });
  expect(chip("INFINITY")).toBeInTheDocument();
  expect(chip("EXTREME")).toBeInTheDocument();
});

test("the deployment order plan's grid shows each sinner's default identity card, the ones left out darkened (#718)", () => {
  const order = ["Ryōshū", "Yi Sang", "Faust", "Hong Lu", "Ishmael", "Rodion", "Outis", "Heathcliff", "Sinclair"];
  renderEditor(<DeploymentTab />, settings({ deployment_order_plans: [{ id: "p", name: "P", order }] }));
  const tile = (name: string) => within(document.querySelector<HTMLElement>(".sinners")!).getByRole("button", { name: new RegExp(name) });
  expect(tile("Gregor")).toHaveClass("out");
  expect(tile("Ryōshū")).not.toHaveClass("out");
  expect(tile("Ryōshū").querySelector("img")?.getAttribute("src")).toMatch(/sinner_cards\/10401\.webp$/); // Ryōshū's LCB Sinner
  expect(tile("Gregor").querySelector("img")?.getAttribute("src")).toMatch(/sinner_cards\/11201\.webp$/);
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

test("a grace card is a group named by its grace: a pick button says whether it is picked, the effects describe it", () => {
  renderEditor(<StarlightTab />, settings({ starlight_plans: [{ id: "s1", name: "Plan", ...defaultStarlight() }] }));
  const card = screen.getByRole("group", { name: GRACES[0].zh });
  expect(card).not.toHaveAttribute("role", "button");
  const pick = within(card).getByRole("button", { name: GRACES[0].zh });
  expect(pick).toHaveAttribute("aria-pressed");
  expect(pick).toHaveAccessibleDescription(new RegExp(GRACES[0].effects.base[0].replace(/^-/, "").replace(/[+()]/g, "\\$&")));
  const [, plus, plus2] = within(card).getAllByRole("button");
  expect(plus).toHaveAccessibleName(`${GRACES[0].zh} +`);
  expect(plus2).toHaveAccessibleName(`${GRACES[0].zh} ++`);
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
  screen.getByRole("button", { name: GRACES[1].zh }).focus();
  await r.user.keyboard("{Enter}");
  expect(levels()[1]).toBe("base");
});

// #719: a card reads as the game's does at each level. The expected titles, prices and yellow values are the game's own
// (its starlight page at + and ++, captures of 2026-11-13), except where comparing with the base text marks a little
// more or less than the game's hand-made marks: Chance Comet's "所選關鍵詞的" (the game: "所選關鍵詞").
describe("a grace card at each level", () => {
  /** The starlight tab on one plan whose grace n is at levels[n]; the others unselected. */
  const show = (levels: Record<number, string>) => {
    const plan = { id: "s1", name: "Plan", ...defaultStarlight() };
    for (const [n, level] of Object.entries(levels)) plan.levels[+n - 1] = level;
    return renderEditor(<StarlightTab />, settings({ starlight_plans: [plan] }));
  };
  const card = (n: number) => screen.getByRole("group", { name: GRACES[n - 1].zh });
  const marked = (n: number) => [...card(n).querySelectorAll("mark")].map((m) => m.textContent);

  test("at + the title gains a +, the price doubles, the + effects show and the values that changed are marked", () => {
    show({ 1: "plus" });
    expect(within(card(1)).getByText("起始之星+")).toBeInTheDocument();
    // the pick button's name is the title it shows, so a voice command can say it (WCAG 2.5.3)
    expect(within(card(1)).getByRole("button", { name: "起始之星+" })).toHaveAttribute("aria-pressed", "true");
    expect(within(card(1)).getByText("★ 20")).toBeInTheDocument();
    expect([...card(1).querySelectorAll("li")].map((li) => li.textContent)).toEqual(GRACES[0].effects.plus);
    expect(marked(1)).toEqual(["+250"]);
  });

  test("at ++ a line the base lacks is marked whole, even beside a base line it resembles", () => {
    show({ 7: "plus2" });
    expect(within(card(7)).getByText("星雲的寵愛++")).toBeInTheDocument();
    expect(within(card(7)).getByText("★ 120")).toBeInTheDocument();
    expect(marked(7)).toEqual(["進入第6層時，人格等級 +3", "+9"]);
  });

  test("a line reworded around the same values stays plain, and its new detail lines are marked and indented", () => {
    show({ 9: "plus" });
    const lines = [...card(9).querySelectorAll("li")];
    expect(lines[0]).toHaveTextContent("進入商店時，獲得1件合成·售賣專用飾品");
    expect(lines[0].querySelector("mark")).toBeNull();
    expect(lines.filter((li) => li.classList.contains("sub")).map((li) => li.textContent)).toEqual(["· 第5層及以下：1~3級", "· 第6層及以上：2~3級"]);
    expect(marked(9)).toEqual(["· 第5層及以下：1~3級", "· 第6層及以上：2~3級", "與第5層", "所選關鍵詞的"]);
  });

  test("unselected and at base a card keeps its plain title, the base price and the base text; its pick button says which", () => {
    show({ 2: "base" });
    for (const n of [1, 2]) {
      expect(within(card(n)).getByText(GRACES[n - 1].zh)).toBeInTheDocument();
      expect(within(card(n)).getByText("★ 10")).toBeInTheDocument();
      expect([...card(n).querySelectorAll("li")].map((li) => li.textContent)).toEqual(GRACES[n - 1].effects.base);
      expect(card(n).querySelector("mark")).toBeNull();
    }
    expect(within(card(1)).getByRole("button", { name: GRACES[0].zh })).toHaveAttribute("aria-pressed", "false");
    expect(within(card(2)).getByRole("button", { name: GRACES[1].zh })).toHaveAttribute("aria-pressed", "true");
  });

  test("the lit + or ++ says so, and the total is what the cards cost at their levels", () => {
    show({ 1: "plus", 7: "plus2", 2: "base" });
    const pressed = (n: number) => within(card(n)).getAllByRole("button").map((b) => b.getAttribute("aria-pressed"));
    expect(pressed(1)).toEqual(["true", "true", "false"]);
    expect(pressed(7)).toEqual(["true", "false", "true"]);
    expect(pressed(2)).toEqual(["true", "false", "false"]);
    expect(screen.getByText(zh["starlight.total"]).querySelector("b")).toHaveTextContent("★ 150"); // 20 + 120 + 10
  });

  test("every card shows its grace's icon from the game, as decoration the screen reader skips", () => {
    show({});
    GRACES.forEach((_, i) => {
      const icon = card(i + 1).querySelector("img");
      expect(icon?.getAttribute("src")).toMatch(new RegExp(`grace_icons/${i + 1}\\.webp$`));
      expect(icon).toHaveAttribute("alt", "");
    });
  });

  test("Select All and Enhance All + / ++ are lit while every card is selected, or at that level", () => {
    show(Object.fromEntries(GRACES.map((_, i) => [i + 1, "plus"])));
    expect(screen.getByRole("button", { name: zh["starlight.selectAll"] })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: `${zh["starlight.enhanceAll"]} +` })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: `${zh["starlight.enhanceAll"]} ++` })).toHaveAttribute("aria-pressed", "false");
    cleanup();
    show({ 1: "plus" });
    expect(screen.getByRole("button", { name: zh["starlight.selectAll"] })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: `${zh["starlight.enhanceAll"]} +` })).toHaveAttribute("aria-pressed", "false");
  });
});
