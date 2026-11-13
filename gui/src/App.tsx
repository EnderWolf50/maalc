// Shell: load <root>/config/settings.json, the tabs, and check-then-save (spec 04 section 2).
import { Fragment, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import * as api from "./api";
import { TEXT, fill, type Key } from "./i18n";
import { LUX_MODES, newSettings, parseSettings, rebase, runEnum, type Luxcavation, type LuxMode, type Settings } from "./model";
import { DeploymentTab, StarlightTab, ThemePackTab } from "./Plans";
import { GiftListsTab } from "./GiftLists";
import { TeamsTab } from "./Teams";
import {
  Decimal, EditorContext, Field, Input, Mark, Num, Select, ToggleNum, focusPath, nextTab, isPickList, makeCtx, translate, useEditor,
  useUndoRow, withBreaks,
  type Picked,
} from "./ui";
import { sayProblem, validate, type Problem } from "./validate";

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

/** The tabs in groups (what a run plays with, the plans, the overrides, the daily tasks): the tabs that start a group. */
const GROUP_STARTS = new Set<TabId>(["deployment", "events", "daily"]);

/** What the prompt guards: the window closes, or the page reloads (F5, Ctrl+R). */
type Leave = "close" | "reload";
const toText = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
/** The element id of the problem at this place in the problems block. */
const problemId = (i: number) => `problem-${i}`;
/** The tab that edits a settings path ("teams/1/name"), if any ("(root)" has none). */
const tabOf = (path: string) => TABS.find((x) => (x[3] as readonly string[]).includes(path.split("/")[0]));
/** A problem across edits: its kind and the fields it marks, not its words, which name what the user is typing. */
const problemKey = (p: Problem) => `${p.say.key} ${p.paths.join(" ")}`;
/** The controls a value is typed into, not picked from (a select, a switch, a drag). */
const TYPED = new Set(["text", "search", "url", "email", "tel", "password", "number"]);
const typesText = (el: EventTarget) => el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && TYPED.has(el.type));

