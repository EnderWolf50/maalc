// Several theme packs picked and moved at once on the theme pack plan screen (#743): Ctrl or Shift with a click, Space, or a box
// drawn from empty space picks packs; a drag, Alt+↑/↓ or a weight typed on one of them moves every pick. A single pack's click,
// drag and box stay as they were (Plans.test.tsx).
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, onTestFinished, test, vi } from "vitest";
import { TEXT, fill } from "./i18n";
import { GROUP_MIN, newSettings, packZh, type Settings, type ThemePackPlan } from "./model";
import { ThemePackTab } from "./ThemePacks";
import { PACK_EN, dragHeld, dragOnto, englishOf, pickInList, renderEditor } from "./testing";

const zh = TEXT.zh_tw;
// The data file's first packs, in the order the 0 lane shows them (theme_packs.yaml): The Outcast sits in the -1 lane.
const FIRST = ["The B.E.", "The Forgotten", "Flat-broke Gamblers", "Automated Factory", "The Unloving", "Nagel und Hammer"];

const planOf = (weights: Record<string, number> = { "The Outcast": -1 }, id = "p1", name = "Mine"): ThemePackPlan =>
  ({ id, name, weights, threshold: 0, unlisted: 0, event_packs: "weight" });
const settings = (plans: ThemePackPlan[]): Settings => ({ ...newSettings(), language: "zh_tw", theme_pack_plans: plans });

async function open(plans = [planOf()]) {
  const r = renderEditor(<ThemePackTab />, settings(plans));
  await pickInList(r.user, plans[0].name);
  return { ...r, weights: () => r.settings().theme_pack_plans[0].weights, plan: () => r.settings().theme_pack_plans[0] };
}

// The Chinese UI shows each pack's Chinese name with its English one under it (#899): a pack goes by its English name here.
const chipOf = (name: string) => screen.getByText(name, { selector: PACK_EN }).closest(".pk") as HTMLElement;
const laneOf = (name: string) => chipOf(name).closest(".lane") as HTMLElement;
const laneAt = (w: string) => [...document.querySelectorAll(".lane:not(.add)")].find((l) => l.querySelector(".w")!.textContent === w) as HTMLElement;
const picked = () => [...document.querySelectorAll(".pk[aria-pressed='true'] .nm")].map(englishOf);
const bar = () => document.querySelector(".pickbar") as HTMLElement;
const box = () => screen.getByRole("spinbutton", { name: zh["packs.weightPrompt"] });
const said = () => document.querySelector(".lanes ~ [aria-live]")!.textContent;
const lanes = () => document.querySelector(".lanes") as HTMLElement;
const addLanes = () => screen.getAllByText(new RegExp(zh["packs.newLane"])).map((x) => x.closest(".lane")!);

async function ctrlClick(user: ReturnType<typeof renderEditor>["user"], ...packs: (string | Element)[]) {
  await user.keyboard("{Control>}");
  for (const p of packs) await user.click(typeof p === "string" ? chipOf(p) : p);
  await user.keyboard("{/Control}");
}

