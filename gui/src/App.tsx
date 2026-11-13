// Shell: load <root>/config/settings.json, the tabs, and check-then-save (spec 04 section 2).
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api";
import { TEXT, type Key } from "./i18n";
import { LUX_MODES, newSettings, parseSettings, rebase, runEnum, type Luxcavation, type LuxMode, type Settings } from "./model";
import { DeploymentTab, StarlightTab, ThemePackTab } from "./Plans";
import { GiftListsTab } from "./GiftLists";
import { TeamsTab } from "./Teams";
import { Decimal, EditorContext, Field, Icon, Num, ProblemMark, Select, ToggleNum, tabKeys, useEditor, withBreaks, type Ctx } from "./ui";
import { validate, type Problem } from "./validate";

export const TABS = [
  ["run", "tab.run", RunTab, ["run"]],
  ["teams", "tab.teams", TeamsTab, ["teams"]],
  ["gifts", "tab.gifts", GiftListsTab, ["gift_lists"]],
  ["deployment", "tab.deployment", DeploymentTab, ["deployment_order_plans"]],
  ["starlight", "tab.starlight", StarlightTab, ["starlight_plans"]],
  ["themepacks", "tab.themepacks", ThemePackTab, ["theme_pack_plans"]],
  ["events", "tab.events", EventsTab, ["event_overrides"]],
  ["trials", "tab.trials", TrialsTab, ["trial_risk_overrides"]],
  ["daily", "tab.daily", DailyTab, ["luxcavation", "charge_enkephalin"]],
] as const;
/** The tab bar's groups start at these: the run and what it uses, the named plans, the overrides, the daily tasks. */
const GROUP_START = new Set<(typeof TABS)[number][0]>(["deployment", "events", "daily"]);

const toText = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
/** A field whose text has its own undo (the browser's): Ctrl+Z there is the field's, and its keystrokes are one edit. */
const isTextField = (el: EventTarget | null) => el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement
  && !["checkbox", "radio", "button", "submit", "range", "color", "file"].includes(el.type));
/** How many edits 復原 can take back. */
const UNDO_DEPTH = 100;

