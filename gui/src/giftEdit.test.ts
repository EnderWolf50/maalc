// plan(): what a click with a state does to a gift. Since #626 every recipe material of the 1.118.1 data is a gift a shop may
// sell, so no real gift is locked and unwantable; the mock makes Lunar Memory's first fragment one, as a season may.
import { describe, expect, test, vi } from "vitest";
import { plan } from "./giftEdit";
import { GIFT_KEYWORDS, defaultGorder } from "./model";

vi.mock("./giftCatalog", async (original) => {
  const real = await original<typeof import("./giftCatalog")>();
  return { ...real, wantable: (g: { id: number }) => g.id !== 9105 && real.wantable(g as Parameters<typeof real.wantable>[0]) };
});

const wantingLunar = { order: [...GIFT_KEYWORDS], want: [9083], keep: [], gorder: defaultGorder() };

describe("plan", () => {
  test("a locked material no shop sells is refused all three states, want too", () => {
    for (const to of ["want", "keep", "drop"] as const) expect(plan(wantingLunar, 9105, to)).toEqual({ locked: [9083] });
  });

  test("a locked material a shop sells may be wanted for itself", () => {
    expect(plan(wantingLunar, 9110, "want")).toEqual({ to: "want" });
    expect(plan(wantingLunar, 9110, "keep")).toEqual({ locked: [9083] });
  });

  test("an unlocked gift no shop sells becomes keep when wanted", () => {
    expect(plan({ ...wantingLunar, want: [] }, 9105, "want")).toEqual({ to: "keep", downgraded: true });
  });
});