describe("picking packs with the mouse", () => {
  test("Ctrl and a click pick a pack without opening its box; a second one unpicks it", async () => {
    const r = await open();
    expect(bar()).toHaveTextContent(zh["packs.pickHint"]);
    await ctrlClick(r.user, "The Forgotten", "The Unloving");
    expect(picked()).toEqual(["The Forgotten", "The Unloving"]);
    expect(chipOf("The Forgotten")).toHaveClass("picked");
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(bar()).toHaveTextContent(fill(zh["packs.picked"], { n: 2 }));
    expect(said()).toBe(fill(zh["packs.picked"], { n: 2 }));
    await ctrlClick(r.user, "The Forgotten");
    expect(picked()).toEqual(["The Unloving"]);
    expect(chipOf("The Forgotten")).not.toHaveClass("picked");
  });

  test("Shift and a click pick the range of a lane between the last pack clicked and this one, in the order the lane shows", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1]);
    await r.user.keyboard("{Shift>}");
    await r.user.click(chipOf(FIRST[4]));
    await r.user.keyboard("{/Shift}");
    expect(picked()).toEqual(FIRST.slice(1, 5));
    // a pack of another lane starts no run: it is picked alone, added to the picks
    await r.user.keyboard("{Shift>}");
    await r.user.click(chipOf("The Outcast"));
    await r.user.keyboard("{/Shift}");
    expect(picked()).toEqual([...FIRST.slice(1, 5), "The Outcast"]);
  });

  test("a plain click starts a Shift click's range too: its box closes and the range from it is picked", async () => {
    const r = await open();
    await r.user.click(chipOf(FIRST[1]));
    expect(chipOf(FIRST[1])).toContainElement(box());
    await r.user.keyboard("{Shift>}");
    await r.user.click(chipOf(FIRST[3]));
    await r.user.keyboard("{/Shift}");
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(picked()).toEqual(FIRST.slice(1, 4));
    expect(r.weights()).toEqual({ "The Outcast": -1 });
  });

  test("a range starts only from a pack of this plan: in another plan Shift and a click pick the pack alone", async () => {
    const r = await open([planOf(), planOf({}, "p2", "Yours")]);
    await ctrlClick(r.user, FIRST[1]);
    await pickInList(r.user, "Yours");
    await r.user.keyboard("{Shift>}");
    await r.user.click(chipOf(FIRST[4]));
    await r.user.keyboard("{/Shift}");
    expect(picked()).toEqual([FIRST[4]]);
  });

  test("a plain click on a pack not picked drops the picks and types that pack's weight alone, as before", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], FIRST[2]);
    await r.user.click(chipOf(FIRST[3]));
    expect(picked()).toEqual([]);
    await r.user.keyboard("3{Enter}");
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[3]]: 3 });
  });

  test("a click on a picked pack opens its box, and the weight typed there goes to every pick; the picks stay", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], FIRST[2], "The Outcast");
    await r.user.click(chipOf(FIRST[2]));
    expect(chipOf(FIRST[2])).toContainElement(box());
    expect(box()).toHaveValue(0); // the weight of the pack clicked
    await r.user.keyboard("5{Enter}");
    expect(r.weights()).toEqual({ "The Outcast": 5, [FIRST[1]]: 5, [FIRST[2]]: 5 });
    expect(picked()).toEqual([FIRST[1], "The Outcast", FIRST[2]]); // in the +5 lane now, in the data file's order
    expect(said()).toBe(fill(zh["packs.moved"], { n: 3, w: "+5" }));
  });

  test("取消選取 on the bar drops the picks, and the bar keeps its height: it shows the hint again", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1]);
    await r.user.click(within(bar()).getByRole("button", { name: zh["packs.unpick"] }));
    expect(picked()).toEqual([]);
    expect(bar()).toHaveTextContent(zh["packs.pickHint"]);
    expect(said()).toBe(zh["packs.unpicked"]);
  });
});

describe("dragging picked packs", () => {
  test("a drag of any picked pack moves every pick to the lane it is dropped on; the picks stay", async () => {
    const r = await open();
    await ctrlClick(r.user, ...FIRST.slice(1, 5));
    dragOnto(chipOf(FIRST[3]), laneOf("The Outcast"));
    expect(r.weights()).toEqual({ "The Outcast": -1, ...Object.fromEntries(FIRST.slice(1, 5).map((n) => [n, -1])) });
    expect(laneOf(FIRST[0])).toBe(laneAt("0"));
    expect(picked()).toEqual(FIRST.slice(1, 5));
    expect(said()).toBe(fill(zh["packs.moved"], { n: 4, w: "-1" }));
  });

  test("while held, the other picks are dimmed, the pack held shows their count and the lane under it says where they go", async () => {
    const r = await open();
    await ctrlClick(r.user, ...FIRST.slice(1, 5));
    const held = dragHeld(chipOf(FIRST[3]), laneAt("-1"));
    expect(FIRST.slice(0, 5).map((n) => chipOf(n).classList.contains("lifted"))).toEqual([false, true, true, false, true]);
    expect(within(chipOf(FIRST[3])).getByText("4")).toHaveClass("count");
    expect(laneAt("-1")).toHaveClass("lit");
    expect(laneAt("-1")).toHaveTextContent(fill(zh["packs.drop"], { n: 4, w: "-1" }));
    expect(laneAt("0")).not.toHaveClass("lit");
    held.leave();
    expect(laneAt("-1")).not.toHaveClass("lit");
    held.end();
    expect(document.querySelector(".lifted, .count")).toBeNull();
  });

  test("a drag of a pack not picked moves it alone and drops the picks; a single drag shows no count and lights no lane", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], FIRST[2]);
    const held = dragHeld(chipOf(FIRST[4]), laneAt("-1"));
    expect(document.querySelector(".lifted, .count, .lane.lit")).toBeNull();
    held.end();
    dragOnto(chipOf(FIRST[4]), laneAt("-1"));
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[4]]: -1 });
    expect(picked()).toEqual([]);
  });

  test("dropped on a + lane, the picks take the weight typed there", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], FIRST[2]);
    const [, bottom] = addLanes();
    dragOnto(chipOf(FIRST[1]), bottom);
    expect(bottom).toContainElement(box());
    expect(bottom).toHaveTextContent(fill(zh["packs.many"], { n: 2 }));
    expect(box()).toHaveValue(-2);
    await r.user.keyboard("-3{Enter}");
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[1]]: -3, [FIRST[2]]: -3 });
  });

  test("the unlisted packs' chip moves with the picks", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], zh["packs.unlisted"]);
    dragOnto(chipOf(FIRST[1]), laneAt("-1"));
    expect(r.plan().unlisted).toBe(-1);
    expect(r.weights()[FIRST[1]]).toBe(-1);
  });
});

