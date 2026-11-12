// The shared controls of ui.tsx. ReorderList: a list that selects (teams, plans) is reached and picked from the keyboard too.
import { screen } from "@testing-library/react";
import { useState } from "react";
import { expect, test } from "vitest";
import { renderEditor } from "./testing";
import { ReorderList } from "./ui";

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

test("a key on a row's own buttons moves the row, and does not pick it", async () => {
  const { user } = renderEditor(<Picker onPick={() => {}} />);
  screen.getAllByRole("button", { name: "下移" })[0].focus();
  await user.keyboard("{Enter}");
  expect(screen.getAllByRole("listitem").map((li) => li.textContent!.match(/T\w/)![0])).toEqual(["Tb", "Ta", "Tc"]);
  expect(screen.getByRole("status")).toHaveTextContent("Ta");
});

test("a list that only orders (no selection) adds no tab stop per row", () => {
  renderEditor(<Picker />);
  for (const row of screen.getAllByRole("listitem")) expect(row).not.toHaveAttribute("tabindex");
});
