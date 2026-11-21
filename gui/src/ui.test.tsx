// The shared controls of ui.tsx. ReorderList: the whole row drags, Alt with an arrow moves a row from the keyboard, and a list
// that selects (teams, plans) is picked from the keyboard too. Choice and Select: every dropdown draws the same chevron.
import { screen, within } from "@testing-library/react";
import { useState } from "react";
import { expect, test } from "vitest";
import giftListsCss from "./giftlists.css?raw";
import { TEXT } from "./i18n";
import indexCss from "./index.css?raw";
import { altMove, cssRules, cssValueOf, dragHeld, dragOnto, renderEditor } from "./testing";
import { LockContext, ReorderList } from "./ui";

test("no rule but the base one gives a select the background shorthand, which would clear its drawn chevron (#734)", () => {
  const base = 'select, input:not([type="checkbox"])'; // the chevron rule follows it at the same specificity
  const reachesSelect = (selector: string) => selector.split(",").some((s) => /(^|[\s>+~])select\b/.test(s.trim()));
  const clearing = [...cssRules(indexCss), ...cssRules(giftListsCss)]
    .filter((r) => r.selector !== base && reachesSelect(r.selector) && /(^|[;\s])background\s*:/.test(r.body))
    .map((r) => r.selector);
  expect(clearing).toEqual([]);
});

function Picker({ onPick }: { onPick?: (name: string) => void }) {
  const [items, setItems] = useState(["Ta", "Tb", "Tc"]);
  const [sel, setSel] = useState(0);
  return (
    <>
      <ReorderList items={items} keyOf={(x) => x} render={(x) => x} onChange={setItems} selected={sel}
        onSelect={onPick && ((i, list) => { setSel(i); onPick(list[i]); })} />
      <output>{items[sel]}</output>
    </>
  );
}

test("a row of a selecting list takes focus, and Enter or Space picks it", async () => {
  const { user } = renderEditor(<Picker onPick={() => {}} />);
  const rows = screen.getAllByRole("listitem");
  rows[1].focus();
  expect(rows[1]).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("status")).toHaveTextContent("Tb");
  expect(rows[1]).toHaveAttribute("aria-current", "true");
  rows[2].focus();
  await user.keyboard(" ");
  expect(screen.getByRole("status")).toHaveTextContent("Tc");
});

const order = () => screen.getAllByRole("listitem").map((li) => li.textContent);
const row = (name: string) => screen.getAllByRole("listitem").find((li) => li.textContent === name)!;

// #873 (spec #871 「共用的排序清單」): the whole row drags, no handle and no ↑↓; the keyboard moves a row with Alt and an arrow
test("a row has no handle and no move buttons: the row itself drags", () => {
  renderEditor(<Picker onPick={() => {}} />);
  for (const li of screen.getAllByRole("listitem")) {
    expect(li).toHaveAttribute("draggable", "true");
    expect(within(li).queryAllByRole("button")).toEqual([]);
    expect(li).toHaveTextContent(/^T\w$/); // the row's own words only, no grip mark
  }
  dragOnto(row("Tc"), row("Ta"));
  expect(order()).toEqual(["Tc", "Ta", "Tb"]);
});

test("Alt+↓ and Alt+↑ move the focused row one place, Alt+End and Alt+Home to the end and the start; the focus stays on it", async () => {
  const { user } = renderEditor(<Picker />);
  await altMove(user, row("Ta"), "ArrowDown");
  expect(order()).toEqual(["Tb", "Ta", "Tc"]);
  expect(row("Ta")).toHaveFocus();
  await user.keyboard("{Alt>}{End}{/Alt}");
  expect(order()).toEqual(["Tb", "Tc", "Ta"]);
  expect(row("Ta")).toHaveFocus();
  await user.keyboard("{Alt>}{ArrowUp}{/Alt}");
  expect(order()).toEqual(["Tb", "Ta", "Tc"]);
  await user.keyboard("{Alt>}{Home}{/Alt}");
  expect(order()).toEqual(["Ta", "Tb", "Tc"]);
  expect(row("Ta")).toHaveFocus();
  // past an end, and an arrow without Alt, leave the order as it is
  await user.keyboard("{Alt>}{ArrowUp}{/Alt}{ArrowDown}");
  expect(order()).toEqual(["Ta", "Tb", "Tc"]);
});

