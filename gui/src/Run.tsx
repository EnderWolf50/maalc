// The Run tab (#814, #815, #816, spec #811 「設定視窗」, spec 04 sections 5, 12 and 14): the emulator on top, with the device
// scan; the task list on the left (ticks, drag or ↑↓: the run order; a task listed again, or an extra entry removed, #811)
// and the picked task's options on the right; the global
// options in a frame of their own; the scheduled runs (Schedules.tsx); the runner's Start and Stop, each posted task's state
// and the live log at the bottom. Each control
// writes the settings key the runner or the agent reads at a task's start, and shows that key beside its label: the agent's
// stop lines name an option by it ("run/start_team: team 'x' was deleted ..."). A team pick lists the settings' teams as they
// are now. During a run the settings it reads are locked (LockContext): a task still shows its options when clicked.
import { memo, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { fill, type Key } from "./i18n";
import { schema, type LuxOptions, type Settings } from "./model";
import { LOG_LINES, crashed, isRunning, sameAddress, useRunner, type Device, type LogLine, type RunView } from "./runner";
import * as api from "./api";
import { SchedulesSection } from "./Schedules";
import { Choice, Field, Input, LockContext, Mark, Num, ReorderList, Select, ToggleNum, useEditor, usePick, withBreaks } from "./ui";

const RUN = schema.properties.run.properties as Record<string, { enum?: (string | number)[] }>;
const runEnum = (k: string) => RUN[k].enum!.map(String);
const LUX_MODES: string[] = schema.$defs.luxcavation.properties.mode.enum;
/** The task ids (agent/settings.schema.json $defs.task); a new file lists them as model.ts newSections says. */
export const TASKS: string[] = schema.$defs.task.enum;
/** The run keys every task reads (the global options): the rest of run is the Mirror Dungeon task's. */
export const GLOBAL_KEYS = ["webhook_url", "auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const;
const isGlobal = (key: string) => (GLOBAL_KEYS as readonly string[]).includes(key);
/** The settings paths that hold each task's options, a task with none left out: the one table the tab, its problem marks
 * and the read-back's notice go by. */
const TASK_ROOTS: Record<string, string[]> = {
  MirrorDungeon: Object.keys(RUN).filter((k) => !isGlobal(k)).map((k) => `run/${k}`),
  ExpLuxcavation: ["luxcavation/exp"], ThreadLuxcavation: ["luxcavation/thread"], ChargeEnkephalin: ["charge_enkephalin"],
};
const within = (path: string, root: string) => path === root || path.startsWith(root + "/");

/** The task whose options hold a settings path: the Run tab shows that task's options to reach the field. Undefined for a
 * global option and anything else. */
export const taskOfPath = (path: string) => Object.keys(TASK_ROOTS).find((id) => TASK_ROOTS[id].some((root) => within(path, root)));
/** A task's name in the GUI's language; an id the GUI does not know (a hand edit, which the schema check names) as it is. */
export const taskName = (t: (k: Key) => string, id: string) => (TASKS.includes(id) ? t(`task.${id}` as Key) : id);
/** The text key of a task option's label by its settings path: run/<key> is run.<key>, luxcavation/<task>/<key> lux.<key>,
 * charge_enkephalin/count charge.count. */
export const optionLabel = (path: string): Key => {
  const parts = path.split("/");
  const key = parts[parts.length - 1];
  return (parts[0] === "luxcavation" ? `lux.${key}` : parts[0] === "charge_enkephalin" ? `charge.${key}` : `run.${key}`) as Key;
};

/** A field's label with its settings key after it, small: the key a stop line names. A screen reader reads the label alone.
 * One inline span, so a switch's flex row (.check) keeps the label and its key as one item. */
function Keyed({ path }: { path: string }) {
  const { t } = useEditor();
  return <span className="keyed">{t(optionLabel(path))}<code className="key" aria-hidden>{path}</code></span>;
}
/** A field of the tab: its label and settings key, the control, a note. */
const KeyField = ({ path, note, children }: { path: string; note?: string; children: ReactNode }) =>
  <Field label={<Keyed path={path} />} path={path} note={note}>{children}</Field>;
/** A switch of the tab with its note under it (#721): the label's text the size of the fields', its key after it. */
function Switch({ path, checked, note, onChange }: { path: string; checked: boolean; note?: string; onChange: (on: boolean) => void }) {
  return (
    <Mark className="toggle" path={path}>
      <label className="check">
        <Input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><Keyed path={path} />
      </label>
      {note && <small>{withBreaks(note)}</small>}
    </Mark>
  );
}

/** An entry's pick key: its task's id for the task's first entry, `<id>#<n>` for the one after n others (a task may be listed
 * more than once, #811), so the pick stays on its entry when the list is reordered; a pick by id alone is the first entry. */
const entryKey = (tasks: { id: string }[], j: number) => {
  const n = tasks.slice(0, j).filter((x) => x.id === tasks[j].id).length;
  return n ? `${tasks[j].id}#${n}` : tasks[j].id;
};

export function RunTab() {
  const { s, update, t, bad } = useEditor();
  // each entry a row of its own: `nth` is its place among its task's entries (from 0), `of` how many the task has
  const rows = s.tasks.map((x, j) => ({
    ...x, key: entryKey(s.tasks, j), nth: s.tasks.slice(0, j).filter((y) => y.id === x.id).length,
    of: s.tasks.filter((y) => y.id === x.id).length,
  }));
  const [i, setSel] = usePick("tasks", rows.map((x) => ({ id: x.key })));
  const picked = rows[i];
  const locked = isRunning(useRunner().view);
  // the picked task once more, unticked, right after the picked entry, and picked: a new entry runs only once ticked
  const again = () => {
    const tasks = [...s.tasks.slice(0, i + 1), { id: picked.id, enabled: false }, ...s.tasks.slice(i + 1)];
    update((d) => { d.tasks = tasks; });
    setSel(entryKey(tasks, i + 1));
  };
  // a task's last entry stays (the button is only there while it has another): every task is listed, to be ticked
  const remove = () => {
    update((d) => { d.tasks.splice(i, 1); });
    setSel(picked.id);
  };
  return (
    <div className="run-page">
      <LockContext.Provider value={locked}>
      {locked && <p className="notice" role="status">{t("runner.locked")}</p>}
      <EmulatorFields />
      <div className="split">
        <aside className="task-list" data-path="tasks">
          <h3>{t("tasks.title")}</h3>
          <p className="muted">{withBreaks(t("tasks.note"))}</p>
          {/* a moved list's rows still carry the keys of before the move: the pick's key is counted in the list after it */}
          <ReorderList items={rows} keyOf={(x) => x.key} selected={i} onSelect={(j, list) => setSel(entryKey(list, j))}
            badAt={(j) => bad(`tasks/${j}`) || (TASK_ROOTS[rows[j].id] ?? []).some(bad)}
            onChange={(moved) => update((d) => { d.tasks = moved.map(({ id, enabled }) => ({ id, enabled })); })}
            render={(x, j) => (
              <span className="task-row">
                {/* the tick's own hit area, larger than the bare box; a click there ticks and leaves the picked task as it is */}
                <label className="tick" onClick={(e) => e.stopPropagation()}>
                  <Input type="checkbox" checked={x.enabled}
                    aria-label={fill(t(x.of > 1 ? "tasks.tick_nth" : "tasks.tick"), { name: taskName(t, x.id), n: x.nth + 1 })}
                    onChange={(e) => update((d) => { d.tasks[j].enabled = e.target.checked; })} />
                </label>
                <span className={x.enabled ? "" : "muted"}>{taskName(t, x.id)}</span>
              </span>
            )} />
          {picked && (
            <div className="task-actions">
              <button type="button" disabled={locked} onClick={again}>
                <span aria-hidden>+ </span>{fill(t("tasks.again"), { name: taskName(t, picked.id) })}
              </button>
              {picked.of > 1 && <button type="button" className="danger" disabled={locked} onClick={remove}>{t("tasks.remove")}</button>}
            </div>
          )}
        </aside>
        <section className="task-options">
          {picked && <>
            {/* the task's id beside its name: the agent's stop lines name a task by it ("the MirrorDungeon task") */}
            <h3>{taskName(t, picked.id)} <code>{picked.id}</code></h3>
            {picked.of > 1 && <p className="muted">{fill(t("tasks.entries"), { n: picked.of })}</p>}
            <TaskOptions id={picked.id} />
          </>}
        </section>
      </div>
      <GlobalOptions />
      </LockContext.Provider>
      {/* the run reads no schedule: they stay open to edits during a run (#816) */}
      <SchedulesSection />
      <RunnerSection />
    </div>
  );
}

/** What the status line says of the run: the phase, then where it got to (the connection, the resource) or how it ended. */
function statusOf(t: (k: Key) => string, v: RunView) {
  if (v.phase === "idle") return t("runner.status_idle");
  // ended before its end event: the window ended its tree after a stop, or it crashed and the run failed (spec #811)
  if (v.phase === "ended") return t(crashed(v) ? "runner.result.crashed" : v.exit && !v.exit.ended ? "runner.result.stopped"
    : `runner.result.${v.result ?? "failed"}`);
  const parts = [
    v.phase === "stopping" && t("runner.stopping"),
    v.link ? fill(t(`runner.link.${v.link.state}`), { address: v.link.address }) : t("runner.status_starting"),
    v.resource && t(`runner.resource.${v.resource}`),
  ];
  return parts.filter(Boolean).join(" · ");
}

/** One line of the live log: its time, where it came from (a class, so the bot's own lines read apart) and its text. */
const LogRow = memo(function LogRow({ line }: { line: LogLine }) {
  return <li className={`src-${line.source}`}><time>{line.t}</time><span>{line.line}</span></li>;
});

/** The runner (#815): Start (it saves first) and Stop, what the run is doing, each posted task's state, the live log (the last
 * LOG_LINES lines, MaaFramework's own output hidden unless asked for), and how a run that went wrong ended. */
function RunnerSection() {
  const { t } = useEditor();
  const { view, start, stop, blocked, reveal, revealed } = useRunner();
  const running = isRunning(view);
  const [showConsole, setShowConsole] = useState(false);
  // a scheduled run's window shows its log and Stop (spec #811 「定時執行」): they sit at the tab's bottom
  const box = useRef<HTMLFieldSetElement>(null);
  useEffect(() => {
    if (!reveal) return;
    box.current?.scrollIntoView?.({ block: "start" });
    revealed?.();
  }, [reveal]);
  const shown = showConsole ? view.log : view.log.filter((l) => l.source !== "console");
  // the log follows its newest line while the user has not scrolled up from the bottom
  const pane = useRef<HTMLOListElement>(null);
  const follow = useRef(true);
  useLayoutEffect(() => { if (follow.current && pane.current) pane.current.scrollTop = pane.current.scrollHeight; }, [view.log, showConsole]);
  return (
    <fieldset className="runner" ref={box}>
      <legend>{t("runner.title")}</legend>
      <div className="runner-bar">
        <button type="button" className="primary" disabled={running || blocked !== null} onClick={start}>{t("runner.start")}</button>
        <button type="button" disabled={view.phase !== "running"} onClick={stop}>
          {view.phase === "stopping" ? t("runner.stopping") : t("runner.stop")}
        </button>
        <span className="runner-status" role="status" data-phase={view.phase}>{statusOf(t, view)}</span>
      </div>
      {blocked && !running ? <p className="caution">{t(`runner.blocked_${blocked}`)}</p> : <p className="muted">{t("runner.start_note")}</p>}
      {view.refused && <p className="caution" role="alert">{fill(t("runner.refused"), { error: view.refused })}</p>}
      {view.killed && <p className="caution" role="alert">{fill(t("runner.killed"), { reason: view.killed })}</p>}
      {crashed(view) && (
        <div className="crash" role="alert">
          <p>{fill(t("runner.crash"), { code: view.exit!.code ?? "—" })}</p>
          <pre>{view.exit!.tail.join("\n")}</pre>
        </div>
      )}
      <div className="runner-body">
        <div className="run-tasks">
          <h3>{t("runner.tasks")}</h3>
          {view.tasks.length ? (
            <ol aria-label={t("runner.tasks")}>
              {view.tasks.map((x, j) => (
                <li key={j} data-state={x.state}>
                  <span>{taskName(t, x.entry)}</span>
                  <span className="state">{t(`runner.state.${x.state}`)}</span>
                  {x.reason && <small>{x.reason}</small>}
                </li>
              ))}
            </ol>
          ) : <p className="muted">{t("runner.tasks_none")}</p>}
        </div>
        <div className="run-log-pane">
          <h3>{t("runner.log")}</h3>
          <p className="muted">{fill(t("runner.log_note"), { n: LOG_LINES })}</p>
          <label className="check">
            <input type="checkbox" checked={showConsole} onChange={(e) => setShowConsole(e.target.checked)} />{t("runner.console")}
          </label>
          <ol className="run-log" ref={pane} aria-label={t("runner.log")} tabIndex={0}
            onScroll={(e) => { const el = e.currentTarget; follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24; }}>
            {shown.map((l) => <LogRow key={l.n} line={l} />)}
          </ol>
        </div>
      </div>
    </fieldset>
  );
}

function TaskOptions({ id }: { id: string }) {
  const { t } = useEditor();
  if (id === "MirrorDungeon") return <MirrorOptions />;
  if (id === "ExpLuxcavation") return <LuxFields task="exp" />;
  if (id === "ThreadLuxcavation") return <LuxFields task="thread" />;
  if (id === "ChargeEnkephalin") return <ChargeFields />;
  return <p className="muted">{t("tasks.none")}</p>;
}

/** The Mirror Dungeon task's options (spec 04 section 5) in three groups by what they decide: the run itself, the weekly
 * bonuses, what happens when something fails. */
function MirrorOptions() {
  const { s, update, t, tv } = useEditor();
  const run = s.run;
  const pastFive = run.target_floor > 5;
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  type Pick = "difficulty" | "weekly_bonus_use" | "weekly_bonus_amount" | "starlight_unaffordable" | "after_retries" | "theme_pack_refresh";
  const pick = (k: Pick, note?: string) => (
    <KeyField path={`run/${k}`} note={note}>
      <Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />
    </KeyField>
  );
  return (
    <div className="groups">
      <fieldset>
        <legend>{t("run.group_run")}</legend>
        <div className="grid">
          {pick("difficulty")}
          <KeyField path="run/target_floor" note={pastFive ? t("run.target_floor_note") : undefined}>
            <Select value={String(run.target_floor)} options={runEnum("target_floor")} label={(v) => tv("target_floor", v)}
              onChange={(v) => set({ target_floor: Number(v) })} />
            {/* Remove with #434: until the entrance switches Parallel Superposition on, a target above 5 still stops at floor 5. */}
            {pastFive && <small>{t("run.target_floor_entry_note")}</small>}
          </KeyField>
          <ToggleNum label={<Keyed path="run/runs" />} path="run/runs" value={run.runs} on={1} min={1} note={t("run.runs_note")}
            onChange={(v) => set({ runs: v })} />
          {pick("theme_pack_refresh", t("run.theme_pack_refresh_note"))}
          <KeyField path="run/start_team" note={t("run.start_team_note")}>
            <TeamPick value={run.start_team} none={t("run.start_team_queue")} markOff onChange={(v) => set({ start_team: v })} />
          </KeyField>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_weekly")}</legend>
        <div className="grid">
          {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
          {pick("weekly_bonus_amount")}
          <Switch path="run/stop_when_weekly_bonus_out" checked={run.stop_when_weekly_bonus_out}
            onChange={(on) => set({ stop_when_weekly_bonus_out: on })} />
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_failure")}</legend>
        <div className="grid">
          {pick("starlight_unaffordable")}
          <KeyField path="run/wipe_retries">
            <Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} />
          </KeyField>
          {pick("after_retries", t("run.after_retries_note"))}
        </div>
      </fieldset>
    </div>
  );
}

/** A team pick (the start team, a Luxcavation task's team): `none` first (null), then the settings' teams as they are now,
 * by name and slot, a disabled one marked when that stops the task (`markOff`). A team deleted since stays the value, shown
 * as deleted with why the task will stop, until another is picked: the agent stops the task at its start over it. */
function TeamPick({ value, none, markOff = false, onChange }: {
  value: string | null; none: string; markOff?: boolean; onChange: (v: string | null) => void;
}) {
  const { s, t } = useEditor();
  const ids = s.teams.map((x) => x.id);
  const team = s.teams.find((x) => x.id === value);
  const gone = value !== null && !team;
  const label = (id: string) => {
    if (id === "") return none;
    const x = s.teams.find((y) => y.id === id);
    if (!x) return fill(t("teamPick.gone"), { id });
    return fill(t(markOff && !x.enabled ? "teamPick.off" : "teamPick"), { name: x.name || "—", slot: x.game_team });
  };
  const warn = gone ? "teamPick.gone_note" : markOff && team && !team.enabled ? "teamPick.off_note" : null;
  return (<>
    <Select value={value ?? ""} options={["", ...ids, ...(gone ? [value] : [])]} label={label} onChange={(v) => onChange(v || null)} />
    {warn && <small className="caution">{t(warn)}</small>}
  </>);
}

/** A Luxcavation task's options (spec 04 section 12). */
function LuxFields({ task }: { task: keyof Settings["luxcavation"] }) {
  const { s, update, t, tv } = useEditor();
  const opts = s.luxcavation[task];
  const set = (patch: Partial<LuxOptions>) => update((d) => { Object.assign(d.luxcavation[task], patch); });
  const path = `luxcavation/${task}`;
  return (
    <div className="stack">
      <p className="muted">{withBreaks(t(`lux.${task}_note`))}</p>
      <div className="grid">
        <KeyField path={`${path}/mode`}>
          <Select value={opts.mode} options={LUX_MODES} label={(v) => tv("lux_mode", v)} onChange={(v) => set({ mode: v })} />
        </KeyField>
        <KeyField path={`${path}/count`} note={opts.mode === "daily" ? t("lux.count_unused") : undefined}>
          <Num value={opts.count} min={1} disabled={opts.mode === "daily"} onChange={(v) => set({ count: v })} />
        </KeyField>
        <KeyField path={`${path}/team`} note={t("lux.team_note")}>
          <TeamPick value={opts.team} none={t("lux.team_none")} onChange={(v) => set({ team: v })} />
        </KeyField>
        <Switch path={`${path}/consecutive`} checked={opts.consecutive} note={t("lux.consecutive_note")}
          onChange={(on) => set({ consecutive: on })} />
        <KeyField path={`${path}/retries`} note={t("lux.retries_note")}>
          <Num value={opts.retries} min={0} onChange={(v) => set({ retries: v })} />
        </KeyField>
      </div>
    </div>
  );
}

/** Charge Enkephalin's count (spec 04 section 12): it spends Lunacy, which its note says first. */
function ChargeFields() {
  const { s, update, t } = useEditor();
  return (
    <div className="stack">
      <p className="caution">{withBreaks(t("charge.note"))}</p>
      <div className="grid">
        <KeyField path="charge_enkephalin/count">
          <Num value={s.charge_enkephalin.count} min={0} max={10} onChange={(v) => update((d) => { d.charge_enkephalin.count = v; })} />
        </KeyField>
      </div>
    </div>
  );
}

/** The four options every task reads (spec 04 section 5): the webhook and three switches, each with its note. */
function GlobalOptions() {
  const { s, update, t } = useEditor();
  const set = (patch: Partial<Settings["run"]>) => update((d) => { Object.assign(d.run, patch); });
  return (
    <fieldset className="globals">
      <legend>{t("globals.title")}</legend>
      <p className="muted">{t("globals.note")}</p>
      <div className="grid">
        <KeyField path="run/webhook_url" note={t("run.webhook_url_note")}>
          <Input type="url" value={s.run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />
        </KeyField>
        {GLOBAL_KEYS.filter((k): k is Exclude<typeof k, "webhook_url"> => k !== "webhook_url").map((k) => (
          <Switch key={k} path={`run/${k}`} checked={s.run[k]} note={t(`run.${k}_note`)} onChange={(on) => set({ [k]: on })} />
        ))}
      </div>
    </fieldset>
  );
}

/** The last device scan: none yet, under way, the devices it found, or why it found none. */
type Scan = { state: "none" } | { state: "scanning" } | { state: "found"; devices: Device[] } | { state: "failed"; error: string };

/** A device of a scan as its pick list names it: a MuMu one by its instance. */
const deviceName = (t: (k: Key) => string, d: Device) =>
  d.mumu ? fill(t("emu.device_mumu"), { index: d.mumu.index, address: d.address }) : fill(t("emu.device"), { name: d.name, address: d.address });

/** The emulator the runner connects to (spec 04 section 14): its adb address, its MuMu instance and MuMuManager.exe; an empty
 * field is none (null). The scan lists the emulators that run, MuMu first; a pick fills in all three, saved with the rest. */
function EmulatorFields() {
  const { s, update, t } = useEditor();
  const set = (patch: Partial<Settings["emulator"]>) => update((d) => { Object.assign(d.emulator, patch); });
  const label = (k: "address" | "mumu_index" | "mumu_manager") =>
    <span className="keyed">{t(`emu.${k}`)}<code className="key" aria-hidden>emulator/{k}</code></span>;
  const text = (v: string) => (v.trim() === "" ? null : v);
  const running = isRunning(useRunner().view);
  // the last scan: its devices, or why it found none; null before the first
  const [scan, setScan] = useState<Scan>({ state: "none" });
  const find = () => {
    setScan({ state: "scanning" });
    api.scanDevices().then((devices) => setScan({ state: "found", devices }), (e) => setScan({ state: "failed", error: String(e) }));
  };
  const found = scan.state === "found" ? scan.devices : null;
  const at = found && s.emulator.address !== null ? found.findIndex((d) => sameAddress(d.address, s.emulator.address!)) : -1;
  const pick = (d: Device) => set({ address: d.address, mumu_index: d.mumu?.index ?? null, mumu_manager: d.mumu?.manager ?? null });
  return (
    <fieldset className="emulator" data-path="emulator">
      <legend>{t("emu.title")}</legend>
      <div className="row scan">
        <button type="button" disabled={scan.state === "scanning" || running} onClick={find}>
          {scan.state === "scanning" ? t("emu.scanning") : t("emu.scan")}
        </button>
        {found && found.length > 0 && (
          <label className="field">
            <span>{t("emu.found")}</span>
            <Choice value={at >= 0 ? String(at) : ""} onChange={(e) => { if (e.target.value !== "") pick(found[Number(e.target.value)]); }}>
              {at < 0 && <option value="">{t("emu.pick")}</option>}
              {found.map((d, j) => <option key={j} value={j}>{deviceName(t, d)}</option>)}
            </Choice>
            <small>{t("emu.found_note")}</small>
          </label>
        )}
        {found && found.length === 0 && <p className="muted">{t("emu.none_found")}</p>}
        {scan.state === "failed" && <p className="caution">{fill(t("emu.scan_failed"), { error: scan.error })}</p>}
      </div>
      <div className="row">
        <Field label={label("address")} path="emulator/address">
          <Input type="text" value={s.emulator.address ?? ""} spellCheck={false} onChange={(e) => set({ address: text(e.target.value) })} />
        </Field>
        <Field label={label("mumu_index")} path="emulator/mumu_index">
          <Input type="number" min={0} step={1} value={s.emulator.mumu_index ?? ""}
            onChange={(e) => set({ mumu_index: e.target.value === "" ? null : Math.max(0, Math.trunc(Number(e.target.value))) })} />
        </Field>
        <Field label={label("mumu_manager")} path="emulator/mumu_manager">
          <Input type="text" className="wide" value={s.emulator.mumu_manager ?? ""} spellCheck={false}
            onChange={(e) => set({ mumu_manager: text(e.target.value) })} />
        </Field>
      </div>
      <p className="muted">{withBreaks(t("emu.note"))}</p>
    </fieldset>
  );
}
