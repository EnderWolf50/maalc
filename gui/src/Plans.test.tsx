// Component tests of the plan tabs: the theme pack screen (spec 04 section 8), with no "含想要" mark (#739), its filters,
// badges and weights typed in place, and for every plan tab which teams use a plan and how a deleted one comes back (#679).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, onTestFinished, test, vi } from "vitest";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import { TEXT, fill } from "./i18n";
import {
  GIFT_KEYWORDS, GRACES, SINNERS, defaultGorder, defaultStarlight, newSettings, newTeam, type GiftList, type Settings,
} from "./model";
import css from "./index.css?raw";
import { DeploymentTab } from "./Deployment";
import { StarlightTab } from "./Starlight";
import { ThemePackTab } from "./ThemePacks";
import { cssRules, cssValueOf, expectLines, filterEffect, pickInList, renderEditor, textOf } from "./testing";

const zh = TEXT.zh_tw;
const mine = (want: number[]): GiftList => ({
  id: "mine", name: "Mine", order: [...GIFT_KEYWORDS], want, keep: [], gorder: defaultGorder(), fusion_condition: "any",
});
const settings = (patch: Partial<Settings> = {}): Settings => ({ ...newSettings(), language: "zh_tw", ...patch });

const chipNamed = async (pack: string) => (await screen.findByText(pack, { selector: ".nm" })).closest(".pk") as HTMLElement;