export default function App() {
  const [s, setS] = useState<Settings | null>(null);
  const [savedText, setSavedText] = useState("");
  const [loadError, setLoadError] = useState("");
  const [root, setRoot] = useState("");
  const [tab, setTab] = useState<TabId>("teams");
  const [giftList, setGiftList] = useState("default"); // what the gift list tab shows; the teams tab can point it at a list
  const [picked, setPicked] = useState<Picked>({});
  const [jump, setJump] = useState<string | null>(null); // the path of the problem the user clicked
  // While a field is typed in: the problems (problemKey) that showed before its last keystroke. A problem the typing makes
  // waits until the field loses focus, or a save is tried; null: every problem shows (#717).
  const [typing, setTyping] = useState<Set<string> | null>(null);
  const [status, setStatus] = useState(""); // a TEXT key, or text as it is (an error, the gift ids a load dropped)
  const [failed, setFailed] = useState(false); // the last save did not write the file (a conflict or an error)
  const [refused, setRefused] = useState(false); // the last save stopped at the checks, and its problems are not all fixed
  // The window was closed, or the page asked to reload (F5, Ctrl+R), with unsaved changes: the prompt for that shows (#695, #702).
  const [asking, setAsking] = useState<false | Leave>(false);
  const [maximized, setMaximized] = useState(false); // the window fills the screen: the title bar offers Restore
  // The edits Revert dropped: Undo puts them back while the editor still holds the file's settings.
  const [revertedFrom, setRevertedFrom] = useState<Settings | null>(null);
  // The file's text as last read or written: other text there is another writer's, the Agent's after a claim (#501).
  const disk = useRef<string | null>(null);
  const latest = useRef({ s, savedText });
  latest.current = { s, savedText };

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

  // Closing the window with unsaved changes asks first; with none it closes.
  const focusBefore = useRef<Element | null>(null); // what had the focus when the prompt opened: it gets it back when the prompt goes
  const unsaved = () => { const { s, savedText } = latest.current; return s !== null && toText(s) !== savedText; };
  const ask = (kind: Leave) => {
    focusBefore.current ??= document.activeElement; // now: the page behind the prompt goes inert, which takes the focus away
    setAsking((was) => (kind === "close" ? kind : was || kind)); // a close outranks a reload; a reload keeps the prompt that shows
  };
  useEffect(() => api.onCloseRequested(() => {
    const keep = unsaved();
    if (keep) ask("close");
    return keep;
  }), []);
  // F5 and Ctrl+R would reload the page and drop the edits (WebView2 keeps the browser's keys on). With unsaved changes the
  // prompt asks first; with none the key is left alone and the browser reloads (#702).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // a key that types no Latin letter (an input method's "Process", a Russian "к") is told by its place on the keyboard
      const r = /^[a-z]$/i.test(e.key) ? e.key.toLowerCase() === "r" : e.code === "KeyR";
      const reload = e.key === "F5" || e.key === "BrowserRefresh" || ((e.ctrlKey || e.metaKey) && r);
      if (!reload || e.altKey || !unsaved()) return;
      e.preventDefault();
      ask("reload");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => api.onMaximized(setMaximized), []);
  useEffect(() => {
    if (asking || !focusBefore.current) return;
    (focusBefore.current as HTMLElement).focus?.();
    focusBefore.current = null;
  }, [asking]);

  // A clicked problem's field, focused once its tab and its team or plan are on screen.
  useEffect(() => {
    if (jump === null) return;
    setJump(null);
    focusPath(jump);
  }, [jump]);

  const problems: Problem[] = useMemo(() => (s ? validate(s) : []), [s]);
  // what the marks, the tab markers, the problems block and the save plate show; a fix shows at once, typing or not
  const shown = typing ? problems.filter((p) => typing.has(problemKey(p))) : problems;
  useEffect(() => { if (!problems.length) setRefused(false); }, [problems.length]);
  const lang = s?.language ?? "zh_tw";
  const { t } = translate(lang);

  // The title bar alone, before the settings are read and when they do not read: the window has no system bar to fall back on.
  const bare = (
    <header data-tauri-drag-region="deep">
      <h1>{t("title")}</h1>
      <span className="path" />
      <WindowButtons t={t} maximized={maximized} onError={(e) => setLoadError((why) => (why ? `${why}\n${String(e)}` : String(e)))} />
    </header>
  );
  if (loadError) {
    return (<>
      {bare}
      <main className="load-error">
        <p>{t("loadError")}</p>
        <pre>{loadError}</pre>
        <div className="row">
          <button type="button" onClick={() => { setLoadError(""); setS(newSettings()); setSavedText(""); }}>{t("newFile")}</button>
          <button type="button" onClick={() => { api.requestClose().catch(() => {}); }}>{t("win.close")}</button>
        </div>
      </main>
    </>);
  }
  if (!s) return bare;

  // a marked field's controls are described by the problems' text (#695)
  const problemIds = (path: string) => shown
    .flatMap((p, i) => (p.paths.some((m) => m === path || m.startsWith(path + "/")) ? [problemId(i)] : [])).join(" ");
  const ctx = makeCtx({
    s, problemIds, giftList, picked, setPicked,
    // any edit makes the edits that the revert (放棄變更) dropped no longer the newest: its Undo goes
    setS: (next) => { setRevertedFrom(null); setS((prev) => next(prev!)); },
    chooseList: (id, open) => { setGiftList(id); if (open) setTab("gifts"); },
  });
  const dirty = toText(s) !== savedText;
  const said = Object.prototype.hasOwnProperty.call(TEXT[lang], status) ? t(status as Key) : status;
  // shown beside "unsaved" too (a refused save, the file read again), but not what an edit since has made stale
  const note = status === "saved" || status === "reverted" ? "" : said;

  /** Check, then write; true when the file holds the edits. */
  const save = async () => {
    setTyping(null); // a save tried shows every problem, also one still being typed (Ctrl+S in the field)
    setFailed(false);
    setRefused(false);
    try {
      for (let tries = 1; ; tries++) {
        const current = (await sync())!; // what another writer changed since goes under the edits first (#501)
        if (validate(current).length) {
          setRefused(true);
          setStatus("");
          return false;
        }
        const written = toText(current);
        try {
          await api.saveSettings(written, disk.current);
        } catch (e) {
          if (!api.isChanged(e)) throw e;
          if (tries < 3) continue; // it changed between that read and this write
          setFailed(true);
          setStatus("saveConflict");
          return false;
        }
        disk.current = written;
        latest.current = { s: current, savedText: written };
        setSavedText(written);
        setStatus("saved");
        return true;
      }
    } catch (e) {
      setFailed(true);
      setStatus(String(e));
      return false;
    }
  };
  saveRef.current = asking ? () => {} : save; // while the close prompt asks, its buttons decide

  /** The window closes; a failed close (no permission to) says why, and the editor stays as it was. */
  const close = () => api.closeWindow().catch((e) => setStatus(String(e)));
  /** What the prompt's Save and Discard end with: the window closes or the page loads again. */
  const leave = async (kind: Leave) => { if (kind === "close") await close(); else api.reloadPage(); };
  const leavePrompt = asking && (
    <LeavePrompt kind={asking} onCancel={() => setAsking(false)}
      onSave={async () => { setAsking(false); if (await save()) await leave(asking); }}
      onDiscard={() => { setAsking(false); leave(asking); }} />
  );

  /** Back to the file's settings, every unsaved edit dropped; Undo, beside the plate, brings them back until the next edit. */
  const revert = () => {
    setRevertedFrom(s);
    setS(JSON.parse(savedText) as Settings);
    setFailed(false);
    setStatus("reverted");
  };
  const undoRevert = () => {
    setS(revertedFrom);
    setRevertedFrom(null);
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

  const Current = TABS.find((x) => x[0] === tab)![2];
  // The save state plate: problems to fix (a refused save, or problems a save would meet), a write that failed, unsaved,
  // saved, or a note. Save takes the crimson frame while problems stop it or after a write failed, the caution stripe while
  // unsaved changes can go through. It counts the problems the fields show, so it waits for a field being typed in too.
  const state = shown.length ? "blocked" : failed ? "failed" : dirty ? "dirty" : status === "saved" ? "saved" : said ? "note" : "clean";
  const stateText = [
    shown.length > 0 && fill(t(refused ? "saveState.refused" : "saveState.toFix"), { n: shown.length }),
    dirty ? [t("unsaved"), note].filter(Boolean).join(" ") : said || (!shown.length && t("saveState.clean")),
  ].filter(Boolean).join(" · ");
  const saveLook = state === "blocked" || state === "failed" ? " refused" : state === "dirty" ? " armed" : "";
  const canRevert = dirty && savedText !== ""; // a file to go back to: a new one has none
  const canUndoRevert = status === "reverted" && revertedFrom !== null && !dirty;
  /** Arrow keys walk the tabs and open the one they reach (they are cheap to draw); Home and End go to the ends. */
  const walkTabs = (e: ReactKeyboardEvent) => {
    const next = nextTab(TABS.map((x) => x[0]), tab, e.key);
    if (!next) return;
    e.preventDefault();
    setTab(next);
    document.getElementById(`tab-${next}`)?.focus();
  };
  return (
    <EditorContext.Provider value={ctx}>
      {/* The title bar too: the system's is hidden (tauri.conf.json). Tauri drags the window from any of its parts that is not a
          control (drag.js "deep"), and a double click there maximises it. */}
      <header inert={!!asking} data-tauri-drag-region="deep">
        <h1>{t("title")}</h1>
        <span className="muted path" title={`${root}\\config\\settings.json`}>{root}\config\settings.json</span>
        <label className="lang">{t("language")}
          <select value={s.language} onChange={(e) => ctx.update((d) => { d.language = e.target.value as Settings["language"]; })}>
            <option value="zh_tw">繁體中文</option>
            <option value="en_us">English</option>
          </select>
        </label>
        <span className="status" data-state={state} aria-live="polite">{stateText}</span>
        {canRevert && <button type="button" className="quiet" title={t("revert.note")} onClick={revert}>{t("revert")}</button>}
        {canUndoRevert && <button type="button" className="quiet" onClick={undoRevert}>{t("undo")}</button>}
        <button type="button" className={"primary" + saveLook} onClick={save}>{t("save")}</button>
        <WindowButtons t={t} maximized={maximized} onError={(e) => setStatus(String(e))} />
      </header>
      <nav role="tablist" onKeyDown={walkTabs} inert={!!asking}>
        {TABS.map(([id, label, , prefixes]) => (
          <Fragment key={id}>
            {GROUP_STARTS.has(id) && <span className="tabsep" aria-hidden />}
            <button type="button" role="tab" id={`tab-${id}`} data-tab={id} aria-selected={tab === id} aria-controls="tabpanel"
              tabIndex={tab === id ? 0 : -1} className={(tab === id ? "selected" : "") + (prefixes.some(ctx.bad) ? " bad" : "")}
              onClick={() => setTab(id)}>{t(label)}</button>
          </Fragment>
        ))}
      </nav>
      {/* A keystroke in the focused field (onChange runs after the field's own, in one render) keeps what shows now: half a
          word does not turn red. Leaving the field shows what waited. A select, a switch or a drag marks at once. */}
      <main inert={!!asking}
        onChange={(e) => { if (e.target === document.activeElement && typesText(e.target)) setTyping(new Set(shown.map(problemKey))); }}
        onBlur={() => setTyping(null)}>
        <div id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {/* the page's heading under the window's: the tab's name, for a screen reader's list of headings */}
          <h2 className="sr-only">{t(TABS.find((x) => x[0] === tab)![1])}</h2>
          {/* in the tab panel, so the tab bar stays where it is when problems come and go */}
          {shown.length > 0 && (
            <div className="problems" role="alert">
              <p>{t("saveBlocked")}</p>
              <ul>{shown.map((p, i) => (
                // the editor's words; the bot's own (English) text stays on hover, as the log and a bug report have it
                <li key={i} id={problemId(i)} title={p.text}>
                  {tabOf(p.paths[0]) ? <button type="button" onClick={() => goTo(p.paths[0])}>{sayProblem(p, lang)}</button> : sayProblem(p, lang)}
                </li>
              ))}</ul>
            </div>
          )}
          <Current />
        </div>
      </main>
      {leavePrompt}
    </EditorContext.Provider>
  );
}

