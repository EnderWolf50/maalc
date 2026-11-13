// The trial table's names and scores (data/trials.yaml, #381), bundled at build time: the trial score overrides tab offers the
// names and says when a typed one is not in the table (spec 04 section 11: such a row has no effect).
import { parse as parseYaml } from "yaml";
import trialsYaml from "../../assets/resource/base/data/trials.yaml?raw";

/** Trial name -> its score in pt, as the table has it. */
export const TRIAL_SCORES: Record<string, number> = Object.fromEntries(
  Object.entries((parseYaml(trialsYaml) as { trials: Record<string, { score: number }> }).trials).map(([name, t]) => [name, t.score]),
);
