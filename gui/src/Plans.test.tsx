// Component tests of the theme pack plan screen's "含想要" mark (#421, spec 04 section 8): which packs carry it and what its
// tooltip lists, for the list the teams using the plan hold.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import { GIFT_BY_ID } from "./giftCatalog";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, defaultGorder, newSettings, newTeam, type GiftList, type Settings } from "./model";
import { ThemePackTab } from "./Plans";
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

test("a plan's hint and the event pack note show one topic to a line", async () => {
  const plan = { id: "p1", name: "Mine", weights: {}, threshold: 0, unlisted: 0, event_packs: "weight" };
  const r = renderEditor(<ThemePackTab />, settings({ theme_pack_plans: [plan] }));
  await r.user.click(await screen.findByText("Mine"));
  await screen.findByText(zh["packs.eventPacks"]);
  expectLines(zh["packs.hint"]);
  expectLines(zh["packs.eventPacksNote"]);
});
