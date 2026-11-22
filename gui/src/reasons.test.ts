// Stop reason codes (#881): a code's sentence in the window's language, its params filled in, a team by its settings name.
import { describe, expect, test } from "vitest";
import { fill } from "./i18n";
import { REASONS, sayReason } from "./reasons";

describe("sayReason", () => {
  test("fills a code's sentence with its params in either language", () => {
    for (const lang of ["zh_tw", "en_us"] as const) {
      expect(sayReason(lang, { code: "LuxDefeated", params: { retries: 2 } })).toBe(fill(REASONS.LuxDefeated[lang], { retries: 2 }));
    }
    expect(sayReason("zh_tw", { code: "LuxDefeated", params: { retries: 2 } })).toBe("戰鬥失敗，2 次重打都用完了。");
  });

  test("a team param, an id, reads as the settings name the team; one they do not have stays its id", () => {
    const names: Record<string, string> = { b: "高難度隊" };
    const team = (id: string) => names[id] ?? id;
    expect(sayReason("zh_tw", { code: "StartTeamDisabled", params: { team: "b" } }, team)).toBe("起頭隊伍「高難度隊」是停用的。啟用它，或選另一支。");
    expect(sayReason("en_us", { code: "TeamDeleted", params: { team: "gone" } }, team))
      .toBe('The team "gone" was deleted. Pick another one in the options of this task.');
  });

  test("no sentence for no code, a code the file does not have, or params that do not fill its sentence", () => {
    expect(sayReason("zh_tw", undefined)).toBeUndefined();
    expect(sayReason("zh_tw", { code: "NotYetKnown", params: {} })).toBeUndefined();
    expect(sayReason("zh_tw", { code: "toString", params: {} })).toBeUndefined(); // not an inherited key
    expect(sayReason("zh_tw", { code: "LuxDefeated", params: {} })).toBeUndefined();
  });
});