// #739: the plan screen shows nothing of what the gift lists want (the user, 2026-11-14: the two are not directly related,
// and a mark for it confuses). A team of the default plan wants The Outcast's first own gift; the default list's materials
// of 9780 are LCB Regular Check-up's (what #421 marked).
describe("no 含想要 on the theme pack plan screen", () => {
  const PACKS = ["The Outcast", "LCB Regular Check-up"]; // a wanted own gift, and the default list's materials
  const wanting = () => {
    const team = { ...newTeam(1, "T1"), gift_list: "mine", theme_pack_plan: "default" };
    return settings({ gift_lists: [mine([recipes.pack_gifts["1002"][0]])], teams: [team] });
  };

  test("no dot on a pack, no key line and no wanted gifts on hover", async () => {
    renderEditor(<ThemePackTab />, wanting());
    for (const pack of PACKS) {
      const chip = await chipNamed(pack);
      expect(within(chip).queryByRole("img", { name: "含想要" })).toBeNull();
      expect(chip).not.toHaveAttribute("title"); // its name is on it: nothing to show on hover
    }
    expect(document.body).not.toHaveTextContent("含想要");
  });

  test("in picture mode a pack's hover is its name alone", async () => {
    const r = renderEditor(<ThemePackTab />, wanting());
    await r.user.click(await screen.findByRole("button", { name: zh["packs.images"] }));
    for (const pack of PACKS) {
      expect(screen.getByRole("img", { name: pack }).closest(".pk")).toHaveAttribute("title", pack);
    }
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
  const plan = (weights: Record<string, number> = { "The Outcast": -1 }) =>
    ({ id: "p1", name: "Mine", weights, threshold: 0, unlisted: 0, event_packs: "weight" });
  /** The theme pack tab on plan Mine (lanes 0 and -1 unless `p` says otherwise); window.prompt only counts calls. */
  async function open(p = plan()) {
    const asked = vi.spyOn(window, "prompt").mockReturnValue(null);
    onTestFinished(() => asked.mockRestore());
    const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [p] }));
    await r.user.click(await screen.findByText("Mine"));
    return { ...r, asked, weights: () => r.settings().theme_pack_plans[0].weights };
  }
  const chipOf = async (name: string) => (await screen.findByText(name, { selector: ".nm" })).closest(".pk") as HTMLElement;
  const box = () => screen.getByRole("spinbutton", { name: zh["packs.weightPrompt"] });
  /** The + lanes, the one above the lanes and the one below, while neither has a box open. */
  const addLanes = () => screen.getAllByText(new RegExp(zh["packs.newLane"])).map((x) => x.closest(".lane")!);
  /** Drag the pack `name` onto `lane`. */
  const dropOn = async (lane: Element, name: string) => {
    const dataTransfer = { setData() {}, effectAllowed: "", dropEffect: "" };
    const chip = await chipOf(name);
    fireEvent.dragStart(chip, { dataTransfer });
    fireEvent.dragOver(lane, { dataTransfer });
    fireEvent.drop(lane, { dataTransfer });
    fireEvent.dragEnd(chip, { dataTransfer });
  };

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

  // #739: a score typed is not lost when the box loses the focus (the user, 2026-11-14).
  test("a score typed and the focus moved away keeps it, as Enter does, on a pack and in a + lane", async () => {
    const r = await open();
    const search = screen.getByRole("searchbox", { name: zh["packs.search"] });
    await r.user.click(await chipOf("The Forgotten"));
    await r.user.keyboard("3"); // over the selected 0
    await r.user.click(search);
    expect(r.weights()["The Forgotten"]).toBe(3);
    expect(screen.queryByRole("spinbutton")).toBeNull();
    await dropOn(addLanes()[1], "Flat-broke Gamblers");
    await r.user.keyboard("-6");
    await r.user.click(search);
    expect(r.weights()["Flat-broke Gamblers"]).toBe(-6);
  });

  test("a click on another pack keeps the score typed into the first, then opens the second's box", async () => {
    const r = await open();
    await r.user.click(await chipOf("The Forgotten"));
    await r.user.keyboard("3");
    await r.user.click(await chipOf("Flat-broke Gamblers"));
    expect(r.weights()["The Forgotten"]).toBe(3);
    expect(within(await chipOf("Flat-broke Gamblers")).getByRole("spinbutton")).toHaveFocus();
    await r.user.keyboard("{Escape}");
    expect(r.weights()).toEqual({ "The Outcast": -1, "The Forgotten": 3 });
  });

  test("the pack pressed opens though the chips moved before the button came up", async () => {
    // Keeping the first score moves its pack to another lane, and the packs after it close up before a person's click ends:
    // the press starts on Flat-broke Gamblers, and the button comes up over the pack now in its place.
    const r = await open();
    await r.user.click(await chipOf("The Forgotten"));
    await r.user.keyboard("3");
    await r.user.pointer([{ keys: "[MouseLeft>]", target: await chipOf("Flat-broke Gamblers") }, { keys: "[/MouseLeft]", target: await chipOf("The Unloving") }]);
    expect(r.weights()["The Forgotten"]).toBe(3);
    expect(within(await chipOf("Flat-broke Gamblers")).getByRole("spinbutton")).toHaveFocus();
  });

  test("a press on another pack while a box is open drags nothing, and its release opens that pack", async () => {
    // Keeping the first score moves packs between the press and the drag, which would start from whatever is now under the
    // press: while a box is open a press is a click.
    const r = await open();
    await r.user.click(await chipOf("The Forgotten"));
    await r.user.keyboard("3");
    const chip = await chipOf("Flat-broke Gamblers");
    await r.user.pointer({ keys: "[MouseLeft>]", target: chip });
    await dropOn((await chipOf("The Outcast")).closest(".lane")!, "Flat-broke Gamblers");
    expect(r.weights()).toEqual({ "The Outcast": -1, "The Forgotten": 3 });
    expect(screen.queryByRole("spinbutton")).toBeNull();
    await r.user.pointer({ keys: "[/MouseLeft]", target: chip });
    expect(within(chip).getByRole("spinbutton")).toHaveFocus();
    await r.user.keyboard("{Escape}");
    await dropOn((await chipOf("The Outcast")).closest(".lane")!, "Flat-broke Gamblers"); // no box open: it drags
    expect(r.weights()["Flat-broke Gamblers"]).toBe(-1);
  });

  test("a right press on another pack keeps the first score and opens nothing", async () => {
    const r = await open();
    await r.user.click(await chipOf("The Forgotten"));
    await r.user.keyboard("3");
    await r.user.pointer({ keys: "[MouseRight]", target: await chipOf("Flat-broke Gamblers") });
    expect(r.weights()["The Forgotten"]).toBe(3);
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  test("leaving the box untouched, empty or with a score out of range closes it with the weight as it was and no warning", async () => {
    const r = await open();
    const search = screen.getByRole("searchbox", { name: zh["packs.search"] });
    for (const typed of ["", "{Backspace}", "11", "11{Enter}"]) {
      await r.user.click(await chipOf("The Outcast"));
      if (typed) await r.user.keyboard(typed);
      await r.user.click(search);
      expect(screen.queryByRole("spinbutton"), typed).toBeNull();
      expect(screen.queryByText(zh["packs.weightRange"]), typed).toBeNull();
      expect(r.weights(), typed).toEqual({ "The Outcast": -1 });
    }
    await dropOn(addLanes()[0], "The Forgotten"); // its box opens on +1, left as it is: no new lane
    await r.user.click(search);
    expect(r.weights()).toEqual({ "The Outcast": -1 });
    expect([...document.querySelectorAll(".lane:not(.add) .w")].map((w) => w.textContent)).toEqual(["0", "-1"]);
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
    const [, lane] = addLanes();
    await dropOn(lane, "The Forgotten");
    expect(lane).toContainElement(box());
    await r.user.keyboard("-3{Enter}");
    expect(r.weights()["The Forgotten"]).toBe(-3);
    expect(r.asked).not.toHaveBeenCalled();
  });

  test("a + above the lanes takes a pack too, so a score higher than every lane needs no drag past the list (#720)", async () => {
    const r = await open();
    const [top, bottom] = addLanes();
    const scored = [...document.querySelectorAll(".lane:not(.add)")];
    expect(top.compareDocumentPosition(scored[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(bottom.compareDocumentPosition(scored[scored.length - 1]) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    await dropOn(top, "The Forgotten");
    expect(top).toContainElement(box());
    expect(bottom).not.toContainElement(box());
    await r.user.keyboard("4{Enter}");
    expect(r.weights()["The Forgotten"]).toBe(4);
    expect(document.querySelector(".lane:not(.add) .w")).toHaveTextContent("+4");
  });

  test("a + lane's box opens on the score past every lane, selected, so a number typed replaces it (#734)", async () => {
    const r = await open(); // lanes 0 and -1
    await dropOn(addLanes()[0], "The Forgotten");
    expect(box()).toHaveFocus();
    expect(box()).toHaveValue(1); // the highest, 0, + 1
    await r.user.keyboard("4{Enter}"); // 14 if the 1 were not selected: out of range
    expect(r.weights()["The Forgotten"]).toBe(4);
    await dropOn(addLanes()[1], "Flat-broke Gamblers"); // lanes 4, 0 and -1 now
    expect(box()).toHaveValue(-2); // the lowest, -1, - 1
    await r.user.keyboard("-7{Enter}"); // -2-7 if the -2 were not selected
    expect(r.weights()["Flat-broke Gamblers"]).toBe(-7);
  });

  test("Enter keeps the prefilled score; a plan with no score yet offers +1 above and -1 below its one lane, 0 (#734)", async () => {
    const r = await open(plan({}));
    await dropOn(addLanes()[0], "The Forgotten");
    expect(box()).toHaveValue(1);
    await r.user.keyboard("{Escape}");
    await dropOn(addLanes()[1], "The Forgotten");
    expect(box()).toHaveValue(-1);
    await r.user.keyboard("{Enter}");
    expect(r.weights()).toEqual({ "The Forgotten": -1 });
  });

  test("past the -10..10 range the prefill stops at its end, a score Enter keeps (#734)", async () => {
    const r = await open(plan({ "The Forgotten": 10, "The Outcast": -10 }));
    await dropOn(addLanes()[0], "Flat-broke Gamblers");
    expect(box()).toHaveValue(10);
    await r.user.keyboard("{Escape}");
    await dropOn(addLanes()[1], "Flat-broke Gamblers");
    expect(box()).toHaveValue(-10);
    await r.user.keyboard("{Enter}"); // into the -10 lane there already is
    expect(r.weights()["Flat-broke Gamblers"]).toBe(-10);
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

test("the deployment order plan's grid shows each sinner's default identity card (#718), lit as the formation screen's (#750)", () => {
  const order = ["Ryōshū", "Yi Sang", "Faust", "Hong Lu", "Ishmael", "Rodion", "Outis", "Heathcliff", "Sinclair"];
  renderEditor(<DeploymentTab />, settings({ deployment_order_plans: [{ id: "p", name: "P", order }] }));
  const tile = (name: string) => within(document.querySelector<HTMLElement>(".sinners")!).getByRole("button", { name: new RegExp(name) });
  const artLook = (name: string) => filterEffect(cssValueOf(css, tile(name).querySelector("img")!, "filter"));
  expect(tile("Gregor")).toHaveClass("out");
  expect(tile("Ryōshū")).not.toHaveClass("out");
  expect(tile("Ryōshū").querySelector("img")?.getAttribute("src")).toMatch(/sinner_cards\/10401\.webp$/); // Ryōshū's LCB Sinner
  expect(tile("Gregor").querySelector("img")?.getAttribute("src")).toMatch(/sinner_cards\/11201\.webp$/);
  // the game's selected art at 0.42-0.48 of its light (blue 0.36-0.43), a card left out grey at full light
  // (tests/screens/Formation.png, #744)
  for (const s of ["Ryōshū", "Sinclair"]) {
    expect(artLook(s).light).toBeGreaterThanOrEqual(0.4);
    expect(artLook(s).light).toBeLessThanOrEqual(0.5);
  }
  expect(artLook("Gregor")).toEqual({ light: 1, colour: 0 });
});

describe("deleting a plan", () => {
  test("can be undone: the plan comes back in its place, in the editor", async () => {
    const plans = ["D1", "D2", "D3"].map((name) => ({ id: name.toLowerCase(), name, order: [...SINNERS] }));
    const r = renderEditor(<DeploymentTab />, settings({ deployment_order_plans: plans }));
    await pickInList(r.user, "D2");
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
    await pickInList(r.user, "D2");
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
  expect(pick).toHaveAccessibleDescription(new RegExp(textOf(GRACES[0].effects.zh.base[0]).replace(/[+()]/g, "\\$&")));
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

// #719, #733: a card reads as the game's does at each level. The expected titles, prices and yellow text are the game's own
// (its starlight page at + and ++, captures of 2026-11-13); the yellow comes from the game's text markup (graces.json).
describe("a grace card at each level", () => {
  /** The starlight tab on one plan whose grace n is at levels[n]; the others unselected. */
  const show = (levels: Record<number, string>) => {
    const plan = { id: "s1", name: "Plan", ...defaultStarlight() };
    for (const [n, level] of Object.entries(levels)) plan.levels[+n - 1] = level;
    return renderEditor(<StarlightTab />, settings({ starlight_plans: [plan] }));
  };
  const card = (n: number) => screen.getByRole("group", { name: GRACES[n - 1].zh });
  const marked = (n: number) => [...card(n).querySelectorAll("mark")].map((m) => m.textContent);
  /** A card's price: the game's starlight icon (a "★" the icon covers, so a screen reader still says it) and the number. */
  const price = (n: number) => card(n).querySelector(".price");

  test("at + the title gains a +, the price doubles, the + effects show and the values that changed are marked", () => {
    show({ 1: "plus" });
    expect(within(card(1)).getByText("起始之星+")).toBeInTheDocument();
    // the pick button's name is the title it shows, so a voice command can say it (WCAG 2.5.3)
    expect(within(card(1)).getByRole("button", { name: "起始之星+" })).toHaveAttribute("aria-pressed", "true");
    expect(price(1)).toHaveTextContent(/^★ 20$/);
    expect([...card(1).querySelectorAll("li")].map((li) => li.textContent)).toEqual(GRACES[0].effects.zh.plus!.map(textOf));
    expect(marked(1)).toEqual(["+250"]);
  });

  test("at ++ a line the game prints yellow is marked whole, and of (最多+9) only the 9", () => {
    show({ 7: "plus2" });
    expect(within(card(7)).getByText("星雲的寵愛++")).toBeInTheDocument();
    expect(price(7)).toHaveTextContent(/^★ 120$/);
    expect(marked(7)).toEqual(["進入第6層時，人格等級 +3", "9"]);
  });

  test("a count is marked with its unit, as the game marks it", () => {
    show({ 1: "plus2", 6: "plus" });
    expect(marked(1)).toEqual(["+250", "2次"]);
    expect(marked(6)).toEqual(["2件", "特殊商店出現機率 +10%"]);
  });

  test("at + Chance Comet marks its new detail lines, indented, the floor it adds and 所選關鍵詞, not the 的 after it", () => {
    show({ 9: "plus" });
    const lines = [...card(9).querySelectorAll("li")];
    expect(lines[0]).toHaveTextContent("進入商店時，獲得1件合成·售賣專用飾品");
    expect(lines[0].querySelector("mark")).toBeNull();
    expect(lines.filter((li) => li.classList.contains("sub")).map((li) => li.textContent)).toEqual(["· 第5層及以下：1~3級", "· 第6層及以上：2~3級"]);
    expect(marked(9)).toEqual(["· 第5層及以下：1~3級", "· 第6層及以上：2~3級", "與第5層", "所選關鍵詞"]);
  });

  test("at ++ Chance Comet marks 第5層與第7層 without the 、 before it, 所選關鍵詞 and 4級 apart", () => {
    show({ 9: "plus2" });
    expect(within(card(9)).getAllByRole("listitem")[3]).toHaveTextContent("進入第3層、第5層與第7層時，隨機獲得1件所選關鍵詞的4級飾品");
    expect(marked(9)).toEqual(["· 第5層及以下：2~3級", "· 第6層及以上：3~4級", "第5層與第7層", "所選關鍵詞", "4級", "1級"]);
  });

  test("at + and ++ All-round Possibility marks 選擇獲得 with the count, not the count alone", () => {
    show({ 10: "plus" });
    expect(marked(10)).toEqual(["選擇獲得2件", "微茫的殘影"]);
    cleanup();
    show({ 10: "plus2" });
    expect(marked(10)).toEqual(["選擇獲得3件", "微茫的殘影、閃耀的殘影"]);
  });

  test("unselected and at base a card keeps its plain title, the base price and the base text; its pick button says which", () => {
    show({ 2: "base" });
    for (const n of [1, 2]) {
      expect(within(card(n)).getByText(GRACES[n - 1].zh)).toBeInTheDocument();
      expect(price(n)).toHaveTextContent(/^★ 10$/);
      expect([...card(n).querySelectorAll("li")].map((li) => li.textContent)).toEqual(GRACES[n - 1].effects.zh.base.map(textOf));
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

  test("the price and the total wear the game's starlight icon over their ★", () => {
    show({ 1: "plus" });
    expect(price(1)?.querySelector(".star")).toHaveTextContent(/^★$/);
    expect(screen.getByText(zh["starlight.total"]).querySelector("b .star")).toHaveTextContent(/^★$/);
  });

  test("+ and ++ draw the game's + glyph once and twice, on each card and in Enhance All, lit or not", () => {
    show({ 1: "plus", 2: "plus2" });
    for (const n of [1, 2, 3]) {
      const [, plus, plus2] = within(card(n)).getAllByRole("button");
      expect(plus.querySelectorAll(".glyph")).toHaveLength(1);
      expect(plus2.querySelectorAll(".glyph")).toHaveLength(2);
    }
    expect(screen.getByRole("button", { name: `${zh["starlight.enhanceAll"]} +` }).querySelectorAll(".glyph")).toHaveLength(1);
    expect(screen.getByRole("button", { name: `${zh["starlight.enhanceAll"]} ++` }).querySelectorAll(".glyph")).toHaveLength(2);
  });

  // #726: the card face, its selected and hover frames, the + / ++ plate lit and unlit, the glyphs, the price icon, the Enhance
  // All panel and the page are the game's own sprites (tools/grace_icons.py), each drawn for its own state.
  test("each state draws the game's own texture for it, and the page draws every texture the tool writes", () => {
    const rules = cssRules(css);
    const drawn = (selector: string) => rules.filter((r) => r.selector.split(",").map((x) => x.trim()).includes(selector))
      .flatMap((r) => [...r.body.matchAll(/grace_card\/([\w-]+)\.webp/g)].map((m) => m[1]));
    const states: [string, string][] = [
      [".starlight", "page"], [".grace::before", "face"], [".grace:not(.none)::before", "face-picked"], [".grace::after", "hover"],
      [".grace .enhance button", "button"], ['.grace .enhance button[aria-pressed="true"]', "button-lit"],
      [".grace-side button", "button"], ['.grace-side button[aria-pressed="true"]', "button-lit"],
      [".starlight .glyph", "plus"], ['.starlight button[aria-pressed="true"] .glyph', "plus-lit"],
      [".starlight .star", "star"], [".grace-side", "side"],
    ];
    for (const [selector, file] of states) expect(drawn(selector), selector).toEqual([file]);
    const written = Object.keys(import.meta.glob("./grace_card/*.webp")).map((f) => f.replace(/^.*\/|\.webp$/g, ""));
    expect(written.sort()).toEqual([...new Set(states.map(([, file]) => file))].sort());
  });

  // The longest title, "傾落的流星雨++" (6 characters and "++", about 7.2 em), sits right of the icon's bracket, in 55 % of the
  // card's width (the face's band from 145 to 356 of 380 px): at 6.8 % of the width per em it takes 49 %, on one line. Below
  // 191 px the font stops at 13 px, so no column is narrower than 216 px (#726; 144 px before, and two lines). A title wider
  // than its band takes --fit instead (#751): Starlight.test.tsx tests the size, the real window the fit.
  test("a card is wide enough for its longest title on one line", () => {
    const cols = cssRules(css).filter((r) => r.selector === ".graces").map((r) => r.body.match(/minmax\((\d+)px/)?.[1]);
    expect(cols.length).toBeGreaterThan(0);
    for (const px of cols) expect(Number(px)).toBeGreaterThanOrEqual(216);
    const title = cssRules(css).find((r) => r.selector === ".grace .title")?.body ?? "";
    expect(title).toMatch(/font-size:\s*var\(--fit,\s*clamp\(13px,\s*6\.8cqw/);
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
