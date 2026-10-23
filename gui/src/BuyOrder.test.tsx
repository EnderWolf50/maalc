// Component tests of the purchase order dialog and the drag-to-reorder of the gift list tab (#296): what the user sees and
// does, and what the list holds afterwards.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import recipes from "../../assets/resource/base/data/gift_recipes.json";
import { GIFT_BY_ID } from "./giftCatalog";
import { GiftListsTab } from "./GiftLists";
import { DEFAULT_LIST, queue } from "./gifts";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, SEARCH_GIFTS, defaultGorder, newSettings, type GiftList, type Settings } from "./model";
import { renderEditor } from "./testing";

const zh = TEXT.zh_tw;
const say = (s: string, vars: Record<string, string | number> = {}) => s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
const nameOf = (id: number) => GIFT_BY_ID.get(id)!.zh;
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const idsOf = (keyword: string, tier: number) => SEARCH_GIFTS.filter((g) => g.keyword === keyword && g.tier === tier).map((g) => g.id);

const burnFusion = recipes.gifts.find((g) => g.keyword === "Burn")!.id;
const [b1, b2, b3] = idsOf("Burn", 3), [l1, l2] = idsOf("Bleed", 3), [b2a] = idsOf("Burn", 2);
const REST = GIFT_KEYWORDS.filter((k) => k !== "Burn" && k !== "Bleed");
/** Burn first, then Bleed; three Burn gifts and two Bleed gifts wanted, so the buy queue is b1 b2 b3 l1 l2. */
const mine = (patch: Partial<GiftList> = {}): GiftList => ({
  id: "mine", name: "Mine", order: ["Burn", "Bleed", ...REST], want: [b1, b2, b3, l1, l2], keep: [], gorder: defaultGorder(), fusion_condition: "any", ...patch,
});

async function open(list: GiftList | null, language: Settings["language"] = "zh_tw") {
  const s: Settings = { ...newSettings(), language, gift_lists: list ? [list] : [] };
  const r = renderEditor(<GiftListsTab />, s);
  if (list) await r.user.selectOptions(screen.getByRole("combobox", { name: TEXT[language]["gl.list"] }), list.id);
  return r;
}
type Opened = Awaited<ReturnType<typeof open>>;
const held = (r: Opened) => r.settings().gift_lists[0];
const buyButton = () => screen.getByRole("button", { name: /^購買排序（\d+）/ });
const dialog = () => screen.getByRole("dialog", { name: zh["gl.buy_title"] });
async function openDialog(r: Opened) {
  await r.user.click(buyButton());
  return within(dialog());
}
/** The gift rows of the open dialog, in the order shown. */
const rows = () => within(dialog()).queryAllByRole("listitem");
const rowIds = () => rows().map((li) => Number(li.getAttribute("data-gift")));
const position = (li: HTMLElement) => Number(within(li).getByTitle(/\d+/).textContent);
/** The expand button of a keyword's section. */
const section = (k: string) => within(dialog()).getByRole("button", { name: new RegExp("^" + zh[`kw.${k}` as keyof typeof zh] + "第") });

const dt = () => ({ setData() {}, effectAllowed: "", dropEffect: "" });
/** What the browser fires for dragging `from` onto `to`. */
function drag(from: Element, to: Element) {
  fireEvent.dragStart(from, { dataTransfer: dt() });
  fireEvent.dragOver(to, { dataTransfer: dt() });
  fireEvent.drop(to, { dataTransfer: dt() });
  fireEvent.dragEnd(from, { dataTransfer: dt() });
}
const tileOf = (id: number) => screen.getByRole("button", { name: new RegExp("^" + escape(nameOf(id)) + "，") });

