import { expect, test } from "vitest";
import conf from "../src-tauri/tauri.conf.json";

test("the window keeps dragDropEnabled false: Tauri's default swallows HTML5 drag and drop on Windows, every list stopped reordering (#64)", () => {
  expect(conf.app.windows.map((w) => w.dragDropEnabled)).toEqual([false]);
});
