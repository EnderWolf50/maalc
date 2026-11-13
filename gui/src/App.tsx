// Shell: load <root>/config/settings.json, the tabs, and check-then-save (spec 04 section 2).
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api";
import { TEXT, fill, type Key } from "./i18n";
import { LUX_MODES, newSettings, parseSettings, rebase, runEnum, type Luxcavation, type LuxMode, type Settings } from "./model";
import { DeploymentTab, StarlightTab, ThemePackTab } from "./Plans";
import { GiftListsTab } from "./GiftLists";
import { TeamsTab } from "./Teams";
import { Group, Note, Rail, Row, ToggleRow, useRailCompact } from "./frame";
import {
  Decimal, EditorContext, GLYPHS, Icon, Num, Select, focusPath, isPickList, makeCtx, translate, useEditor, type Picked,
} from "./ui";
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
type TabId = (typeof TABS)[number][0];

/** The rail's groups, by job: what to run, teams and plans, overrides, daily tasks. A group of one page needs no header. */
const NAV: { label?: Key; tabs: TabId[] }[] = [
  { tabs: ["run"] },
  { label: "nav.teams", tabs: ["teams", "gifts", "deployment", "starlight", "themepacks"] },
  { label: "nav.overrides", tabs: ["events", "trials"] },
  { tabs: ["daily"] },
];
/** Each page's icon in the rail (Segoe Fluent Icons). */
const PAGE_GLYPH: Record<TabId, number> = {
  run: 0xe9e9, teams: 0xe716, gifts: 0xf133, deployment: 0xe8cb, starlight: 0xe734, themepacks: 0xe81e, events: 0xe8f2,
  trials: 0xec4a, daily: 0xe787,
};

/** The Windows accent colour on the page, when the app can read it; the stylesheet derives the light and dark shades. */
function useSystemAccent() {
  useEffect(() => {
    api.accentColor().then((c) => { if (c) document.documentElement.style.setProperty("--sys-accent", c); }, () => {});
  }, []);
}

const toText = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
/** The tab that edits a settings path ("teams/1/name"), if any ("(root)" has none). */
const tabOf = (path: string) => TABS.find((x) => (x[3] as readonly string[]).includes(path.split("/")[0]));

