// The game data the settings window reads at run time (api.ts loadGameFiles): in a browser (and here) the repo's copy,
// under Tauri what the Rust side reads from <root>/resource/base/data.
import { afterEach, expect, test, vi } from "vitest";

afterEach(() => { vi.resetModules(); vi.doUnmock("@tauri-apps/api/core"); });

test("without Tauri the repo's data folder answers: text files, folder listings and the URL of an image", async () => {
  const { loadGameFiles } = await import("./api");
  const files = await loadGameFiles();
  expect(JSON.parse(files.texts["gift_search.json"]).gifts.length).toBeGreaterThan(0);
  expect(files.texts["theme_packs.yaml"]).toContain("pack_ids");
  expect(files.folders["grace_icons"]).toContain("1.webp");
  expect(files.folders["gift_icons"].length).toBeGreaterThan(100);
  expect(files.url("grace_icons/1.webp")).toMatch(/grace_icons\/1\.webp$/);
});

test("under Tauri the Rust side's answer is used, and an image's URL is the asset protocol's URL of its file", async () => {
  const invoke = vi.fn().mockResolvedValue({
    dir: "C:/maalc/resource/base/data", texts: { "gift_search.json": "{}" }, folders: { gift_icons: ["9001.webp"] },
  });
  vi.doMock("@tauri-apps/api/core", () => ({
    invoke, isTauri: () => true, convertFileSrc: (p: string) => `asset://${p}`,
  }));
  const { loadGameFiles } = await import("./api");
  const files = await loadGameFiles();
  expect(invoke).toHaveBeenCalledWith("load_game_data", expect.objectContaining({ texts: expect.arrayContaining(["gift_search.json"]) }));
  expect(files.texts["gift_search.json"]).toBe("{}");
  expect(files.folders["gift_icons"]).toEqual(["9001.webp"]);
  expect(files.url("gift_icons/9001.webp")).toBe("asset://C:/maalc/resource/base/data/gift_icons/9001.webp");
});

test("a read that fails under Tauri reaches the caller with the reason", async () => {
  vi.doMock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockRejectedValue("no resource folder under <root>"), isTauri: () => true, convertFileSrc: String }));
  const { loadGameFiles } = await import("./api");
  await expect(loadGameFiles()).rejects.toBe("no resource folder under <root>");
});
