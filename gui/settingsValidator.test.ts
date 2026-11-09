// The dev server hands virtual:settings-validator to the browser as is, and a browser has no require (#220).
import { expect, test } from "vitest";
import { settingsValidatorCode } from "./settingsValidator";

test("the generated validator module imports Ajv's runtime helpers instead of requiring them", () => {
  const code = settingsValidatorCode();
  expect(code).not.toMatch(/=\s*require\(/);
  expect(code).toMatch(/;import \w+ from "ajv\/dist\/runtime\/ucs2length";/);
});
