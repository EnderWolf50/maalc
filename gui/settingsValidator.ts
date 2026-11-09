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

/** The ES module source: settings checks a whole settings file, giftList one gift_lists entry. */
export function settingsValidatorCode(): string {
  const ajv = new Ajv2020({ allErrors: true, strict: false, code: { source: true, esm: true } });
  ajv.addSchema(schema);
  return standaloneCode(ajv, { settings: schema.$id, giftList: `${schema.$id}#/$defs/gift_list` });
}

export function settingsValidator(): Plugin {
  return {
    name: "settings-validator",
    resolveId: (id) => (id === ID ? RESOLVED : undefined),
    load: (id) => (id === RESOLVED ? settingsValidatorCode() : undefined),
  };
}
