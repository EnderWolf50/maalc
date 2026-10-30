// The built GUI runs under tauri.conf.json's CSP (the dev page does not, #164): what vite inlines has to pass it.
import { expect, test } from "vitest";
import conf from "../src-tauri/tauri.conf.json";

const directive = (name: string) =>
  conf.app.security.csp.split(";").map((d) => d.trim().split(/\s+/)).find(([n]) => n === name)?.slice(1);

test("images may be data: URLs: vite inlines every icon under 4 KB as one, the gift and keyword icons all but one (#310)", () => {
  expect(directive("img-src")).toEqual(expect.arrayContaining(["'self'", "data:"]));
});
