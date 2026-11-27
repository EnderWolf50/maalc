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

/** The valid file at an older version, these edits made to it (tests/test_settings.py older): each team with the switch version
 * 24 dropped, and run with version 23's start_team (#954); below version 23 without the sections it added (#813), below 22
 * without its team_queue (#803), and version 20's with the three sections it had. */
export function olderFile(version: 20 | 21 | 22 | 23, edits: Edit[] = []) {
  const teams = cases.valid.teams.map((t) => ({ ...t, enabled: true }));
  const all = { ...cases.valid, teams, run: { ...cases.valid.run, start_team: null } };
  const old = Object.fromEntries(Object.entries(all).filter(([k]) =>
    version === 23 || (!cases.added_v23.includes(k) && (version === 22 || k !== "team_queue"))));
  return applyEdits({ ...old, version, ...(version === 20 ? cases.v20 : {}) }, edits);
}
export const v20File = (edits: Edit[] = []) => olderFile(20, edits);
export const v21File = (edits: Edit[] = []) => olderFile(21, edits);
