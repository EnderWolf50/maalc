// Shell: load <root>/config/settings.json, the tabs, and check-then-save (spec 04 section 2); the run the window starts (#815),
// which outlives a tab switch: Start saves first, and closing the window during a run hides it in the tray. The scheduled runs
// (#816): the load and each save bring the Task Scheduler's tasks in line with the schedules, and a scheduled start
// (`maalc-gui.exe --run <id>`) runs the task list as Start does, closing the window it opened when the run ends.
import { Fragment, useEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import * as api from "./api";
import { DeploymentTab } from "./Deployment";
import { GiftListsTab } from "./GiftLists";
import { TEXT, fill, type Key } from "./i18n";
import { newSettings, parseSettings, rebase, withoutGoneStart, type Settings } from "./model";
import { EventsTab, TrialsTab } from "./Overrides";
import { READ_BACK_FILES, readBack, type ReadBackFiles, type Report } from "./readBack";
import { ReadBackNotice } from "./ReadBackNotice";
import { RunTab, entryKey, taskOfPath } from "./Run";
import { IDLE, RunnerContext, crashed, isRunning, reduce, wantsList, type Runner } from "./runner";
import { ScheduleContext, logLine, stamp, type Outcome, type ScheduleView } from "./schedule";
import { StarlightTab } from "./Starlight";
import { TeamsTab } from "./Teams";
import { ThemePackTab } from "./ThemePacks";
import { EditorContext, focusPath, nextTab, isPickList, makeCtx, translate, type Picked } from "./ui";
import { FailureNotice, OutcomeNotice, UpdateChip, type Failure, type Update, type UpdateStep } from "./Update";
import { sayProblem, validate, type Problem } from "./validate";
import { LeavePrompt, TitleBar, WindowButtons, type Leave } from "./WindowControls";

export const TABS = [
  // the team queue is arranged in the Mirror Dungeon task's options (#878): a problem in it opens the Run tab on that task
  ["run", "tab.run", RunTab, ["run", "luxcavation", "charge_enkephalin", "tasks", "emulator", "schedules", "team_queue"]],
  ["teams", "tab.teams", TeamsTab, ["teams"]],
  ["gifts", "tab.gifts", GiftListsTab, ["gift_lists"]],
  ["deployment", "tab.deployment", DeploymentTab, ["deployment_order_plans"]],
  ["starlight", "tab.starlight", StarlightTab, ["starlight_plans"]],
  ["themepacks", "tab.themepacks", ThemePackTab, ["theme_pack_plans"]],
  ["events", "tab.events", EventsTab, ["event_overrides"]],
  ["trials", "tab.trials", TrialsTab, ["trial_risk_overrides"]],
] as const;

type TabId = (typeof TABS)[number][0];

/** The tabs in groups (what runs: the task list and its options; the team and its gift list; the plans; the overrides): the
 * tabs that start a group after the first. The Run tab edits the settings file's task options, task list, emulator and
 * schedules (version 23, #813, #814, #816) and runs the tasks (#815), so the window opens on it. */
const GROUP_STARTS = new Set<TabId>(["teams", "deployment", "events"]);

const toText = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
/** A status as the header says it in lang: a TEXT key in that language's words, anything else as it is. */
const sayStatus = (lang: Settings["language"], status: string) =>
  Object.prototype.hasOwnProperty.call(TEXT[lang], status) ? TEXT[lang][status as Key] : status;
/** config/'s files the read-back reads (#814), each as read: a file that cannot be read says why, which the notice shows. */
async function readBackFiles(): Promise<ReadBackFiles> {
  const read = (name: string) => api.loadReadBack(name).catch((e: unknown) => ({ error: String(e) }));
  const [mxu, teamOptions, v20] = await Promise.all([READ_BACK_FILES.mxu, READ_BACK_FILES.teamOptions, READ_BACK_FILES.v20].map(read));
  return { mxu, teamOptions, v20 };
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

/** `start`: the tab the window opens on, the Run tab unless a caller (a test of another tab) names one. */
export default function App({ start = "run" }: { start?: TabId } = {}) {
  const [s, setS] = useState<Settings | null>(null);
  const [savedText, setSavedText] = useState("");
  const [loadError, setLoadError] = useState("");
  const [root, setRoot] = useState("");
  const [tab, setTab] = useState<TabId>(start);
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
  // An older file's read-back (#814): config/'s files as the load read them, so the old file read again (the Agent writes
  // back the version it read, #501) reads the same values back; and its report, which shows once the file is written as
  // the current version, until dismissed.
  const backFiles = useRef<ReadBackFiles | null>(null);
  const pending = useRef<Report | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  /** The file is written: an older one's read-back is done, and its notice shows. */
  const wroteBack = () => {
    if (!pending.current) return;
    setReport(pending.current);
    pending.current = null;
  };
  /** A file's settings as the editor holds them: migrated, and an older one's run values read back from the files the load
   * read; with the read-back's report, null when there was none. */
  const settingsOf = (text: string) => {
    const parsed = parseSettings(text);
    const back = parsed.old && backFiles.current ? readBack(parsed.data, parsed.old.version, backFiles.current) : null;
    return { ...parsed, data: back?.data ?? parsed.data, report: back?.report ?? null };
  };
  const latest = useRef({ s, savedText });
  latest.current = { s, savedText };
  // the run: what the backend relays of it, folded into one view (runner.ts); a page loaded again during a run takes it up
  const [run, dispatch] = useReducer(reduce, IDLE);
  const [starting, setStarting] = useState(false); // Start's save and the runner's start are under way
  const startingRef = useRef(false); // the same, at once: a scheduled start right after another reads it before a render
  const runRef = useRef(run);
  runRef.current = run;
  // the scheduled runs (#816): the last sync with the Task Scheduler, the last scheduled start the window took, and the
  // schedule whose start opened this window, which closes when its run ends
  const [synced, setSynced] = useState<ScheduleView["synced"]>(null);
  const [lastScheduled, setLastScheduled] = useState<ScheduleView["last"]>(null);
  const closeAfter = useRef<string | null>(null);
  const [reveal, setReveal] = useState(false); // a scheduled run started: the Run tab shows its log and Stop
  /** Bring the Task Scheduler's tasks in line with `list`, the schedules of the file as read or saved. */
  const writeTasks = (list: Settings["schedules"]) => {
    api.syncSchedules(list).then((done) => setSynced({ done }), (e: unknown) => setSynced({ error: String(e) }));
  };
  /** What came of a scheduled start: a line in logs/schedule.log (done when the promise is) and the live log, and the
   * schedules' section's last start. */
  const noteScheduled = (id: string, outcome: Outcome) => {
    const line = logLine(id, outcome), at = stamp();
    dispatch({ type: "note", line });
    setLastScheduled({ id, at, outcome });
    return api.logSchedule(`${at} ${line}`).catch(() => {});
  };
  // the run this page took up was under way when it did (the backend's word, not the phase of the moment: its messages come
  // one by one); a run this page starts carries its own list, so this stays as it is for good
  const [takenUp, setTakenUp] = useState(false);
  // whether the backend answered if this page took up a run, and whether it handed out the scheduled starts this window opened
  // for, the first of them begun: until both, the Run tab does not know whether a run is under way or starting as it opens (#876)
  const [attached, setAttached] = useState(false);
  const [startsBegun, setStartsBegun] = useState(false);
  useEffect(() => {
    let live = true; // the development build starts an effect twice: the first channel's messages are dropped
    api.attachRun((m) => { if (live) dispatch(m); }).then((underWay) => {
      if (!live) return;
      if (underWay) { dispatch({ type: "attached" }); setTakenUp(true); } // running now: the run's messages come after the answer
      setAttached(true);
    }, () => { if (live) setAttached(true); });
    return () => { live = false; };
  }, []);
  // the run's list follows the settings' task list (runner.ts listed): a run under way a page took up takes it, and after a
  // run an edit to it takes the run's states off the Run tab's rows for good
  const tasksNow = s ? JSON.stringify(s.tasks) : null;
  const runWantsList = wantsList(run);
  useEffect(() => { if (s) dispatch({ type: "list", list: s.tasks, adopt: takenUp }); }, [tasksNow, runWantsList, takenUp]);
  // The self-update (#817): the newer release the start's check found and how far its update is, shown in the header; why
  // its last step failed and how the last apply went (read at the window's start), each above every tab until dismissed.
  const [update, setUpdate] = useState<Update | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [outcome, setOutcome] = useState<api.UpdateOutcome | null>(null);
  useEffect(() => {
    // a check that fails says nothing; the development build asks twice, and the backend answers both from one check
    api.checkUpdate().then(({ current, release }) => {
      if (release) setUpdate((u) => u ?? { current, release, at: { step: "available" } });
    }, () => {});
    api.lastUpdate().then((o) => { if (o) setOutcome(o); }, () => {});
  }, []);
  const stepTo = (at: UpdateStep) => setUpdate((u) => u && { ...u, at });

  /** Take what another writer changed in the file, under the unsaved edits (rebase); the settings the editor holds now. */
  const sync = async () => {
    const text = await api.loadSettings();
    const { s: draft, savedText: base } = latest.current; // set in one render: no draft is a load not done
    if (text === disk.current || !draft) return draft;
    let data: Settings | undefined;
    try {
      data = text === null ? undefined : settingsOf(text).data;
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
        const { old } = parseSettings(text);
        // An older file is kept aside before anything writes over it, a save of a file the checks refuse too (#782). When
        // it cannot be, the load fails with why, and nothing is written.
        if (old) {
          await api.saveOldSettings(old.version, text);
          // the run values a v1.0.0 install held outside the file come back once (#814); a version 23 file reads none
          backFiles.current = await readBackFiles();
        }
        const { data, unknown, report } = settingsOf(text);
        pending.current = report;
        const migratedText = toText(data);
        setS(data);
        setSavedText(migratedText); // dirty = content changed, not formatting; before the write-back, which a poll may meet
        // the window's start checks the tasks (a moved folder's point at the old one); schedules the checks refuse wait for
        // their fix and a save
        if (!validate(data).some((p) => p.paths.some((m) => within(m, "schedules")))) writeTasks(data.schedules);
        // written back only when it passes the checks: a file they refuse waits for the user's fixes and a save
        if (old && !validate(data).length) {
          try {
            await api.saveSettings(migratedText, text);
            disk.current = migratedText;
            wroteBack();
          } catch (e) {
            if (!api.isChanged(e)) throw e; // the Agent wrote first: the next poll reads its file, and a save writes it back
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
  // During a run the window hides in the tray instead, the run going on, unsaved edits and all (#815); a run that ended
  // meanwhile (the backend says it hid nothing) closes as below. A hide that fails keeps the window open and says why:
  // closing it would end the run with the app.
  useEffect(() => {
    const askIfUnsaved = () => {
      const keep = unsaved();
      if (keep) ask("close");
      return keep;
    };
    return api.onCloseRequested(() => {
      if (!isRunning(runRef.current)) return askIfUnsaved();
      const { t } = translate(latest.current.s?.language ?? "zh_tw");
      return api.hideToTray({ tip: t("tray.tip"), show: t("tray.show"), stop: t("tray.stop") })
        .then((hid) => hid || askIfUnsaved(), (e: unknown) => { setStatus(String(e)); return true; });
    });
  }, []);
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
  // the schedules as the file holds them: an edit not saved yet is not in the Task Scheduler
  const savedSchedules = useMemo(() => {
    try { return JSON.stringify((JSON.parse(savedText) as Settings).schedules ?? []); } catch { return "[]"; }
  }, [savedText]);

  // A scheduled run's start (#816), taken in turn once the settings are read or failed to: its own start's `--run`, then each
  // second start's. What runs it is set further down, once a render has the settings; until then (the load error screen) it
  // is not run, and says so.
  const scheduledRef = useRef<(r: api.Scheduled) => Promise<unknown>>(async () => {});
  scheduledRef.current = ({ id }) => noteScheduled(id, { kind: "unread" });
  const ready = s !== null || loadError !== "";
  useEffect(() => {
    if (!ready) return;
    let queue: Promise<unknown> = Promise.resolve();
    // taken before a StrictMode double start drops the first effect: the backend hands each start out once. startsBegun once
    // the first start has begun (a run's start marks the window busy at once, startRun), or none came
    const take = () => {
      queue = queue.then(() => api.takeScheduled()).then(async (all) => {
        for (const r of all) {
          const done = scheduledRef.current(r);
          setStartsBegun(true);
          await done;
        }
      }).catch(() => {}).then(() => setStartsBegun(true));
    };
    take();
    return api.onScheduled(take);
  }, [ready]);
  // the window a schedule opened closes when its run ends, unless it has edits that closing would drop, or the runner crashed:
  // the exit code and its last lines are only in this window (spec #811 「執行器」: the window stays and says why)
  useEffect(() => {
    const id = closeAfter.current;
    if (run.phase !== "ended" || id === null) return;
    closeAfter.current = null;
    if (crashed(run)) {
      noteScheduled(id, { kind: "crashed", code: run.exit!.code });
      return;
    }
    if (unsaved()) {
      noteScheduled(id, { kind: "kept_open" });
      return;
    }
    noteScheduled(id, { kind: "closed" }).finally(() => { api.closeWindow().catch(() => {}); });
  }, [run.phase]);
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
  const savedNow = status === "saved";
  const note = savedNow || status === "reverted" ? "" : said;

  /** Check, then write; true when the file holds the edits. */
  const save = async () => {
    setTyped(null); // a save tried shows every problem, also one still being typed (Ctrl+S in the field)
    setFailed(false);
    setRefused(false);
    try {
      for (let tries = 1; ; tries++) {
        const synced = (await sync())!; // what another writer changed since goes under the edits first (#501)
        const current = withoutGoneStart(synced); // a flag on a team deleted since goes (#878)
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
        if (current !== synced) setS((now) => now && withoutGoneStart(now)); // the dropped flag is saved, not an edit; an edit made since stays
        setSavedText(written);
        wroteBack();
        setStatus("saved");
        writeTasks(current.schedules); // each save checks the tasks against the schedules it wrote
        return true;
      }
    } catch (e) {
      setFailed(true);
      setStatus(String(e));
      return false;
    }
  };
  saveRef.current = asking ? () => {} : save; // while the close prompt asks, its buttons decide

  /** Start the ticked tasks: unsaved edits are saved first (each task reads the file at its start), then the runner starts on
   * the file's task list and emulator. A save the checks refuse starts nothing, and says why as any save does. Returns why
   * nothing started, null when the run did. */
  type NotStarted = Extract<Outcome, { kind: "refused" }>["why"];
  const startRun = async (): Promise<NotStarted | null> => {
    if (startingRef.current || isRunning(runRef.current)) return { error: api.RUN_UNDER_WAY };
    if (problems.length) return "problems";
    startingRef.current = true;
    setStarting(true);
    try {
      if (dirty && !(await save())) return "save";
      const { s: now } = latest.current;
      const entries = now!.tasks.filter((x) => x.enabled).map((x) => x.id); // a task's id is its entry node (interface.json)
      if (!entries.length) return "no_task";
      // the whole list it starts from: the Run tab writes the run's states on its rows while the list is still this one
      const begin = { type: "begin", entries, list: now!.tasks } as const;
      runRef.current = reduce(runRef.current, begin); // under way now, for a scheduled start right after this one
      dispatch(begin);
      return await api.startRun(entries, now!.emulator, dispatch).then(() => null, (e: unknown) => {
        dispatch({ type: "refused", error: String(e) });
        return { error: String(e) };
      });
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  };
  /** Apply the downloaded update: the window closes for it, so unsaved edits are saved first, as Start saves them; a save the
   * checks refuse applies nothing, and says why as any save does. It waits while a run is under way, as the backend does. */
  const applyUpdate = async () => {
    if (startingRef.current || isRunning(runRef.current)) return; // a run starting or under way
    stepTo({ step: "applying" });
    if (unsaved() && !(await save())) return stepTo({ step: "ready" });
    try {
      await api.applyUpdate(); // the window exits: the new version opens once it replaced the files
    } catch (e) {
      if (api.isRunUnderWay(e)) return stepTo({ step: "ready" }); // a run started meanwhile
      setFailure({ why: "apply", error: String(e) });
      stepTo({ step: "failed" });
    }
  };
  /** Download the newer release, check its sha256 and unpack it, then apply it unless a run is under way. A run may start
   * meanwhile: the apply then waits for it to end. */
  const startUpdate = async () => {
    setFailure(null);
    stepTo({ step: "download", received: 0, total: update?.release.size ?? 0 });
    try {
      await api.downloadUpdate(stepTo); // each progress is a step of the update
    } catch (e) {
      setFailure({ why: api.isMismatch(e) ? "mismatch" : "download", error: String(e) });
      return stepTo({ step: "failed" });
    }
    stepTo({ step: "ready" });
    await applyUpdate();
  };
  /** A scheduled run's start (#816, spec #811 「定時執行」): the task list runs as Start runs it, on the Run tab; skipped while a
   * run is under way or while an update left the folder half replaced (lib.rs Scheduled, #817),
   * not run when its schedule is not in the settings (a task left from an older file) or Start would not start. The window it
   * opened closes when the run ends (the effect above); one that stays open says why. */
  scheduledRef.current = async ({ id, opened, update_unfinished }) => {
    if (!latest.current.s?.schedules.some((x) => x.id === id)) return noteScheduled(id, { kind: "unknown" });
    if (update_unfinished) return noteScheduled(id, { kind: "updating" }); // as the backend found it when the start came
    if (startingRef.current || isRunning(runRef.current)) return noteScheduled(id, { kind: "busy" });
    setTab("run");
    if (opened) closeAfter.current = id; // before the start: a run that ends at once still closes the window
    const why = await startRun();
    if (why === null) {
      setReveal(true);
      return noteScheduled(id, { kind: "started" });
    }
    if (closeAfter.current === id) closeAfter.current = null;
    return noteScheduled(id, { kind: "refused", why });
  };
  const runner: Runner = {
    view: run,
    start: () => { startRun(); },
    stop: () => { api.stopRun().catch(() => {}); },
    blocked: starting ? "saving" : problems.length ? "problems" : s.tasks.some((x) => x.enabled) ? null : "no_task",
    reveal, revealed: () => setReveal(false),
    settled: attached && startsBegun,
  };

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
    const task = taskOfPath(path); // a task option shows with its task picked
    if (section === "gift_lists" && s.gift_lists[at]) setGiftList(s.gift_lists[at].id);
    else if (section === "tasks" && s.tasks[at]) ctx.pick("tasks", entryKey(s.tasks, at)); // that entry, not its task's first
    else if (isPickList(section) && s[section][at]) ctx.pick(section, s[section][at].id);
    else if (task) ctx.pick("tasks", task);
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
  // not during a run: Undo would bring back edits to the settings the run reads, which a save would then write (#815)
  const canUndoRevert = status === "reverted" && revertedFrom !== null && !dirty && !isRunning(run);
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
        {update && <UpdateChip update={update} running={isRunning(run)} onUpdate={() => { startUpdate(); }} onApply={() => { applyUpdate(); }} />}
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
          {/* why the update stopped, and how the last apply went (#817) */}
          {failure && update && <FailureNotice version={update.release.version} failure={failure} onDismiss={() => setFailure(null)} />}
          {outcome && <OutcomeNotice outcome={outcome} onDismiss={() => setOutcome(null)} />}
          {/* an older file's run values read back, once (#814) */}
          {report && <ReadBackNotice report={report} onDismiss={() => setReport(null)} />}
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
          <RunnerContext.Provider value={runner}>
            <ScheduleContext.Provider value={{ synced, saved: savedSchedules, last: lastScheduled }}><Current /></ScheduleContext.Provider>
          </RunnerContext.Provider>
        </div>
      </main>
      {leavePrompt}
    </EditorContext.Provider>
  );
}
