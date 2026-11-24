// The dev server hands virtual:settings-validator to the browser as is, and a browser has no require (#220).
/// <reference path="./src/vite-env.d.ts" />
import equal from "ajv/dist/runtime/equal";
import ucs2length from "ajv/dist/runtime/ucs2length";
import { settings, giftList } from "virtual:settings-validator";
import { expect, test } from "vitest";
import cases from "../tests/settings_cases.json";
import { settingsValidatorCode } from "./settingsValidator";

const dataModule = (source: string) => `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`;

const RUNTIME_HELPERS: Record<string, { toString(): string }> = {
  "ajv/dist/runtime/ucs2length": ucs2length,
  "ajv/dist/runtime/equal": equal,
};

/** Load the generated module with each Ajv runtime helper exported either as Vite dev's pre-bundled CommonJS object
 * (`export default { __esModule: true, default: fn }`) or as the unwrapped function the build and vitest see (#666). */
async function loadGenerated(wrapped: boolean) {
  const source = settingsValidatorCode().replace(/"(ajv\/dist\/runtime\/[\w-]+)"/g, (_, spec: string) => {
    const helper = RUNTIME_HELPERS[spec];
    if (!helper) throw new Error(`unexpected Ajv runtime helper: ${spec}`);
    const body = wrapped
      ? `const fn = ${helper.toString()};\nexport default Object.defineProperty({ default: fn }, "__esModule", { value: true });`
      : `export default ${helper.toString()};`;
    return JSON.stringify(dataModule(body));
  });
  return import(/* @vite-ignore */ dataModule(source)) as Promise<{ settings: typeof settings; giftList: typeof giftList }>;
}

test("the generated validator module imports Ajv's runtime helpers instead of requiring them", () => {
  const code = settingsValidatorCode();
  expect(code).not.toMatch(/=\s*require\(/);
  expect(code).toMatch(/;import \w+ from "ajv\/dist\/runtime\/ucs2length";/);
  expect(code).toMatch(/;import \w+ from "ajv\/dist\/runtime\/equal";/);
});

// Guards the virtual module's contract in Vitest (passes on base; the dev-server CJS-wrapper case below is red on base).
test("virtual:settings-validator validates the shared valid settings file and its gift list", () => {
  expect(settings(cases.valid)).toBe(true);
  expect(giftList(cases.valid.gift_lists[0])).toBe(true);
});

test.each([
  ["dev server CJS wrapper ({ default: fn })", true],
  ["build unwrapped function", false],
])("the generated module runs minLength and uniqueItems checks with %s (#666)", async (_, wrapped) => {
  const mod = await loadGenerated(wrapped);
  expect(mod.settings(cases.valid)).toBe(true);
  expect(mod.giftList(cases.valid.gift_lists[0])).toBe(true);

  const emptyName = structuredClone(cases.valid);
  emptyName.teams[0].name = "";
  expect(mod.settings(emptyName)).toBe(false);

  const duplicateGift = structuredClone(cases.valid);
  duplicateGift.gift_lists[0].want = [9053, 9053];
  expect(mod.settings(duplicateGift)).toBe(false);
  expect(mod.giftList(duplicateGift.gift_lists[0])).toBe(false);
});
