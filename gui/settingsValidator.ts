// Compiles agent/settings.schema.json into standalone validators when vite loads virtual:settings-validator (#220).
// The built GUI runs with script-src 'self', which blocks the Function constructor Ajv's compile() needs at run time;
// standalone code is plain JavaScript. Built at every build, dev start and test run from the schema itself, it always
// matches the schema, so there is no generated file to commit and keep in step.
import Ajv2020 from "ajv/dist/2020";
import standaloneCode from "ajv/dist/standalone";
import type { Plugin } from "vite";
import schema from "../agent/settings.schema.json";

const ID = "virtual:settings-validator";
const RESOLVED = "\0" + ID;

/** The ES module source: settings checks a whole settings file, giftList one gift_lists entry (src/vite-env.d.ts types
 * these two names). */
export function settingsValidatorCode(): string {
  const ajv = new Ajv2020({ allErrors: true, strict: false, code: { source: true, esm: true } });
  ajv.addSchema(schema);
  const code = standaloneCode(ajv, { settings: schema.$id, giftList: `${schema.$id}#/$defs/gift_list` });
  // Ajv 8 still requires its runtime helpers (ucs2length for minLength, equal for uniqueItems) in esm mode. The build
  // bundles a require, but the dev server sends this module to the browser as is, where require does not exist.
  return code.replace(/const (\w+) = require\("(ajv\/dist\/runtime\/[\w-]+)"\)\.default;/g, (_, name: string, path: string) =>
    `import ${name} from "${path}";`);
}

export function settingsValidatorPlugin(): Plugin {
  return {
    name: "settings-validator",
    resolveId: (id) => (id === ID ? RESOLVED : undefined),
    load: (id) => (id === RESOLVED ? settingsValidatorCode() : undefined),
  };
}