export default function App() {
  const [s, setS] = useState<Settings | null>(null);
  const [savedText, setSavedText] = useState("");
  const [loadError, setLoadError] = useState("");
  const [root, setRoot] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("teams");
  const [giftList, setGiftList] = useState("default"); // what the gift list tab shows; the teams tab can point it at a list
  const [compact, setCompact] = useRailCompact();
  const [picked, setPicked] = useState<Picked>({});
  const [jump, setJump] = useState<string | null>(null); // the path of the problem the user clicked
  const [checked, setChecked] = useState(false); // a save was tried and refused: the banner and the title bar's count show
  const [status, setStatus] = useState(""); // a TEXT key, or text as it is (an error, the gift ids a load dropped)
  // The file's text as last read or written: other text there is another writer's, the Agent's after a claim (#501).
  const disk = useRef<string | null>(null);
  const latest = useRef({ s, savedText });
  latest.current = { s, savedText };
  useSystemAccent();

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
    return next;
  };

  useEffect(() => {
    const poll = () => { sync().catch(() => {}); };
    const timer = setInterval(poll, 2000);
    window.addEventListener("focus", poll);
    return () => { clearInterval(timer); window.removeEventListener("focus", poll); };
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

  // Ctrl+S is the Save button, in a field too; the browser's own Save page never opens.
  const saveRef = useRef(() => {});
  saveRef.current = () => {}; // until this render has a save to offer: none on the load error screen
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // an input method can report the key as "Process": then its place on the keyboard says it is S
      const s = e.key === "Process" ? e.code === "KeyS" : e.key.toLowerCase() === "s";
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey || !s) return;
      e.preventDefault();
      if (!e.repeat) saveRef.current(); // held down: one save, not one per repeat
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A clicked problem's field, focused once its tab and its team or plan are on screen.
  useEffect(() => {
    if (jump === null) return;
    setJump(null);
    focusPath(jump);
  }, [jump]);

  const problems: Problem[] = useMemo(() => (s ? validate(s) : []), [s]);
  const lang = s?.language ?? "zh_tw";
  const { t } = translate(lang);

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

  // The marks (the rail's dot, the red field, the list's dot) show as soon as an edit makes a problem; the banner and the
  // title bar's count wait for a save.
  const marked = new Set(problems.flatMap((p) => p.paths));
  const bad = (path: string) => [...marked].some((m) => m === path || m.startsWith(path + "/"));
  const ctx = makeCtx({
    s, bad, giftList, picked, setPicked,
    setS: (next) => setS((prev) => next(prev!)),
    chooseList: (id, open) => { setGiftList(id); if (open) setTab("gifts"); },
    openTab: (id) => { if (TABS.some((x) => x[0] === id)) setTab(id as TabId); },
  });
  const dirty = toText(s) !== savedText;
  const said = Object.prototype.hasOwnProperty.call(TEXT[lang], status) ? t(status as Key) : status;
  const note = status === "saved" ? "" : said; // shown beside "unsaved" too: a refused save, the file read again

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
        setChecked(false); // saved: a problem made later shows its marks, and the banner waits for the next save
        return setStatus("saved");
      }
    } catch (e) {
      setStatus(String(e));
    }
  };
  saveRef.current = save;

  /** Back to the file as last read or written: every unsaved edit goes, after a confirm. */
  const revert = () => {
    if (!confirm(t("revertConfirm"))) return;
    setS(savedText ? JSON.parse(savedText) : newSettings());
    setChecked(false);
    setStatus("");
  };

  /** Show where a problem points: its tab and the team, plan or gift list it names; the effect above then focuses its field. */
  const goTo = (path: string) => {
    const [section, index] = path.split("/");
    const at = Number(index);
    if (section === "gift_lists" && s.gift_lists[at]) setGiftList(s.gift_lists[at].id);
    else if (isPickList(section) && s[section][at]) ctx.pick(section, s[section][at].id);
    setTab(tabOf(path)![0]);
    setJump(path);
  };

  const [, label, Current] = TABS.find((x) => x[0] === tab)!;
  const groups = NAV.map((g) => ({
    label: g.label,
    items: g.tabs.map((id) => {
      const [, name, , prefixes] = TABS.find((x) => x[0] === id)!;
      return { id, label: t(name), glyph: PAGE_GLYPH[id], bad: prefixes.some(bad) };
    }),
  }));
  const blocked = checked && problems.length > 0; // a refused save says so beside the button that caused it
  const state = blocked ? "blocked" : dirty ? "dirty" : status === "saved" ? "ok" : "";
  return (
    <EditorContext.Provider value={ctx}>
      <header>
        <button type="button" className="subtle nav-toggle" aria-label={t("nav.toggle")} title={t("nav.toggle")} aria-expanded={!compact}
          onClick={() => setCompact(!compact)}><Icon glyph={GLYPHS.menu} /></button>
        <h1>{t("title")}</h1>
        <span className="path" title={t("file")}>{root}\config\settings.json</span>
        <span className={"status" + (state ? " " + state : "")} aria-live="polite">{blocked
          ? fill(t("blockedCount"), { n: problems.length }) : dirty ? [t("unsaved"), note].filter(Boolean).join(" ") : said}</span>
        {dirty && <button type="button" className="subtle" onClick={revert}><Icon glyph={GLYPHS.reset} />{t("revert")}</button>}
        <label className="lang" title={t("language")}><Icon glyph={GLYPHS.language} /><span className="sr-only">{t("language")}</span>
          <select value={s.language} onChange={(e) => ctx.update((d) => { d.language = e.target.value as Settings["language"]; })}>
            <option value="zh_tw">繁體中文</option>
            <option value="en_us">English</option>
          </select>
        </label>
        <button type="button" className={"primary" + (dirty ? " dirty" : "")} onClick={save}><Icon glyph={GLYPHS.save} />{t("save")}</button>
      </header>
      <Rail groups={groups} current={tab} onPick={setTab} label={t("nav.label")} compact={compact} />
      <main aria-labelledby="page-title">
        <h2 className="page-title" id="page-title">{t(label)}</h2>
        {checked && problems.length > 0 && (
          <div className="problems" role="alert">
            <Icon glyph={GLYPHS.error} />
            <div>
              <p>{t("saveBlocked")}</p>
              <ul>{problems.map((p, i) => (
                <li key={i}>{tabOf(p.paths[0]) ? <button type="button" onClick={() => goTo(p.paths[0])}>{p.text}</button> : p.text}</li>
              ))}</ul>
            </div>
          </div>
        )}
        <Current />
      </main>
    </EditorContext.Provider>
  );
}