export default function App() {
  const [s, setS] = useState<Settings | null>(null);
  const [savedText, setSavedText] = useState("");
  const [loadError, setLoadError] = useState("");
  const [root, setRoot] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("teams");
  const [giftList, setGiftList] = useState("default"); // what the gift list tab shows; the teams tab can point it at a list
  const [checked, setChecked] = useState(false); // marks show after the first save attempt
  const [status, setStatus] = useState(""); // a TEXT key, or text as it is (an error, the gift ids a load dropped)
  // The file's text as last read or written: other text there is another writer's, the Agent's after a claim (#501).
  const disk = useRef<string | null>(null);
  const latest = useRef({ s, savedText });
  latest.current = { s, savedText };
  // Undo: the settings before each edit, newest last. A run of keystrokes in one text field is one edit.
  const past = useRef<Settings[]>([]);
  const [undoDepth, setUndoDepth] = useState(0);
  const lastEdit = useRef<{ at: number; field: EventTarget | null }>({ at: 0, field: null });
  const forget = () => { past.current = []; setUndoDepth(0); };
  const undo = () => {
    const before = past.current.pop();
    if (!before) return;
    setUndoDepth(past.current.length);
    lastEdit.current = { at: 0, field: null };
    latest.current = { ...latest.current, s: before };
    setS(before);
  };
  const undoRef = useRef(undo);
  undoRef.current = undo;

  /** Take what another writer changed in the file, under the unsaved edits (rebase); the settings the editor holds now. */
  const sync = async () => {
    const text = await api.loadSettings();
    const { s: draft, savedText: base } = latest.current; // set in one render: no draft is a load not done
    if (text === disk.current || !draft) return draft;
    let data: Settings | undefined;
    try {
      data = text === null ? undefined : parseSettings(text).data;
    } catch {
      return draft; // half an edit by hand: not taken as read, so a save is refused until it parses
    }
    disk.current = text;
    if (!data) {
      setStatus("diskGone");
      return draft;
    }
    const next = rebase(base ? JSON.parse(base) : newSettings(), draft, data); // no base: a new file, not saved yet
    latest.current = { s: next, savedText: toText(data) }; // now, not at the render: a save's sync may run before it
    setS(next);
    setSavedText(toText(data));
    setStatus("diskChanged");
    forget(); // the steps back were taken over the file as it was: undoing one would drop the other writer's change
    return next;
  };

  useEffect(() => {
    const poll = () => { sync().catch(() => {}); };
    const timer = setInterval(poll, 2000);
    window.addEventListener("focus", poll);
    return () => { clearInterval(timer); window.removeEventListener("focus", poll); };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z" && !isTextField(e.target)) {
        e.preventDefault();
        undoRef.current();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    api.rootDir().then(setRoot, (e) => setLoadError(String(e)));
    api.loadSettings().then(async (text) => {
      if (text === null) return setS(newSettings());
      disk.current = text; // read, even when it does not parse: New file then writes over it
      try {
        const { data, migrated, unknown } = parseSettings(text);
        const migratedText = toText(data);
        setS(data);
        setSavedText(migratedText); // dirty = content changed, not formatting; before the write-back, which a poll may meet
        if (migrated && !validate(data).length) {
          try {
            await api.saveSettings(migratedText, text);
            disk.current = migratedText;
          } catch (e) {
            if (!api.isChanged(e)) throw e; // the Agent wrote first: the next poll reads its file
          }
        }
        setStatus(unknown ? TEXT[data.language]["migrate.unknown"].replace("{n}", String(unknown)) : "");
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
        <button type="button" onClick={() => { setLoadError(""); setS(newSettings()); setSavedText(""); }}>{t("newFile")}</button>
      </main>
    );
  }
  if (!s) return null;

  const marked = new Set(checked ? problems.flatMap((p) => p.paths) : []);
  const bad = (path: string) => [...marked].some((m) => m === path || m.startsWith(path + "/"));
  const ctx: Ctx = {
    s, t, bad, giftList,
    chooseList: (id, open) => { setGiftList(id); if (open) setTab("gifts"); },
    update: (fn) => {
      const field = isTextField(document.activeElement) ? document.activeElement : null, now = Date.now();
      const sameTyping = field !== null && field === lastEdit.current.field && now - lastEdit.current.at < 1500;
      lastEdit.current = { at: now, field };
      if (!sameTyping) {
        past.current = [...past.current.slice(1 - UNDO_DEPTH), latest.current.s!];
        setUndoDepth(past.current.length);
      }
      setS((prev) => { const next = structuredClone(prev!); fn(next); return next; });
    },
    tv: (field, v) => TEXT[lang][`${field}.${v}` as Key] ?? v,
  };
  const dirty = toText(s) !== savedText;
  const said = Object.prototype.hasOwnProperty.call(TEXT[lang], status) ? t(status as Key) : status;
  const note = status === "saved" ? "" : said; // shown beside "unsaved" too: a refused save, the file read again
  const blocked = checked && problems.length > 0;
  const state = blocked ? " blocked" : dirty ? " dirty" : status === "saved" ? " saved" : ""; // the dot before the status text

  const save = async () => {
    setChecked(true);
    try {
      for (let tries = 1; ; tries++) {
        const current = (await sync())!; // what another writer changed since goes under the edits first (#501)
        if (validate(current).length) return setStatus("");
        const written = toText(current);
        try {
          await api.saveSettings(written, disk.current);
        } catch (e) {
          if (!api.isChanged(e)) throw e;
          if (tries < 3) continue; // it changed between that read and this write
          return setStatus("saveConflict");
        }
        disk.current = written;
        latest.current = { s: current, savedText: written };
        setSavedText(written);
        return setStatus("saved");
      }
    } catch (e) {
      setStatus(String(e));
    }
  };

  const [, tabLabel, Current] = TABS.find((x) => x[0] === tab)!;
  return (
    <EditorContext.Provider value={ctx}>
      <header>
        <h1>{t("title")}</h1>
        <span className="muted path" title={t("file")}>{root}\config\settings.json</span>
        <span className={"status" + state} role="status">
          {dirty ? [t("unsaved"), note].filter(Boolean).join(" ") : blocked && !said ? t("blocked") : said}
        </span>
        <label className="lang">{t("language")}{" "}
          <select value={s.language} onChange={(e) => ctx.update((d) => { d.language = e.target.value as Settings["language"]; })}>
            <option value="zh_tw">繁體中文</option>
            <option value="en_us">English</option>
          </select>
        </label>
        <button type="button" className="undo" disabled={!undoDepth} title={`${t("undo")} (Ctrl+Z)`} onClick={undo}>
          <Icon name="undo" />{t("undo")}
        </button>
        <button type="button" className="primary" onClick={save}>{t("save")}</button>
      </header>
      <nav role="tablist" aria-label={t("title")}>
        {TABS.map(([id, label, , prefixes]) => (
          <button type="button" role="tab" key={id} id={`tab-${id}`} data-tab={id} aria-selected={tab === id} aria-controls="tabpanel"
            tabIndex={tab === id ? 0 : -1} onKeyDown={tabKeys(TABS.map((x) => x[0]), tab, setTab)}
            className={[tab === id && "selected", GROUP_START.has(id) && "group-start", prefixes.some(bad) && "bad"].filter(Boolean).join(" ")}
            onClick={() => setTab(id)}>{t(label)}<ProblemMark on={prefixes.some(bad)} /></button>
        ))}
      </nav>
      {/* Keyed by tab: a tab opens at its top, not at the scroll position the last tab left. A refused save's problems open the
        tab, under the tab bar, so the frame above never moves; the tab bar's dots show which tabs hold them. */}
      <main key={tab} id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        <h2 className="sr-only">{t(tabLabel)}</h2>
        {blocked && (
          <div className="problems" role="alert">
            <p>{t("saveBlocked")}</p>
            <ul>{problems.map((p, i) => <li key={i}>{p.text}</li>)}</ul>
          </div>
        )}
        <Current />
      </main>
    </EditorContext.Provider>
  );
}

function RunTab() {
  const { s, update, t, tv, bad } = useEditor();
  const run = s.run;
  const pastFive = run.target_floor > 5;
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  const pick = (k: "difficulty" | "weekly_bonus_use" | "weekly_bonus_amount" | "starlight_unaffordable" | "after_retries" | "theme_pack_refresh", note?: string) => (
    <Field label={t(`run.${k}`)} path={`run/${k}`} note={note}>
      <Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />
    </Field>
  );
  // Four groups, each a card of label | control rows: the run itself, the weekly bonuses, a wipe or a failure, the screens the bot
  // answers on its own.
  return (
    <>
      <fieldset>
        <legend>{t("run.group_run")}</legend>
        <div className="rows">
          {pick("difficulty")}
          <Field label={t("run.target_floor")} path="run/target_floor" note={pastFive ? t("run.target_floor_note") : undefined}>
            <Select value={String(run.target_floor)} options={runEnum("target_floor").map(String)} label={(v) => tv("target_floor", v)} onChange={(v) => set({ target_floor: Number(v) })} />
            {/* Remove with #434: until the entrance switches Parallel Superposition on, a target above 5 still stops at floor 5. */}
            {pastFive && <small>{t("run.target_floor_entry_note")}</small>}
          </Field>
          <ToggleNum label={t("run.runs")} path="run/runs" value={run.runs} on={1} min={1} note={t("run.runs_note")}
            onChange={(v) => set({ runs: v })} />
          {pick("theme_pack_refresh", t("run.theme_pack_refresh_note"))}
          {pick("starlight_unaffordable")}
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_weekly")}</legend>
        <div className="rows">
          {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
          {pick("weekly_bonus_amount")}
          <label className={"check" + (bad("run/stop_when_weekly_bonus_out") ? " bad" : "")}>
            <input type="checkbox" checked={run.stop_when_weekly_bonus_out} onChange={(e) => set({ stop_when_weekly_bonus_out: e.target.checked })} />
            {t("run.stop_when_weekly_bonus_out")}
          </label>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_failure")}</legend>
        <div className="rows">
          <Field label={t("run.wipe_retries")} path="run/wipe_retries"><Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} /></Field>
          {pick("after_retries")}
          <Field label={t("run.webhook_url")} path="run/webhook_url">
            <input type="url" value={run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />
          </Field>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_screens")}</legend>
        <div className="rows">
          {(["auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const).map((k) => (
            <label key={k} className={"check" + (bad(`run/${k}`) ? " bad" : "")}>
              <input type="checkbox" checked={run[k]} onChange={(e) => set({ [k]: e.target.checked })} />
              {t(`run.${k}`)}
            </label>
          ))}
        </div>
      </fieldset>
    </>
  );
}

/** The daily tasks' options (#362); the client's task list picks and orders the tasks. */
function DailyTab() {
  const { t } = useEditor();
  return (
    <>
      <p className="muted">{withBreaks(t("daily.note"))}</p>
      <LuxFields task="exp" />
      <LuxFields task="thread" />
      <ChargeFields />
    </>
  );
}

function ChargeFields() {
  const { s, update, t } = useEditor();
  return (
    <fieldset>
      <legend>{t("charge.title")}</legend>
      <p className="caution">{withBreaks(t("charge.note"))}</p>
      <div className="rows">
        <Field label={t("charge.count")} path="charge_enkephalin/count">
          <Num value={s.charge_enkephalin.count} min={0} onChange={(v) => update((d) => { d.charge_enkephalin.count = v; })} />
        </Field>
      </div>
    </fieldset>
  );
}

function LuxFields({ task }: { task: keyof Settings["luxcavation"] }) {
  const { s, update, t, tv, bad } = useEditor();
  const opts = s.luxcavation[task];
  const set = (patch: Partial<Luxcavation>) => update((d) => { Object.assign(d.luxcavation[task], patch); });
  const path = `luxcavation/${task}`;
  return (
    <fieldset>
      <legend>{t(`lux.${task}`)}</legend>
      <p className="muted">{withBreaks(t(`lux.${task}_note`))}</p>
      <div className="rows">
        <Field label={t("lux.mode")} path={`${path}/mode`}>
          <Select value={opts.mode} options={LUX_MODES} label={(v) => tv("lux_mode", v)} onChange={(v) => set({ mode: v as LuxMode })} />
        </Field>
        <Field label={t("lux.count")} path={`${path}/count`} note={opts.mode === "daily" ? t("lux.count_unused") : undefined}>
          <Num value={opts.count} min={1} disabled={opts.mode === "daily"} onChange={(v) => set({ count: v })} />
        </Field>
        <Field label={t("lux.team")} path={`${path}/team`} note={t("lux.team_note")}>
          <Select value={opts.team ?? ""} options={["", ...s.teams.map((x) => x.id)]}
            label={(id) => { const x = s.teams.find((x) => x.id === id); return x ? `${x.name || "—"} (#${x.game_team})` : t("lux.team_none"); }}
            onChange={(v) => set({ team: v || null })} />
        </Field>
        {/* A switch sits in the label column, as on the other tabs. */}
        <div className={"toggle" + (bad(`${path}/consecutive`) ? " bad" : "")}>
          <label className="check">
            <input type="checkbox" checked={opts.consecutive} onChange={(e) => set({ consecutive: e.target.checked })} />
            {t("lux.consecutive")}
          </label>
          <small>{withBreaks(t("lux.consecutive_note"))}</small>
        </div>
        <Field label={t("lux.retries")} path={`${path}/retries`} note={t("lux.retries_note")}>
          <Num value={opts.retries} min={0} onChange={(v) => set({ retries: v })} />
        </Field>
      </div>
    </fieldset>
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
    <div className="card">
      {rows.length ? (
        <table className="overrides">
          <thead><tr>{cols.map((c) => <th key={c.key}>{t(c.label)}</th>)}<th /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c.key} className={bad(`${listKey}/${i}/${c.key}`) ? "bad" : ""}>
                    {c.number
                      ? <Decimal value={r[c.key] as number} min={0} onChange={(v) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = v; })} />
                      : <input value={r[c.key] as string} onChange={(e) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = e.target.value; })} />}
                  </td>
                ))}
                <td><button type="button" className="danger" onClick={() => set((l) => { l.splice(i, 1); })}>{t("remove")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">{t("noRows")}</p>}
      <button type="button" className="add" onClick={() => set((l) => { l.push({ ...blank }); })}>+ {t("add")}</button>
    </div>
  );
}

function EventsTab() {
  return <OverrideTable listKey="event_overrides" blank={{ question: "", option: "" }}
    cols={[{ key: "question", label: "event.question" }, { key: "option", label: "event.option" }]} />;
}

function TrialsTab() {
  const { t } = useEditor();
  return (
    <>
      <p className="muted">{withBreaks(t("trial.note"))}</p>
      <OverrideTable listKey="trial_risk_overrides" blank={{ trial: "", risk: 1 }}
        cols={[{ key: "trial", label: "trial.trial" }, { key: "risk", label: "trial.risk", number: true }]} />
    </>
  );
}