describe("picking and moving packs from the keyboard", () => {
  test("Space picks the focused pack and Enter opens it, so a weight typed goes to every pick", async () => {
    const r = await open();
    chipOf(FIRST[1]).focus();
    await r.user.keyboard(" ");
    expect(picked()).toEqual([FIRST[1]]);
    await r.user.tab();
    expect(chipOf(FIRST[2])).toHaveFocus();
    await r.user.keyboard(" ");
    expect(picked()).toEqual([FIRST[1], FIRST[2]]);
    expect(screen.queryByRole("spinbutton")).toBeNull(); // Space no longer opens the box
    await r.user.keyboard(" ");
    expect(picked()).toEqual([FIRST[1]]); // and a second Space unpicks
    await r.user.keyboard(" {Enter}");
    expect(chipOf(FIRST[2])).toContainElement(box());
    await r.user.keyboard("2{Enter}");
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[1]]: 2, [FIRST[2]]: 2 });
  });

  test("Alt+↑ and Alt+↓ move every pick a lane, the focus stays on the pack, and past the end a new lane opens", async () => {
    const r = await open(); // lanes 0 and -1
    await ctrlClick(r.user, FIRST[1], FIRST[2]);
    chipOf(FIRST[2]).focus();
    await r.user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[1]]: -1, [FIRST[2]]: -1 });
    expect(chipOf(FIRST[2])).toHaveFocus();
    expect(said()).toBe(fill(zh["packs.moved"], { n: 2, w: "-1" }));
    await r.user.keyboard("{Alt>}{ArrowDown}{/Alt}"); // -1 is the lowest lane: a new one below it
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[1]]: -2, [FIRST[2]]: -2 });
    await r.user.keyboard("{Alt>}{ArrowUp}{ArrowUp}{ArrowUp}{/Alt}"); // -1, 0, then a new +1 above
    expect(r.weights()).toEqual({ "The Outcast": -1, [FIRST[1]]: 1, [FIRST[2]]: 1 });
    expect(chipOf(FIRST[2])).toHaveFocus();
    expect(picked()).toEqual([FIRST[1], FIRST[2]]);
  });

  test("Alt+↑ on a pack not picked moves it alone; at +10 there is no lane above to open", async () => {
    const r = await open([planOf({ "The Outcast": 10 })]);
    await ctrlClick(r.user, FIRST[1]);
    chipOf(FIRST[2]).focus();
    await r.user.keyboard("{Alt>}{ArrowUp}{/Alt}");
    expect(r.weights()).toEqual({ "The Outcast": 10, [FIRST[2]]: 10 });
    expect(picked()).toEqual([FIRST[1]]);
    chipOf(FIRST[2]).focus();
    await r.user.keyboard("{Alt>}{ArrowUp}{/Alt}");
    expect(r.weights()).toEqual({ "The Outcast": 10, [FIRST[2]]: 10 });
  });

  test("Esc drops the picks from anywhere on the page but a field, where it does the field's own work", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], FIRST[2]);
    await r.user.click(chipOf(FIRST[1]));
    await r.user.keyboard("{Escape}"); // closes the box, the picks stay
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(picked()).toEqual([FIRST[1], FIRST[2]]);
    (document.activeElement as HTMLElement | null)?.blur();
    await r.user.keyboard("{Escape}");
    expect(picked()).toEqual([]);
  });
});