/** The window's own buttons at the title bar's right end. Close is a close request, as Alt+F4 is: with unsaved changes the
 * prompt asks first. A call the window refuses (no permission) says why in the save state, as a failed close does. */
function WindowButtons({ t, maximized, onError }: { t: (k: Key) => string; maximized: boolean; onError: (e: unknown) => void }) {
  const button = (name: string, run: () => Promise<void>, glyph: ReactNode, className?: string) => (
    <button type="button" className={className} aria-label={name} title={name} onClick={() => { run().catch(onError); }}>
      <svg viewBox="0 0 10 10" aria-hidden="true">{glyph}</svg>
    </button>
  );
  return (
    <div className="winctl">
      {button(t("win.minimize"), api.minimizeWindow, <path d="M0 5.5h10" />)}
      {button(t(maximized ? "win.restore" : "win.maximize"), api.toggleMaximize, maximized
        ? <path d="M2.5 2.5V.5h7v7h-2M.5 2.5h7v7h-7z" />
        : <rect x="0.5" y="0.5" width="9" height="9" />)}
      {button(t("win.close"), api.requestClose, <path d="M0 0l10 10M10 0L0 10" />, "close")}
    </div>
  );
}

/** Asked when the window closes, or the page reloads (F5, Ctrl+R), with unsaved changes: save and go on, go on without saving,
 * or stay (Esc). The focus starts on the choice that keeps the edits. */
