// tests/settings_cases.json as the GUI's tests read it, tests/test_settings.py the same way. Not bundled (only tests import it).
import cases from "../../tests/settings_cases.json";

export { cases };

/** A case's edit of a settings file: set a value (a last path segment of - appends) or delete it. */
export type Edit = { set: string; value: unknown } | { delete: string };

export function applyEdits(data: unknown, edits: Edit[]) {
  const out = structuredClone(data) as Record<string, unknown>;
  for (const edit of edits) {
    const parts = ("set" in edit ? edit.set : edit.delete).split("/");
    const last = parts.pop()!;
    let node = out as Record<string, unknown>;
    for (const key of parts) node = node[key] as Record<string, unknown>;
    if (!("set" in edit)) delete node[last];
    else if (last === "-") (node as unknown as unknown[]).push(edit.value);
    else node[last] = edit.value;
  }
  return out;
}

/** The valid file at an older version, these edits made to it (tests/test_settings.py older): without the sections version
 * 23 added (#813), without the team_queue version 22 added below it (#803), and version 20's with the three sections it
 * had. */
export function olderFile(version: 20 | 21 | 22, edits: Edit[] = []) {
  const old = Object.fromEntries(Object.entries(cases.valid).filter(([k]) =>
    !cases.added_v23.includes(k) && (version >= 22 || k !== "team_queue")));
  return applyEdits({ ...old, version, ...(version === 20 ? cases.v20 : {}) }, edits);
}
export const v20File = (edits: Edit[] = []) => olderFile(20, edits);
export const v21File = (edits: Edit[] = []) => olderFile(21, edits);