describe("a box drawn from empty space in the lanes", () => {
  /** Lay the lanes out as a window would (jsdom has no layout): the lanes at the page's top left, the 0 lane's first packs in a
   * row 100 px apart at y 100, The Outcast at y 200; anything else, no box. */
  function layOut() {
    const at = new Map<string, [number, number]>([...FIRST.map((n, i): [string, [number, number]] => [n, [60 + 100 * i, 100]]), ["The Outcast", [60, 200]]]);
    const rect = (x: number, y: number, w: number, h: number) => ({ x, y, left: x, top: y, width: w, height: h, right: x + w, bottom: y + h, toJSON() {} }) as DOMRect;
    const spy = vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      if (this.classList.contains("lanes")) return rect(0, 0, 1200, 800);
      const nm = this.querySelector(".nm");
      const name = nm && englishOf(nm);
      const xy = this.classList.contains("pk") && name ? at.get(name) : undefined;
      return xy ? rect(xy[0], xy[1], 90, 24) : rect(0, 0, 0, 0);
    });
    onTestFinished(() => spy.mockRestore());
  }
  const draw = (from: [number, number], to: [number, number], opts: { ctrlKey?: boolean; on?: Element } = {}) => {
    const on = opts.on ?? laneAt("0");
    fireEvent.pointerDown(on, { button: 0, pointerId: 1, clientX: from[0], clientY: from[1], ctrlKey: opts.ctrlKey });
    fireEvent.pointerMove(lanes(), { pointerId: 1, clientX: (from[0] + to[0]) / 2, clientY: (from[1] + to[1]) / 2 });
    fireEvent.pointerMove(lanes(), { pointerId: 1, clientX: to[0], clientY: to[1] });
    const shown = (document.querySelector(".marquee") as HTMLElement | null)?.style.cssText ?? null; // the box before the release
    fireEvent.pointerUp(lanes(), { pointerId: 1, clientX: to[0], clientY: to[1], ctrlKey: opts.ctrlKey });
    return shown;
  };

  test("picks every pack it touches, and replaces the picks without Ctrl", async () => {
    const r = await open();
    layOut();
    await ctrlClick(r.user, "The Outcast");
    const shown = draw([380, 90], [156, 110]); // right to left, over the 2nd, 3rd and 4th packs (x 160, 260 and 360)
    expect(shown).toBe("left: 156px; top: 90px; width: 224px; height: 20px;");
    expect(picked()).toEqual(FIRST.slice(1, 4));
    expect(document.querySelector(".marquee")).toBeNull();
    expect(said()).toBe(fill(zh["packs.picked"], { n: 3 }));
  });

  test("with Ctrl it adds to the picks", async () => {
    const r = await open();
    layOut();
    await ctrlClick(r.user, "The Outcast");
    draw([155, 90], [270, 110], { ctrlKey: true });
    expect(picked()).toEqual([FIRST[1], FIRST[2], "The Outcast"]);
  });

  test("a click on empty space drops the picks, but not with Ctrl", async () => {
    const r = await open();
    layOut();
    await ctrlClick(r.user, FIRST[1]);
    draw([700, 300], [701, 301], { ctrlKey: true });
    expect(picked()).toEqual([FIRST[1]]);
    draw([700, 300], [701, 301]);
    expect(picked()).toEqual([]);
  });

  test("a box may start on a group's title (#742): it is empty space, not a pack", async () => {
    const r = await open();
    layOut();
    await ctrlClick(r.user, "The Outcast");
    const title = laneAt("0").querySelector("section h3")!;
    expect(draw([155, 90], [270, 110], { on: title })).not.toBeNull();
    expect(picked()).toEqual([FIRST[1], FIRST[2]]);
  });

  test("a press on a pack or on the threshold line draws no box, so their own drags start as before", async () => {
    const r = await open();
    layOut();
    await ctrlClick(r.user, FIRST[1]);
    expect(draw([60, 100], [400, 300], { on: chipOf(FIRST[0]) })).toBeNull();
    expect(draw([60, 100], [400, 300], { on: document.querySelector(".thr span")! })).toBeNull();
    expect(picked()).toEqual([FIRST[1]]);
  });
});