describe("opening and closing", () => {
  test("the button counts the buy queue; the dialog is modal, focuses its close button, and shows the first keyword open", async () => {
    const r = await open(mine());
    expect(buyButton()).toHaveTextContent("購買排序（5）");
    await r.user.click(buyButton());
    expect(dialog()).toHaveAttribute("aria-modal", "true");
    expect(within(dialog()).getByRole("button", { name: zh["gl.close"] })).toHaveFocus();
    expect(section("Burn")).toHaveAttribute("aria-expanded", "true");
    expect(section("Bleed")).toHaveAttribute("aria-expanded", "false");
    expect(rowIds()).toEqual([b1, b2, b3]);
  });

  test("Esc, the close button and a click on the backdrop close it; focus goes back to the button", async () => {
    const r = await open(mine());
    await openDialog(r);
    await r.user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(buyButton()).toHaveFocus();
    await openDialog(r);
    await r.user.click(within(dialog()).getByRole("button", { name: zh["gl.close"] }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(buyButton()).toHaveFocus();
    await openDialog(r);
    await r.user.click(dialog().parentElement!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(buyButton()).toHaveFocus();
    await openDialog(r);
    await r.user.click(dialog()); // inside the dialog is not the backdrop
    expect(dialog()).toBeInTheDocument();
  });

  test("Tab cycles inside the dialog", async () => {
    const r = await open(mine());
    await openDialog(r);
    const buttons = within(dialog()).getAllByRole("button").filter((b) => !(b as HTMLButtonElement).disabled);
    buttons[buttons.length - 1].focus();
    await r.user.tab();
    expect(buttons[0]).toHaveFocus();
    await r.user.tab({ shift: true });
    expect(buttons[buttons.length - 1]).toHaveFocus();
  });

  test("expand all and collapse all; a keyword with nothing wanted says so", async () => {
    const r = await open(mine());
    const d = await openDialog(r);
    await r.user.click(d.getByRole("button", { name: zh["gl.buy_expand"] }));
    for (const k of GIFT_KEYWORDS) expect(section(k)).toHaveAttribute("aria-expanded", "true");
    expect(rowIds()).toEqual([b1, b2, b3, l1, l2]);
    expect(d.getAllByText(zh["gl.buy_none"])).toHaveLength(GIFT_KEYWORDS.length - 2);
    await r.user.click(d.getByRole("button", { name: zh["gl.buy_collapse"] }));
    expect(rows()).toHaveLength(0);
    await r.user.click(section("Bleed"));
    expect(rowIds()).toEqual([l1, l2]);
  });
});

describe("what the sections say", () => {
  test("priority, count and the range in the whole queue; the first real keyword is the main one", async () => {
    const r = await open(mine({ order: ["Keywordless", "Burn", "Bleed", ...REST.filter((k) => k !== "Keywordless")] }));
    await openDialog(r);
    expect(section("Burn")).toHaveTextContent(`${say(zh["gl.rank"], { n: 2 })}・${say(zh["gl.tier_n"], { n: 3 })}`);
    expect(section("Burn")).toHaveTextContent("#1–3");
    expect(section("Bleed")).toHaveTextContent(`${say(zh["gl.rank"], { n: 3 })}・${say(zh["gl.tier_n"], { n: 2 })}`);
    expect(section("Bleed")).toHaveTextContent("#4–5");
    expect(section("Keywordless")).toHaveTextContent("—");
    expect(within(dialog()).getAllByText(zh["gl.main"])).toHaveLength(1);
    expect(section("Burn").parentElement).toHaveTextContent(zh["gl.main"]);
  });

  test("a gift row has its position in the whole queue, its name and its tier; the numbers match the main screen", async () => {
    const r = await open(mine({ order: ["Bleed", "Burn", ...REST] }));
    const d = await openDialog(r);
    await r.user.click(d.getByRole("button", { name: zh["gl.buy_expand"] }));
    expect(rows().map(position)).toEqual([1, 2, 3, 4, 5]);
    expect(rowIds()).toEqual([l1, l2, b1, b2, b3]);
    expect(rows()[0]).toHaveTextContent(nameOf(l1));
    expect(rows()[0]).toHaveTextContent("III");
    expect(buyButton()).toHaveTextContent(`（${queue(held(r)).length}）`);
    await r.user.click(within(dialog()).getByRole("button", { name: zh["gl.close"] }));
    await r.user.click(screen.getByRole("tab", { name: /^燒傷/ }));
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(say(zh["gl.rank"], { n: 2 }));
  });

  test("only wanted gifts the shop sells are listed: a kept gift, a fusion gift and a drop gift are not", async () => {
    const r = await open(mine({ want: [b1, burnFusion], keep: [b2] }));
    await openDialog(r);
    expect(rowIds()).toEqual([b1]);
  });
});

describe("moving with the buttons", () => {
  test("a gift's down and up buttons change gorder only; its position and the queue follow", async () => {
    const r = await open(mine());
    const d = await openDialog(r);
    expect(d.getByRole("button", { name: say(zh["gl.up_gift"], { name: nameOf(b1) }) })).toBeDisabled();
    expect(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(b3) }) })).toBeDisabled();
    await r.user.click(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(b1) }) }));
    expect(rowIds()).toEqual([b2, b1, b3]);
    expect(rows().map(position)).toEqual([1, 2, 3]);
    const g = held(r).gorder.Burn;
    expect(g.indexOf(b2)).toBeLessThan(g.indexOf(b1));
    expect(g.indexOf(b1)).toBeLessThan(g.indexOf(b3));
    expect(queue(held(r)).slice(0, 3)).toEqual([b2, b1, b3]);
    expect(held(r)).toMatchObject({ order: mine().order, want: mine().want, keep: [] });
    await r.user.click(d.getByRole("button", { name: say(zh["gl.up_gift"], { name: nameOf(b3) }) }));
    expect(rowIds()).toEqual([b2, b3, b1]);
  });

  test("a gift moves past its neighbour in the buy list, not past gifts the list does not buy", async () => {
    // b2a (tier II) sits between b1 and b2 in gorder but is not wanted: b1 moving down passes b2, not b2a.
    const gorder = defaultGorder();
    gorder.Burn = [b1, b2a, b2, b3, ...gorder.Burn.filter((x) => ![b1, b2a, b2, b3].includes(x))];
    const r = await open(mine({ gorder }));
    const d = await openDialog(r);
    await r.user.click(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(b1) }) }));
    expect(rowIds()).toEqual([b2, b1, b3]);
    expect(held(r).gorder.Burn.slice(0, 4)).toEqual([b2a, b2, b1, b3]);
  });

  test("keyboard focus stays on the button that was pressed, or the other one when it is now disabled", async () => {
    const r = await open(mine());
    const d = await openDialog(r);
    await r.user.click(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(b1) }) }));
    expect(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(b1) }) })).toHaveFocus();
    await r.user.click(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(b1) }) }));
    expect(d.getByRole("button", { name: say(zh["gl.up_gift"], { name: nameOf(b1) }) })).toHaveFocus(); // last: down is disabled
  });

  test("moving the second keyword up makes it the first, and so the main keyword", async () => {
    const r = await open(mine());
    const d = await openDialog(r);
    expect(section("Burn").parentElement).toHaveTextContent(zh["gl.main"]);
    expect(d.getByRole("button", { name: say(zh["gl.kw_up"], { name: zh["kw.Burn"] }) })).toBeDisabled();
    await r.user.click(d.getByRole("button", { name: say(zh["gl.kw_up"], { name: zh["kw.Bleed"] }) }));
    expect(held(r).order.slice(0, 3)).toEqual(["Bleed", "Burn", REST[0]]);
    expect(held(r).gorder).toEqual(mine().gorder);
    expect(section("Bleed").parentElement).toHaveTextContent(zh["gl.main"]);
    expect(section("Burn").parentElement).not.toHaveTextContent(zh["gl.main"]);
    expect(section("Bleed")).toHaveTextContent("#1–2");
    expect(section("Burn")).toHaveTextContent("#3–5");
    await r.user.click(section("Bleed"));
    expect(rows().map(position)).toEqual([1, 2, 3, 4, 5]); // Bleed's rows now come first
    await r.user.click(d.getByRole("button", { name: say(zh["gl.kw_down"], { name: zh["kw.Bleed"] }) }));
    expect(held(r).order.slice(0, 2)).toEqual(["Burn", "Bleed"]);
  });

  test("the main screen follows: the keyword tabs keep their order, the header says who is main", async () => {
    const r = await open(mine());
    const d = await openDialog(r);
    await r.user.click(d.getByRole("button", { name: say(zh["gl.kw_up"], { name: zh["kw.Bleed"] }) }));
    await r.user.click(d.getByRole("button", { name: zh["gl.close"] }));
    const tabs = screen.getAllByRole("tab").map((x) => x.textContent!.replace(/\d+$/, ""));
    expect(tabs).toEqual(GIFT_KEYWORDS.map((k) => zh[`kw.${k}` as keyof typeof zh]));
    await r.user.click(screen.getByRole("tab", { name: /^流血/ }));
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(zh["gl.main"]);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(say(zh["gl.rank"], { n: 1 }));
  });
});

