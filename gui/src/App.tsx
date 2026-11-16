// Shell: load <root>/config/settings.json, the tabs, and check-then-save (spec 04 section 2).
import { Fragment, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import * as api from "./api";
import { DeploymentTab } from "./Deployment";
import { GiftListsTab } from "./GiftLists";
import { TEXT, fill, type Key } from "./i18n";
import { newSettings, parseSettings, rebase, type Settings } from "./model";
import { movedOptions, sayMoved, type Moved } from "./movedOptions";
import { EventsTab, TrialsTab } from "./Overrides";
import { StarlightTab } from "./Starlight";
import { NO_PICKS, teamOptionsText, teamPicks, type TeamPicks } from "./teamOptions";
import { TeamsTab } from "./Teams";
import { ThemePackTab } from "./ThemePacks";
import { EditorContext, focusPath, nextTab, isPickList, makeCtx, translate, withBreaks, type Picked } from "./ui";
import { sayProblem, validate, type Problem } from "./validate";
import { LeavePrompt, TitleBar, WindowButtons, type Leave } from "./WindowControls";

export const TABS = [
  ["teams", "tab.teams", TeamsTab, ["teams"]],
  ["gifts", "tab.gifts", GiftListsTab, ["gift_lists"]],
  ["deployment", "tab.deployment", DeploymentTab, ["deployment_order_plans"]],
  ["starlight", "tab.starlight", StarlightTab, ["starlight_plans"]],
  ["themepacks", "tab.themepacks", ThemePackTab, ["theme_pack_plans"]],
  ["events", "tab.events", EventsTab, ["event_overrides"]],
  ["trials", "tab.trials", TrialsTab, ["trial_risk_overrides"]],
] as const;

type TabId = (typeof TABS)[number][0];

/** The tabs in groups (the team and its gift list; the plans; the overrides): the tabs that start a group after the first.
 * How each task runs is the client's (MXU, MFAAvalonia): the Mirror Dungeon task's options and the global ones (#779), the
 * daily tasks' (#781) and the Luxcavation teams (#780), so there is no Run options or Daily tab; the settings file has
 * none of their values since version 21 (#782). */
const GROUP_STARTS = new Set<TabId>(["deployment", "events"]);

const toText = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
/** A status as the header says it in lang: a TEXT key in that language's words, anything else as it is. */
const sayStatus = (lang: Settings["language"], status: string) =>
  Object.prototype.hasOwnProperty.call(TEXT[lang], status) ? TEXT[lang][status as Key] : status;
/** Write the team options file when these settings change what it says (#780, teamOptions.ts), a new one starting on
 * picks, and the status after it: `done` (a TEXT key) when it was written, "" when nothing changed, `failed` filled in
 * with the error, in s's language, when the write failed. */
async function teamOptionsNote(s: Settings, picks: TeamPicks, done: Key, failed: Key) {
  try {
    const text = teamOptionsText(await api.loadTeamOptions(), s, picks);
    if (text === null) return "";
    await api.saveTeamOptions(text);
    return done;
  } catch (e) {
    return fill(TEXT[s.language][failed], { error: String(e) });
  }
}
/** The element id of the problem at this place in the problems block. */
const problemId = (i: number) => `problem-${i}`;
/** The tab that edits a settings path ("teams/1/name"), if any ("(root)" has none). */
const tabOf = (path: string) => TABS.find((x) => (x[3] as readonly string[]).includes(path.split("/")[0]));
/** Whether a problem's path is the field's or under it: what the field's frame marks ("teams/1" marks "teams/1/name"). */
const within = (path: string, field: string) => path === field || path.startsWith(field + "/");
/** While the field at settings path `at` is typed in: `p` with the fields it marked before the last keystroke (`before`, the
 * problems shown then), or nothing for a problem the typing made. A problem is the one of its kind it was by a field it marks
 * outside the typed one, not by its words, which name what the user is typing: the typed field's own mark may now be another
 * problem of the kind (TEAMS #1 typed into #12, one clash for another). A problem of the typed field alone is matched by it.
 * A schema error stops the checks across objects (validate), so what they find once it is typed away is new here too. */
function asBefore(p: Problem, at: string, before: Problem[]): Problem[] {
  const inField = (m: string) => at !== "" && within(m, at);
  const outside = p.paths.every(inField) ? p.paths : p.paths.filter((m) => !inField(m));
  const was = before.filter((q) => q.say.key === p.say.key && q.paths.some((m) => outside.includes(m)));
  const paths = p.paths.filter((m) => was.some((q) => q.paths.includes(m)));
  return paths.length ? [{ ...p, paths }] : [];
}
/** The controls a value is typed into, not picked from (a select, a switch, a drag). */
const TYPED = new Set(["text", "search", "url", "number"]);
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
  // The field being typed in, its settings path ("" for none) and the problems shown before its last keystroke: a mark the
  // typing makes waits until the field loses focus, a save is tried or another writer changes the file (asBefore); null: every
  // problem shows (#717).
  const [typed, setTyped] = useState<{ field: EventTarget; at: string; before: Problem[] } | null>(null);
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
  // The teams a version 20 file picked for EXP and Thread Luxcavation: what a first team options file starts on, at the
  // start or at a save, should the start not write one (#782).
  const picks = useRef<TeamPicks>(NO_PICKS);
  // A version 20 file's values the client holds now, off its defaults: listed once, until dismissed (#782).
  const [moved, setMoved] = useState<{ from: number; values: Moved[] } | null>(null);
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
    setTyped(null); // what the other writer brought shows at once, also while a field is typed in
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
        const { data, migrated, unknown, old } = parseSettings(text);
        const migratedText = toText(data);
        if (old) { // before anything writes over it, also a save of a file the checks refuse (#782): a failure is the load's
          await api.saveOldSettings(old.version as number, text);
          picks.current = teamPicks(old);
        }
        setS(data);
        setSavedText(migratedText); // dirty = content changed, not formatting; before the write-back, which a poll may meet
        const ok = !validate(data).length;
        // the team options file again at the start: one deleted or broken since comes back (#780); not from a file the
        // checks refuse, whose teams may not read as teams. Before the write-back: a first one from the old file's teams
        const teamNote = ok ? await teamOptionsNote(data, picks.current, "teamOptions.updated", "teamOptions.failed") : "";
        if (migrated && ok) {
          try {
            await api.saveSettings(migratedText, text);
            disk.current = migratedText;
          } catch (e) {
            if (!api.isChanged(e)) throw e; // the Agent wrote first: the next poll reads its file
          }
        }
        if (old) setMoved({ from: old.version as number, values: movedOptions(old) });
        const notes = [unknown ? TEXT[data.language]["migrate.unknown"].replace("{n}", String(unknown)) : "", teamNote].filter(Boolean);
        // one note stays as it is, a key the header says anew in the language picked next
        setStatus(notes.length === 1 ? notes[0] : notes.map((n) => sayStatus(data.language, n)).join(" "));
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
  // What the marks, the tab markers, the problems block and the save plate show, each problem with the fields it marks now;
  // a fix shows at once, typing or not. The hold is the field's only while it has the focus: a field that goes with the focus
  // in it (Enter closes its box) fires no blur.
  const held = typed && typed.field === document.activeElement ? typed : null;
  const shown = held ? problems.flatMap((p) => asBefore(p, held.at, held.before)) : problems;
  useEffect(() => { if (!problems.length) setRefused(false); }, [problems.length]);
  const lang = s?.language ?? "zh_tw";
  const { t } = translate(lang);

  // The title bar alone, before the settings are read and when they do not read: the window has no system bar to fall back on.
  const bare = (
    <TitleBar>
      <h1>{t("title")}</h1>
      <span className="path" />
      <WindowButtons t={t} maximized={maximized} onError={(e) => setLoadError((why) => (why ? `${why}\n${String(e)}` : String(e)))} />
    </TitleBar>
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
    .flatMap((p, i) => (p.paths.some((m) => within(m, path)) ? [problemId(i)] : [])).join(" ");
  const ctx = makeCtx({
    s, problemIds, giftList, picked, setPicked,
    // any edit makes the edits that the revert (放棄變更) dropped no longer the newest: its Undo goes
    setS: (next) => { setRevertedFrom(null); setS((prev) => next(prev!)); },
    chooseList: (id, open) => { setGiftList(id); if (open) setTab("gifts"); },
  });
  const dirty = toText(s) !== savedText;
  const said = sayStatus(lang, status);
  // shown beside "unsaved" too (a refused save, the file read again), but not what an edit since has made stale
  const savedNow = status === "saved" || status === "savedTeams";
  const note = savedNow || status === "reverted" ? "" : said;

  /** Check, then write; true when the file holds the edits. */
  const save = async () => {
    setTyped(null); // a save tried shows every problem, also one still being typed (Ctrl+S in the field)
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
        // the team options file follows the teams saved; a change is said once, as the client reads it only at its start
        setStatus((await teamOptionsNote(current, picks.current, "savedTeams", "savedTeamsFailed")) || "saved");
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
  const state = shown.length ? "blocked" : failed ? "failed" : dirty ? "dirty" : savedNow ? "saved" : said ? "note" : "clean";
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
      <TitleBar inert={!!asking}>
        <h1>{t("title")}</h1>
        <span className="muted path" title={`${root}\\config\\settings.json`}>{root}\config\settings.json</span>
        <label className="lang"><span>{t("language")}</span>
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
      </TitleBar>
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
        onChange={(e) => {
          if (!(e.target === document.activeElement && typesText(e.target))) return;
          const at = (e.target as HTMLElement).closest<HTMLElement>("[data-path]")?.dataset.path ?? "";
          setTyped({ field: e.target, at, before: shown });
        }}
        onBlur={() => setTyped(null)}>
        <div id="tabpanel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {/* the page's heading under the window's: the tab's name, for a screen reader's list of headings */}
          <h2 className="sr-only">{t(TABS.find((x) => x[0] === tab)![1])}</h2>
          {/* a version 20 file's values to set again in the client, once (#782) */}
          {moved && moved.values.length > 0 && (
            <section className="moved" aria-labelledby="moved-title">
              <h3 id="moved-title">{t("moved.title")}</h3>
              <p>{withBreaks(fill(t("moved.note"), { version: moved.from }))}</p>
              <ul>{sayMoved(moved.values, s.teams, lang).map((row) => (
                <li key={`${row.task} ${row.option}`}>{fill(t("moved.row"), { ...row })}</li>
              ))}</ul>
              <button type="button" onClick={() => setMoved(null)}>{t("moved.dismiss")}</button>
            </section>
          )}
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
