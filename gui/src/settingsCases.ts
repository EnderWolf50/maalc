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

/** The valid file at an older version, without the team_queue version 22 added (#803), these edits made to it; version 20's
 * with the three sections version 21 dropped (#782). */
function beforeQueue(version: 20 | 21, edits: Edit[]) {
  const { team_queue: _, ...old } = cases.valid;
  return applyEdits({ ...old, version, ...(version === 20 ? cases.v20 : {}) }, edits);
}
export const v20File = (edits: Edit[] = []) => beforeQueue(20, edits);
export const v21File = (edits: Edit[] = []) => beforeQueue(21, edits);