describe("dragging in the dialog", () => {
  test("a keyword dropped on another takes its place; a gift only within its keyword", async () => {
    const r = await open(mine());
    const d = await openDialog(r);
    await r.user.click(d.getByRole("button", { name: zh["gl.buy_expand"] }));
    drag(rows()[0], rows()[2]); // b1 onto b3: moves after it
    expect(rowIds()).toEqual([b2, b3, b1, l1, l2]);
    drag(rows()[3], rows()[0]); // a Bleed gift onto a Burn gift: refused
    expect(rowIds()).toEqual([b2, b3, b1, l1, l2]);
    drag(section("Bleed"), section("Burn"));
    expect(held(r).order.slice(0, 2)).toEqual(["Bleed", "Burn"]);
    drag(section("Burn"), rows()[0]); // a keyword onto a gift: refused
    expect(held(r).order.slice(0, 2)).toEqual(["Bleed", "Burn"]);
  });

  test("dragging a gift up puts it before the target", async () => {
    const r = await open(mine());
    await openDialog(r);
    drag(rows()[2], rows()[0]);
    expect(rowIds()).toEqual([b3, b1, b2]);
  });
});

describe("dragging on the main screen", () => {
  test("a gift dropped on another of the same keyword and tier moves in gorder", async () => {
    const r = await open(mine());
    drag(tileOf(b3), tileOf(b1));
    const g = held(r).gorder.Burn;
    expect(g.slice(0, 3)).toEqual([b3, b1, b2]);
    expect(held(r)).toMatchObject({ order: mine().order, want: mine().want, keep: [] });
    drag(tileOf(b1), tileOf(b3)); // up again: before the target
    expect(held(r).gorder.Burn.slice(0, 3)).toEqual([b1, b3, b2]);
    drag(tileOf(b1), tileOf(b2)); // down: after the target
    expect(held(r).gorder.Burn.slice(0, 3)).toEqual([b3, b2, b1]);
  });

  test("a gift dropped on another tier is refused", async () => {
    const r = await open(mine());
    const before = JSON.stringify(held(r));
    drag(tileOf(b1), tileOf(b2a));
    expect(JSON.stringify(held(r))).toBe(before);
  });

  test("a fusion gift has no place in gorder and cannot be dragged", async () => {
    await open(mine());
    expect(tileOf(burnFusion)).toHaveAttribute("draggable", "false");
    expect(tileOf(b1)).toHaveAttribute("draggable", "true");
  });

  test("the default list refuses the drag with the notice", async () => {
    const r = await open(null);
    const before = JSON.stringify(r.settings());
    const [a, b] = DEFAULT_LIST.gorder.Burn.filter((id) => GIFT_BY_ID.get(id)!.tier === 3);
    expect(fireEvent.dragStart(tileOf(a), { dataTransfer: dt() })).toBe(false); // the drag does not start
    expect(screen.getByRole("status")).toHaveTextContent(zh["gl.ro"]);
    drag(tileOf(a), tileOf(b));
    expect(JSON.stringify(r.settings())).toBe(before);
  });
});

