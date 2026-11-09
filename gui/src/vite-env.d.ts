/// <reference types="vite/client" />

// agent/settings.schema.json compiled by Ajv's standalone mode at build time (settingsValidator.ts, #220).
declare module "virtual:settings-validator" {
  import type { ValidateFunction } from "ajv";
  /** A whole settings file. */
  export const settings: ValidateFunction;
  /** One gift_lists entry ($defs/gift_list). */
  export const giftList: ValidateFunction;
}