function LeavePrompt({ kind, onSave, onDiscard, onCancel }: {
  kind: Leave; onSave: () => void; onDiscard: () => void; onCancel: () => void;
}) {
  const { t } = useEditor();
  const cancel = useRef(onCancel);
  cancel.current = onCancel;
  useEffect(() => {
    // from the document: a click on the dimmed page behind takes the focus out of the prompt
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") cancel.current(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="ask-back">
      <div className="ask" role="alertdialog" aria-modal="true" aria-labelledby="close-ask">
        <p id="close-ask">{t(`${kind}Ask`)}</p>
        <div className="ask-buttons">
          <button type="button" className="primary" autoFocus onClick={onSave}>{t(`${kind}Save`)}</button>
          <button type="button" className="danger" onClick={onDiscard}>{t(`${kind}Discard`)}</button>
          <button type="button" onClick={onCancel}>{t("cancel")}</button>
        </div>
      </div>
    </div>
  );
}

function RunTab() {
  const { s, update, t, tv } = useEditor();
  const run = s.run;
  const pastFive = run.target_floor > 5;
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  const pick = (k: "difficulty" | "weekly_bonus_use" | "weekly_bonus_amount" | "starlight_unaffordable" | "after_retries" | "theme_pack_refresh", note?: string) => (
    <Field label={t(`run.${k}`)} path={`run/${k}`} note={note}>
      <Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />
    </Field>
  );
  // Four groups by what they decide: the run itself, the weekly bonuses, what happens when something fails, what the bot does
  // on its own.
  return (
    <div className="groups">
      <fieldset>
        <legend>{t("run.group_run")}</legend>
        <div className="grid">
          {pick("difficulty")}
          <Field label={t("run.target_floor")} path="run/target_floor" note={pastFive ? t("run.target_floor_note") : undefined}>
            <Select value={String(run.target_floor)} options={runEnum("target_floor").map(String)} label={(v) => tv("target_floor", v)} onChange={(v) => set({ target_floor: Number(v) })} />
            {/* Remove with #434: until the entrance switches Parallel Superposition on, a target above 5 still stops at floor 5. */}
            {pastFive && <small>{t("run.target_floor_entry_note")}</small>}
          </Field>
          <ToggleNum label={t("run.runs")} path="run/runs" value={run.runs} on={1} min={1} note={t("run.runs_note")}
            onChange={(v) => set({ runs: v })} />
          {pick("theme_pack_refresh", t("run.theme_pack_refresh_note"))}
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_weekly")}</legend>
        <div className="grid">
          {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
          {pick("weekly_bonus_amount")}
          <Mark as="label" className="check wide" path="run/stop_when_weekly_bonus_out">
            <Input type="checkbox" checked={run.stop_when_weekly_bonus_out} onChange={(e) => set({ stop_when_weekly_bonus_out: e.target.checked })} />
            {t("run.stop_when_weekly_bonus_out")}
          </Mark>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_failure")}</legend>
        <div className="grid">
          {pick("starlight_unaffordable")}
          <Field label={t("run.wipe_retries")} path="run/wipe_retries"><Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} /></Field>
          {pick("after_retries")}
          <Field label={t("run.webhook_url")} path="run/webhook_url">
            <Input type="url" value={run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />
          </Field>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_auto")}</legend>
        <div className="options">
          {(["auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const).map((k) => (
            <Mark as="label" key={k} className="check" path={`run/${k}`}>
              <Input type="checkbox" checked={run[k]} onChange={(e) => set({ [k]: e.target.checked })} />
              {t(`run.${k}`)}
            </Mark>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

/** The daily tasks' options (#362); the client's task list picks and orders the tasks. */
function DailyTab() {
  const { t } = useEditor();
  return (
    <div className="stack">
      <p className="muted">{withBreaks(t("daily.note"))}</p>
      <LuxFields task="exp" />
      <LuxFields task="thread" />
      <ChargeFields />
    </div>
  );
}

function ChargeFields() {
  const { s, update, t } = useEditor();
  return (
    <fieldset>
      <legend>{t("charge.title")}</legend>
      <p className="caution">{withBreaks(t("charge.note"))}</p>
      <div className="grid">
        <Field label={t("charge.count")} path="charge_enkephalin/count">
          <Num value={s.charge_enkephalin.count} min={0} onChange={(v) => update((d) => { d.charge_enkephalin.count = v; })} />
        </Field>
      </div>
    </fieldset>
  );
}

function LuxFields({ task }: { task: keyof Settings["luxcavation"] }) {
  const { s, update, t, tv } = useEditor();
  const opts = s.luxcavation[task];
  const set = (patch: Partial<Luxcavation>) => update((d) => { Object.assign(d.luxcavation[task], patch); });
  const path = `luxcavation/${task}`;
  return (
    <fieldset>
      <legend>{t(`lux.${task}`)}</legend>
      <p className="muted">{withBreaks(t(`lux.${task}_note`))}</p>
      <div className="grid">
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
        <Field label={t("lux.consecutive")} path={`${path}/consecutive`} note={t("lux.consecutive_note")}>
          <Input type="checkbox" checked={opts.consecutive} onChange={(e) => set({ consecutive: e.target.checked })} />
        </Field>
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

function EventsTab() {
  const { t } = useEditor();
  return (
    <div className="stack">
      <p className="muted">{withBreaks(t("event.note"))}</p>
      <OverrideTable listKey="event_overrides" blank={{ question: "", option: "" }}
        cols={[{ key: "question", label: "event.question" }, { key: "option", label: "event.option" }]} />
    </div>
  );
}

function TrialsTab() {
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