// A lane of 20 packs or more shows them under difficulty titles (#742): the 0 lane here holds every pack but The Outcast.
describe("picks in a lane grouped by difficulty", () => {
  const BOTH = zh["packs.groupBoth"], HARD = zh["packs.groupHard"], EXTREME = zh["packs.groupExtreme"];
  /** The group of the lane with weight `w` whose title reads `title`. */
  const groupOf = (w: string, title: string) => [...laneAt(w).querySelectorAll("section")]
    .find((s) => s.querySelector("h3 .t")!.textContent === title) as HTMLElement;
  /** The packs of that group, in the order it shows them. */
  const packsOf = (w: string, title: string) => [...groupOf(w, title).querySelectorAll(".pk .nm")].map((n) => englishOf(n)!);
  const titleOf = (w: string, title: string) => groupOf(w, title).querySelector("h3") as HTMLElement;

  test("a Shift click's range runs on past a group's title, in the order the lane shows; the title is not picked", async () => {
    const r = await open();
    const both = packsOf("0", BOTH), hard = packsOf("0", HARD);
    const last = both[both.length - 1];
    await ctrlClick(r.user, last);
    await r.user.keyboard("{Shift>}");
    await r.user.click(chipOf(hard[1]));
    await r.user.keyboard("{/Shift}");
    expect(picked()).toEqual([last, hard[0], hard[1]]);
  });

  test("a click on a title picks nothing: with Ctrl the picks stay, without it they go, as on empty space", async () => {
    const r = await open();
    const both = packsOf("0", BOTH);
    await ctrlClick(r.user, both[0], both[1]);
    await ctrlClick(r.user, titleOf("0", HARD));
    expect(picked()).toEqual([both[0], both[1]]);
    await r.user.click(titleOf("0", HARD));
    expect(picked()).toEqual([]);
  });

  test("picks from two groups drag out together, and dropped on a title they go back to its lane, each under its own group", async () => {
    const r = await open();
    const [both, extreme] = [packsOf("0", BOTH)[0], packsOf("0", EXTREME)[0]];
    await ctrlClick(r.user, both, extreme);
    dragOnto(chipOf(extreme), laneAt("-1"));
    expect(r.weights()).toEqual({ "The Outcast": -1, [both]: -1, [extreme]: -1 });
    expect(picked()).toEqual([both, extreme]);
    const held = dragHeld(chipOf(both), titleOf("0", BOTH)); // the title is part of its lane's drop target, not one of its own
    expect(laneAt("0")).toHaveClass("lit");
    held.end();
    dragOnto(chipOf(both), titleOf("0", BOTH));
    expect(r.weights()).toEqual({ "The Outcast": -1, [both]: 0, [extreme]: 0 });
    expect(packsOf("0", BOTH)).toContain(both);
    expect(packsOf("0", EXTREME)).toContain(extreme);
  });

  test("Alt+↓ and Alt+↑ move picks of two groups out of the lane and back, the focus staying on the pack under its title", async () => {
    const r = await open();
    const [hard, extreme] = [packsOf("0", HARD)[0], packsOf("0", EXTREME)[0]];
    await ctrlClick(r.user, hard, extreme);
    chipOf(extreme).focus();
    await r.user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(r.weights()).toEqual({ "The Outcast": -1, [hard]: -1, [extreme]: -1 });
    expect(chipOf(extreme)).toHaveFocus();
    await r.user.keyboard("{Alt>}{ArrowUp}{/Alt}");
    expect(r.weights()).toEqual({ "The Outcast": -1, [hard]: 0, [extreme]: 0 });
    expect(chipOf(extreme)).toHaveFocus();
    expect(packsOf("0", HARD)).toContain(hard);
    expect(packsOf("0", EXTREME)).toContain(extreme);
    expect(picked()).toEqual([hard, extreme]);
  });
});