describe("the default list in the dialog", () => {
  test("it can be looked at; every move only shows the notice", async () => {
    const r = await open(null);
    const before = JSON.stringify(r.settings());
    expect(buyButton()).toHaveTextContent(`（${queue(DEFAULT_LIST).length}）`);
    const d = await openDialog(r);
    const first = rowIds()[0];
    await r.user.click(d.getByRole("button", { name: say(zh["gl.down_gift"], { name: nameOf(first) }) }));
    expect(within(dialog()).getByRole("status")).toHaveTextContent(zh["gl.ro"]);
    expect(rowIds()[0]).toBe(first);
    const main = DEFAULT_LIST.order.find((k) => k !== "Keywordless")!;
    const second = DEFAULT_LIST.order[DEFAULT_LIST.order.indexOf(main) + 1];
    await r.user.click(d.getByRole("button", { name: say(zh["gl.kw_up"], { name: zh[`kw.${second}` as keyof typeof zh] }) }));
    drag(section(main), section(second));
    expect(JSON.stringify(r.settings())).toBe(before);
  });
});

describe("in English", () => {
  test("title, labels and the buttons' names", async () => {
    const en = TEXT.en_us;
    const r = await open(mine(), "en_us");
    await r.user.click(screen.getByRole("button", { name: /^Purchase order \(5\)/ }));
    const d = within(screen.getByRole("dialog", { name: en["gl.buy_title"] }));
    expect(d.getByRole("button", { name: say(en["gl.down_gift"], { name: GIFT_BY_ID.get(b1)!.en }) })).toBeInTheDocument();
    expect(d.getByRole("button", { name: say(en["gl.kw_up"], { name: "Bleed" }) })).toBeInTheDocument();
  });
});
