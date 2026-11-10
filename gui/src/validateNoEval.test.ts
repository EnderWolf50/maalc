// The built GUI runs with script-src 'self' only (#220): validate.ts must not compile code at run time, which Ajv's
// compile() does through the Function constructor. With that constructor throwing here, loading validate.ts and running
// it must still work.
import { afterEach, expect, test, vi } from "vitest";
import cases from "../../tests/settings_cases.json";

afterEach(() => vi.unstubAllGlobals());

test("validate loads and runs with the Function constructor blocked, as CSP blocks it (#220)", async () => {
  vi.stubGlobal("Function", function blocked() {
    throw new EvalError("Function constructor blocked, as script-src 'self' blocks it");
  });
  const { validate } = await import("./validate");
  expect(validate(cases.valid)).toEqual([]);
  expect(validate({}).length).toBeGreaterThan(0);
});