// #899 with #742 and #743: the Chinese names hold in a grouped lane, in the search that ungroups it and on what picks show.
describe("Chinese names in a grouped lane and on the picks", () => {
  const zhName = (en: string) => packZh(en, true)!;
  /** The name a chip's `.nm` shows first: in the Chinese UI its Chinese name, before the small English one. */
  const firstName = (nm: Element) => nm.firstChild!.textContent;
  const firstNameOf = (en: string) => firstName(chipOf(en).querySelector(".nm")!);
  /** Each chip of the 0 lane's groups as [the name it shows first, the small English one under it]. */
  const grouped = () => [...laneAt("0").querySelectorAll(".pg .pk .nm")].map((nm) => [firstName(nm), nm.querySelector(".en")?.textContent]);

  test("a grouped lane shows each pack's Chinese name, its English name under it", async () => {
    await open();
    expect(laneAt("0").querySelector(".packs")).toHaveClass("grouped");
    const names = grouped();
    expect(names.length).toBeGreaterThanOrEqual(GROUP_MIN);
    const english = names.map(([, en]) => en!);
    expect(english).toEqual(expect.arrayContaining(FIRST));
    expect(names).toEqual(english.map((en) => [zhName(en), en]));
  });

  test("a search by a Chinese name that leaves fewer than 20 packs shows the lane ungrouped, the pack still in Chinese", async () => {
    const r = await open();
    await r.user.type(screen.getByRole("searchbox", { name: zh["packs.search"] }), zhName("The Forgotten"));
    const packs = laneAt("0").querySelector(".packs")!;
    expect(packs).not.toHaveClass("grouped");
    expect(packs.querySelector("section")).toBeNull();
    expect(firstNameOf("The Forgotten")).toBe(zhName("The Forgotten"));
  });

  test("picks dragged as one are named in Chinese on the bar; the drop and ＋ hints count them", async () => {
    const r = await open();
    const picks = [FIRST[1], FIRST[4]];
    await ctrlClick(r.user, ...picks);
    expect(within(bar()).getByText(picks.map(zhName).join(zh["packs.floorSep"]))).toHaveClass("names");
    expect(picks.map(firstNameOf)).toEqual(picks.map(zhName));
    const held = dragHeld(chipOf(FIRST[1]), laneAt("-1"));
    expect(laneAt("-1")).toHaveTextContent(fill(zh["packs.drop"], { n: 2, w: "-1" }));
    held.end();
    const [top] = addLanes();
    dragOnto(chipOf(FIRST[4]), top);
    expect(top).toHaveTextContent(new RegExp(`^＋ ${fill(zh["packs.many"], { n: 2 })}$`));
  });

  test("the unlisted packs' chip is named by its label on the bar", async () => {
    const r = await open();
    await ctrlClick(r.user, FIRST[1], zh["packs.unlisted"]);
    expect(within(bar()).getByText([zhName(FIRST[1]), zh["packs.unlisted"]].join(zh["packs.floorSep"]))).toHaveClass("names");
  });
});

describe("what the picks hold", () => {
  test("only packs on screen: a search that hides a picked pack drops it, and clearing the search does not bring it back", async () => {
    const r = await open();
    await ctrlClick(r.user, "The Forgotten", "The Unloving");
    await r.user.type(screen.getByRole("searchbox", { name: zh["packs.search"] }), "forg");
    expect(bar()).toHaveTextContent(fill(zh["packs.picked"], { n: 1 }));
    await r.user.keyboard("{Escape}");
    expect(picked()).toEqual(["The Forgotten"]);
  });

  test("another plan starts with none", async () => {
    const r = await open([planOf(), planOf({}, "p2", "Yours")]);
    await ctrlClick(r.user, FIRST[1]);
    await pickInList(r.user, "Yours");
    expect(picked()).toEqual([]);
    await pickInList(r.user, "Mine");
    expect(picked()).toEqual([]);
  });

  test("the locked default plan picks nothing and shows no bar", async () => {
    const r = renderEditor(<ThemePackTab />, settings([]));
    await r.user.keyboard("{Control>}");
    await r.user.click(await screen.findByText(FIRST[1], { selector: PACK_EN }));
    await r.user.keyboard("{/Control}");
    expect(document.querySelector(".pickbar, .pk[aria-pressed]")).toBeNull();
  });
});
