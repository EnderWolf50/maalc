// The window shows the data it reads when it starts (gameData.ts), not what the build held (#767).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import css from "./index.css?raw";
import { StartError } from "./StartError";

const REPO = import.meta.glob<string>(["../../assets/resource/base/data/*.{json,yaml}", "../../assets/resource/base/data/*/{index,plates}.json"],
  { query: "?raw", import: "default", eager: true });
const repoText = (name: string) => REPO["../../assets/resource/base/data/" + name];

afterEach(() => { vi.resetModules(); vi.doUnmock("@tauri-apps/api/core"); });

/** The app under Tauri, with `change` applied to the texts the Rust side would read from the install's data folder. */
async function underTauri(change: (texts: Record<string, string>) => void) {
  const { GAME_TEXTS, GAME_FOLDERS } = await import("./api");
  const texts = Object.fromEntries(GAME_TEXTS.map((n) => [n, repoText(n)]));
  change(texts);
  const folders = Object.fromEntries(GAME_FOLDERS.map((f) => [f, ["9999999.webp"]]));
  vi.resetModules();
  vi.doMock("@tauri-apps/api/core", () => ({
    isTauri: () => true, convertFileSrc: (p: string) => `asset://${p}`,
    invoke: vi.fn().mockResolvedValue({ dir: "C:/install/resource/base/data", texts, folders }),
  }));
}

test("a gift added to the installed data shows in the catalog with its icon and effect, without a new build", async () => {
  await underTauri((texts) => {
    const search = JSON.parse(texts["gift_search.json"]);
    search.gifts.push({ id: 9999999, keyword: "Burn", tier: 1, en: "Brand New Gift", zh: "全新飾品" });
    texts["gift_search.json"] = JSON.stringify(search);
    const effects = JSON.parse(texts["gift_effects.json"]);
    effects.effects["9999999"] = { en: "New effect", zh: "新效果" };
    texts["gift_effects.json"] = JSON.stringify(effects);
  });
  const { GIFT_BY_ID, giftEffect, iconUrl } = await import("./giftCatalog");
  expect(GIFT_BY_ID.get(9999999)?.en).toBe("Brand New Gift");
  expect(giftEffect(9999999, true)).toBe("新效果");
  expect(iconUrl(9999999)).toBe("asset://C:/install/resource/base/data/gift_icons/9999999.webp");
  expect(iconUrl(1)).toBeUndefined(); // the folder lists no other icon
});

test("a gift the installed data lacks is not in the catalog: the repo's copy is not bundled behind it", async () => {
  await underTauri((texts) => {
    const search = JSON.parse(texts["gift_search.json"]);
    texts["gift_search.json"] = JSON.stringify({ ...search, gifts: search.gifts.slice(1) });
  });
  const first = JSON.parse(repoText("gift_search.json")).gifts[0];
  const { SEARCH_GIFTS } = await import("./model");
  expect(SEARCH_GIFTS.find((g) => g.id === first.id)).toBeUndefined();
});

test("the stylesheet's sprites are all set by applyArt, each from its file in the data folder", async () => {
  const used = [...new Set([...css.matchAll(/var\((--sprite-[\w-]+)\)/g)].map((m) => m[1]))];
  expect(used.length).toBeGreaterThan(10);
  const { applyArt } = await import("./gameData");
  const root = document.createElement("div");
  applyArt(root);
  for (const name of used) expect(root.style.getPropertyValue(name), name).toMatch(/^url\(".+\.webp"\)$/);
});

test("the window says why it cannot start instead of staying blank", () => {
  render(<StartError error={new Error("C:\\maalc\\resource\\base\\data\\graces.json: The system cannot find the file specified.")} />);
  expect(screen.getByRole("alert")).toHaveTextContent("graces.json: The system cannot find the file specified.");
  expect(screen.getByRole("alert")).toHaveTextContent("無法讀取遊戲資料");
});

test("the reason of a string rejection (what Tauri's invoke gives) is shown too", () => {
  render(<StartError error={"no resource folder under <root>"} />);
  expect(screen.getByRole("alert")).toHaveTextContent("no resource folder under <root>");
});

test("the error page has a way to close the window: the window has no title bar of its own", async () => {
  const destroy = vi.fn().mockResolvedValue(undefined);
  vi.doMock("@tauri-apps/api/core", () => ({ isTauri: () => true, invoke: vi.fn(), convertFileSrc: String }));
  vi.doMock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ destroy }) }));
  const { StartError: Fresh } = await import("./StartError");
  render(<Fresh error="x" />);
  await userEvent.click(screen.getByRole("button", { name: /關閉/ }));
  expect(destroy).toHaveBeenCalled();
  vi.doUnmock("@tauri-apps/api/window");
});

test("a data file that is there but cut off or mistyped fails with its name", async () => {
  await underTauri((texts) => { texts["graces.json"] = texts["graces.json"].slice(0, 100); });
  await expect(import("./gameData")).rejects.toThrow(/^graces\.json: /);
  await underTauri((texts) => { texts["shop.yaml"] = "a: [1, 2"; });
  await expect(import("./gameData")).rejects.toThrow(/^shop\.yaml: /);
});
