// The two override tabs (spec 04 sections 10 and 11): event overrides and trial score overrides, one editable table with
// their own columns.
import type { Key } from "./i18n";
import { Decimal, Input, Mark, useEditor, useUndoRow, withBreaks } from "./ui";

/** One editable table for both override lists (spec 04 sections 10 and 11). */
function OverrideTable<R extends Record<string, string | number>>({ listKey, cols, blank }: {
  listKey: "event_overrides" | "trial_risk_overrides";
  cols: { key: keyof R & string; label: Key; number?: boolean }[];
  blank: R;
}) {
  const { s, update, t } = useEditor();
  const rows = s[listKey] as unknown as R[];
  const set = (fn: (rows: R[]) => void) => update((d) => fn(d[listKey] as unknown as R[]));
  const [undoNote, removeRow] = useUndoRow(set);
  return (
    <>
      {undoNote}
      {rows.length ? (
        <table className="overrides">
          <thead><tr>{cols.map((c) => <th key={c.key}>{t(c.label)}</th>)}<th /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <Mark as="td" key={c.key} path={`${listKey}/${i}/${c.key}`}>
                    {c.number
                      ? <Decimal value={r[c.key] as number} min={0} onChange={(v) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = v; })} />
                      : <Input value={r[c.key] as string} onChange={(e) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = e.target.value; })} />}
                  </Mark>
                ))}
                <td><button type="button" className="danger" onClick={() => removeRow(rows, i, String(r[cols[0].key]))}>{t("remove")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">{t("noRows")}</p>}
      <button type="button" onClick={() => set((l) => { l.push({ ...blank }); })}>+ {t("add")}</button>
    </>
  );
}

export function EventsTab() {
  const { t } = useEditor();
  return (
    <div className="stack">
      <p className="muted">{withBreaks(t("event.note"))}</p>
      <OverrideTable listKey="event_overrides" blank={{ question: "", option: "" }}
        cols={[{ key: "question", label: "event.question" }, { key: "option", label: "event.option" }]} />
    </div>
  );
}

export function TrialsTab() {
  const { t } = useEditor();
  return (
    <div className="stack">
      <details className="hint">
        <summary>{t("trial.help")}</summary>
        <p>{withBreaks(t("trial.note"))}</p>
      </details>
      <OverrideTable listKey="trial_risk_overrides" blank={{ trial: "", risk: 1 }}
        cols={[{ key: "trial", label: "trial.trial" }, { key: "risk", label: "trial.risk", number: true }]} />
    </div>
  );
}