function RunTab() {
  const { s, update, t, tv } = useEditor();
  const run = s.run;
  const pastFive = run.target_floor > 5;
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  const pick = (k: "difficulty" | "weekly_bonus_use" | "weekly_bonus_amount" | "starlight_unaffordable" | "after_retries" | "theme_pack_refresh", note?: string) => (
    <Row label={t(`run.${k}`)} path={`run/${k}`} note={note}
      control={<Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />} />
  );
  const check = (k: "stop_when_weekly_bonus_out" | "auto_accept_terms" | "auto_download" | "keep_dismissed_screens") => (
    <Row key={k} label={t(`run.${k}`)} path={`run/${k}`}
      check={<input type="checkbox" className="switch" checked={run[k]} onChange={(e) => set({ [k]: e.target.checked })} />} />
  );
  // Grouped by what the player decides: the goal, the weekly bonuses, the choices inside a run, failures, the screens on the way.
  return (
    <div className="settings">
      <Group title={t("run.sec_goal")}>
        {pick("difficulty")}
        <Row label={t("run.target_floor")} path="run/target_floor" note={pastFive ? t("run.target_floor_note") : undefined}
          control={<Select value={String(run.target_floor)} options={runEnum("target_floor").map(String)} label={(v) => tv("target_floor", v)} onChange={(v) => set({ target_floor: Number(v) })} />}>
          {/* Remove with #434: until the entrance switches Parallel Superposition on, a target above 5 still stops at floor 5. */}
          {pastFive && <small>{t("run.target_floor_entry_note")}</small>}
        </Row>
        <ToggleRow label={t("run.runs")} path="run/runs" value={run.runs} on={1} min={1} note={t("run.runs_note")}
          onChange={(v) => set({ runs: v })} />
      </Group>
      <Group title={t("run.sec_weekly")}>
        {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
        {pick("weekly_bonus_amount")}
        {check("stop_when_weekly_bonus_out")}
      </Group>
      <Group title={t("run.sec_in_run")}>
        {pick("starlight_unaffordable")}
        {pick("theme_pack_refresh", t("run.theme_pack_refresh_note"))}
      </Group>
      <Group title={t("run.sec_failure")}>
        <Row label={t("run.wipe_retries")} path="run/wipe_retries" control={<Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} />} />
        {pick("after_retries")}
        <Row label={t("run.webhook_url")} path="run/webhook_url"
          control={<input type="url" className="wide" placeholder="https://" value={run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />} />
      </Group>
      <Group title={t("run.sec_screens")}>
        {(["auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const).map(check)}
      </Group>
    </div>
  );
}

/** The daily tasks' options (#362); the client's task list picks and orders the tasks. */
function DailyTab() {
  const { t } = useEditor();
  return (
    <div className="settings">
      <Note text={t("daily.note")} block />
      <LuxFields task="exp" />
      <LuxFields task="thread" />
      <ChargeFields />
    </div>
  );
}

function ChargeFields() {
  const { s, update, t } = useEditor();
  return (
    <Group title={t("charge.title")}>
      <Note text={t("charge.note")} block />
      <Row label={t("charge.count")} path="charge_enkephalin/count"
        control={<Num value={s.charge_enkephalin.count} min={0} onChange={(v) => update((d) => { d.charge_enkephalin.count = v; })} />} />
    </Group>
  );
}

function LuxFields({ task }: { task: keyof Settings["luxcavation"] }) {
  const { s, update, t, tv } = useEditor();
  const opts = s.luxcavation[task];
  const set = (patch: Partial<Luxcavation>) => update((d) => { Object.assign(d.luxcavation[task], patch); });
  const path = `luxcavation/${task}`;
  return (
    <Group title={t(`lux.${task}`)}>
      <Note text={t(`lux.${task}_note`)} block />
      <Row label={t("lux.mode")} path={`${path}/mode`}
        control={<Select value={opts.mode} options={LUX_MODES} label={(v) => tv("lux_mode", v)} onChange={(v) => set({ mode: v as LuxMode })} />} />
      <Row label={t("lux.count")} path={`${path}/count`} note={opts.mode === "daily" ? t("lux.count_unused") : undefined}
        control={<Num value={opts.count} min={1} disabled={opts.mode === "daily"} onChange={(v) => set({ count: v })} />} />
      <Row label={t("lux.team")} path={`${path}/team`} note={t("lux.team_note")}
        control={<Select value={opts.team ?? ""} options={["", ...s.teams.map((x) => x.id)]}
          label={(id) => { const x = s.teams.find((x) => x.id === id); return x ? `${x.name || "—"} (#${x.game_team})` : t("lux.team_none"); }}
          onChange={(v) => set({ team: v || null })} />} />
      <Row label={t("lux.consecutive")} path={`${path}/consecutive`} note={t("lux.consecutive_note")}
        check={<input type="checkbox" className="switch" checked={opts.consecutive} onChange={(e) => set({ consecutive: e.target.checked })} />} />
      <Row label={t("lux.retries")} path={`${path}/retries`} note={t("lux.retries_note")}
        control={<Num value={opts.retries} min={0} onChange={(v) => set({ retries: v })} />} />
    </Group>
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
                  <td key={c.key} className={bad(`${listKey}/${i}/${c.key}`) ? "bad" : ""} data-path={`${listKey}/${i}/${c.key}`}>
                    {c.number
                      ? <Decimal label={`${t(c.label)} ${i + 1}`} value={r[c.key] as number} min={0} onChange={(v) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = v; })} />
                      : <input aria-label={`${t(c.label)} ${i + 1}`} value={r[c.key] as string} onChange={(e) => set((l) => { (l[i] as Record<string, unknown>)[c.key] = e.target.value; })} />}
                  </td>
                ))}
                <td className="act">
                  <button type="button" className="subtle danger" aria-label={`${t("remove")} ${i + 1}`} title={t("remove")}
                    onClick={() => set((l) => { l.splice(i, 1); })}><Icon glyph={GLYPHS.remove} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="empty-note">{t("noRows")}</p>}
      <button type="button" className="add" onClick={() => set((l) => { l.push({ ...blank }); })}>+ {t("add")}</button>
    </>
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
      <Note text={t("trial.note")} block />
      <OverrideTable listKey="trial_risk_overrides" blank={{ trial: "", risk: 1 }}
        cols={[{ key: "trial", label: "trial.trial" }, { key: "risk", label: "trial.risk", number: true }]} />
    </>
  );
}