test("a move is read out as the row's new place, in a live region that is not a status (the Undo note is one)", async () => {
  const { user } = renderEditor(<Picker />);
  await altMove(user, row("Tc"), "Home");
  const said = screen.getByText("移到第 1 位，共 3 位");
  expect(said.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  expect(said.closest("[role=status]")).toBeNull();
});

test("a second move to the same place is read out again: its words come into the live region anew", async () => {
  const { user } = renderEditor(<Picker />);
  await altMove(user, row("Tc"), "Home");
  const first = screen.getByText("移到第 1 位，共 3 位");
  await altMove(user, row("Tb"), "Home"); // the same words: a screen reader reads only what the region gains
  const second = screen.getByText("移到第 1 位，共 3 位");
  expect(second).not.toBe(first);
  expect(first).not.toBeInTheDocument();
  expect(second.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
});

test("every row takes the focus and says how it moves; the list has the name it is given", () => {
  renderEditor(<ReorderList items={["Ta", "Tb"]} keyOf={(x) => x} render={(x) => x} onChange={() => {}} label="任務清單" />);
  expect(screen.getByRole("list", { name: "任務清單" })).toBeInTheDocument();
  for (const li of screen.getAllByRole("listitem")) {
    expect(li).toHaveAttribute("tabindex", "0");
    expect(li).toHaveAccessibleDescription(TEXT.zh_tw.moveHint);
  }
});

test("a row shows the grabbing hand; while dragged it is dimmed, and a line marks where it lands, past the row under it", () => {
  const look = (name: string, prop: string) => cssValueOf(indexCss, row(name), prop);
  renderEditor(<Picker />);
  expect(look("Ta", "cursor")).toBe("grab");
  expect(look("Tb", "box-shadow")).toBeUndefined();
  let drag = dragHeld(row("Ta"), row("Tc"));
  expect(Number(look("Ta", "opacity"))).toBeLessThan(1);
  expect(look("Tc", "box-shadow")).toMatch(/^0 \dpx /); // dragged down: it lands after Tc, so the line is under Tc
  expect(look("Tb", "box-shadow")).toBeUndefined();
  drag.end();
  drag = dragHeld(row("Tc"), row("Ta"));
  expect(look("Ta", "box-shadow")).toMatch(/^0 -\dpx /); // dragged up: before Ta, the line over it
  drag.leave(); // out of the list: no drop place left
  expect(look("Ta", "box-shadow")).toBeUndefined();
  drag.end();
  expect(look("Ta", "box-shadow")).toBeUndefined();
});

test("the page is the box of what a list draws out of the flow (its words for a screen reader): no page-long scroll (#873)", () => {
  // with the window as their box they made the whole document scroll and the header shift by the scrollbar's width
  const main = document.body.appendChild(document.createElement("main"));
  expect(cssValueOf(indexCss, main, "position")).toBe("relative");
  main.remove();
});

test("locked (the Run tab during a run): neither a drag nor Alt with an arrow moves a row, and a row still picks", async () => {
  const picks: string[] = [];
  const { user } = renderEditor(<LockContext.Provider value={true}><Picker onPick={(name) => picks.push(name)} /></LockContext.Provider>);
  for (const li of screen.getAllByRole("listitem")) expect(li).toHaveAttribute("draggable", "false");
  expect(cssValueOf(indexCss, row("Ta"), "cursor")).toBe("default");
  dragOnto(row("Tc"), row("Ta"));
  await altMove(user, row("Ta"), "ArrowDown");
  await user.keyboard("{Alt>}{End}{/Alt}");
  expect(order()).toEqual(["Ta", "Tb", "Tc"]);
  await user.keyboard("{Enter}");
  expect(picks).toEqual(["Ta"]);
});
