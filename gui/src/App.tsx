// Shell: load <root>/config/settings.json, the tabs, and check-then-save (spec 04 section 2).
import { useEffect, useMemo, useState } from "react";
import * as api from "./api";
import { TEXT, type Key } from "./i18n";
import { newSettings, parseSettings, runEnum, type Settings } from "./model";
import { DeploymentTab, StarlightTab, ThemePackTab } from "./Plans";
import { TeamsTab } from "./Teams";
import { EditorContext, Field, Num, Select, useEditor, type Ctx } from "./ui";
import { validate, type Problem } from "./validate";

const TABS = [
  ["run", "tab.run", RunTab, ["run"]],
  ["teams", "tab.teams", TeamsTab, ["teams"]],
  ["deployment", "tab.deployment", DeploymentTab, ["deployment_order_plans"]],
  ["starlight", "tab.starlight", StarlightTab, ["starlight_plans"]],
  ["themepacks", "tab.themepacks", ThemePackTab, ["theme_pack_plans"]],
  ["events", "tab.events", EventsTab, ["event_overrides"]],
  ["trials", "tab.trials", TrialsTab, ["trial_risk_overrides"]],
] as const;

const toText = (s: Settings) => JSON.stringify(s, null, 2) + "\n";

export default function App() {
  const [s, setS] = useState<Settings | null>(null);
  const [savedText, setSavedText] = useState("");
  const [loadError, setLoadError] = useState("");
  const [root, setRoot] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("teams");
  const [checked, setChecked] = useState(false); // marks show after the first save attempt
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.rootDir().then(setRoot, (e) => setLoadError(String(e)));
    api.loadSettings().then(async (text) => {
      if (text === null) return setS(newSettings());
      try {
        const { data, migrated } = parseSettings(text);
        setS(data);
        if (migrated && !validate(data).length) await api.saveSettings(toText(data));
        setSavedText(toText(data)); // dirty = content changed, not formatting
      } catch (e) {
        setLoadError(String(e));
      }
    }, (e) => setLoadError(String(e)));
  }, []);

  const problems: Problem[] = useMemo(() => (s ? validate(s) : []), [s]);
  const lang = s?.language ?? "zh_tw";
  const t = (k: Key) => TEXT[lang][k] ?? k;

  if (loadError) {
    return (
      <main className="load-error">
        <p>{t("loadError")}</p>
        <pre>{loadError}</pre>
        <button type="button" onClick={() => { setLoadError(""); setS(newSettings()); }}>{t("newFile")}</button>
      </main>
    );
  }
  if (!s) return null;

  const marked = new Set(checked ? problems.flatMap((p) => p.paths) : []);
  const bad = (path: string) => [...marked].some((m) => m === path || m.startsWith(path + "/"));
  const ctx: Ctx = {
    s, t, bad,
    update: (fn) => setS((prev) => { const next = structuredClone(prev!); fn(next); return next; }),
    tv: (field, v) => TEXT[lang][`${field}.${v}` as Key] ?? v,
  };
  const dirty = toText(s) !== savedText;

  const save = async () => {
    setChecked(true);
    if (problems.length) return setStatus("");
    try {
      await api.saveSettings(toText(s));
      setSavedText(toText(s));
      setStatus(t("saved"));
    } catch (e) {
      setStatus(String(e));
    }
  };

  const Current = TABS.find((x) => x[0] === tab)![2];
  return (
    <EditorContext.Provider value={ctx}>
      <header>
        <h1>{t("title")}</h1>
        <span className="muted path" title={t("file")}>{root}\config\settings.json</span>
        <label className="lang">{t("language")}{" "}
          <select value={s.language} onChange={(e) => ctx.update((d) => { d.language = e.target.value as Settings["language"]; })}>
            <option value="zh_tw">繁體中文</option>
            <option value="en_us">English</option>
          </select>
        </label>
        <span className="status">{dirty ? t("unsaved") : status}</span>
        <button type="button" className="primary" onClick={save}>{t("save")}</button>
      </header>
      {checked && problems.length > 0 && (
        <div className="problems" role="alert">
          <p>{t("saveBlocked")}</p>
          <ul>{problems.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
        </div>
      )}
      <div className="body">
        <nav>
          {TABS.map(([id, label, , prefixes]) => (
            <button type="button" key={id} className={(tab === id ? "selected" : "") + (prefixes.some(bad) ? " bad" : "")}
              onClick={() => setTab(id)}>{t(label)}</button>
          ))}
        </nav>
        <main><Current /></main>
      </div>
    </EditorContext.Provider>
  );
}

function RunTab() {
  const { s, update, t, tv, bad } = useEditor();
  const run = s.run;
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  const pick = (k: "difficulty" | "weekly_bonus_use" | "weekly_bonus_amount" | "starlight_unaffordable" | "after_retries", note?: string) => (
    <Field label={t(`run.${k}`)} path={`run/${k}`} note={note}>
      <Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />
    </Field>
  );
  return (
    <div className="grid">
      {pick("difficulty")}
      <Field label={t("run.runs")} path="run/runs"><Num value={run.runs} min={0} onChange={(v) => set({ runs: v })} /></Field>
      {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
      {pick("weekly_bonus_amount")}
      <label className={"check" + (bad("run/stop_when_weekly_bonus_out") ? " bad" : "")}>
        <input type="checkbox" checked={run.stop_when_weekly_bonus_out} onChange={(e) => set({ stop_when_weekly_bonus_out: e.target.checked })} />
        {t("run.stop_when_weekly_bonus_out")}
      </label>
      {pick("starlight_unaffordable")}
      <Field label={t("run.wipe_retries")} path="run/wipe_retries"><Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} /></Field>
      {pick("after_retries")}
      <Field label={t("run.webhook_url")} path="run/webhook_url">
        <input type="url" value={run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />
      </Field>
    </div>
  );
}

/** One editable table for both override lists (spec 04 sections 10 and 11). */
function OverrideTable<R extends Record<string, string | number>>({ listKey, cols, blank }: {
  listKey: "event_overrides" | "trial_risk_overrides";
  cols: { key: keyof R & string; label: Key; number?: boolean }[];
  blank: R;
}) {
  const { s, update, t, bad } = useEditor();
  const rows = s[listKey] as unknown as R[];
  const set = (fn: (rows: R[]) => void) => update((d) => fn(d[listKey] as unknown as R[]));
  return (
    <>
      {rows.length ? (
        <table className="overrides">
          <thead><tr>{cols.map((c) => <th key={c.key}>{t(c.label)}</th>)}<th /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c.key} className={bad(`${listKey}/${i}/${c.key}`) ? "bad" : ""}>
                    {c.number
                      ? <Num value={r[c.key] as number} min={0} max={5} onChange={(v) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = v; })} />
                      : <input value={r[c.key] as string} onChange={(e) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = e.target.value; })} />}
                  </td>
                ))}
                <td><button type="button" className="danger" onClick={() => set((l) => { l.splice(i, 1); })}>{t("remove")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">{t("noRows")}</p>}
      <button type="button" onClick={() => set((l) => { l.push({ ...blank }); })}>+ {t("add")}</button>
    </>
  );
}

function EventsTab() {
  return <OverrideTable listKey="event_overrides" blank={{ question: "", option: "" }}
    cols={[{ key: "question", label: "event.question" }, { key: "option", label: "event.option" }]} />;
}

function TrialsTab() {
  return <OverrideTable listKey="trial_risk_overrides" blank={{ trial: "", risk: 5 }}
    cols={[{ key: "trial", label: "trial.trial" }, { key: "risk", label: "trial.risk", number: true }]} />;
}
