// Stop reason codes (#881): why a task failed or was cancelled, in the window's language. agent/stop_reasons.json holds each
// code's sentences; the bot logs a code after its stop line (agent/reasons.py) and the runner sends it in the task event
// (runner/protocol.py). A reason with no code, or a code this window does not know (a newer bot's), shows its English text.
import file from "../../agent/stop_reasons.json";
import { fill } from "./i18n";
import type { Settings } from "./model";

export type ReasonParams = Record<string, string | number>;
/** A reason's code and its params, as the runner sends them (`reason_code`, `reason_params`). */
export interface ReasonCode { code: string; params: ReasonParams }

export const REASONS: Record<string, Record<Settings["language"], string>> = file.codes;

/** The code's sentence in lang with its params filled in; undefined for a code the file does not have, or params that do not
 * fill each of its placeholders (the English text then shows). */
export function sayReason(lang: Settings["language"], coded: ReasonCode | undefined): string | undefined {
  const sentence = coded && Object.prototype.hasOwnProperty.call(REASONS, coded.code) ? REASONS[coded.code][lang] : undefined;
  if (sentence === undefined) return undefined;
  const wanted = [...sentence.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
  return wanted.every((k) => Object.prototype.hasOwnProperty.call(coded!.params, k)) ? fill(sentence, coded!.params) : undefined;
}
