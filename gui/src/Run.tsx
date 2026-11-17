// The Run tab (#814, spec #811 「設定視窗」, spec 04 sections 5, 12 and 14): the emulator on top; the task list on the
// left (ticks, drag or ↑↓: the run order) and the picked task's options on the right; the global options in a frame of their
// own; the place the runner's Start, Stop and live log take (the next ticket of #811). Each control writes the settings key
// the runner or the agent reads at a task's start, and shows that key beside its label: the agent's stop lines name an
// option by it ("run/start_team: team 'x' was deleted ..."). A team pick lists the settings' teams as they are now.
import type { ReactNode } from "react";
import { fill, type Key } from "./i18n";
import { schema, type LuxOptions, type Settings } from "./model";
import { Field, Input, Mark, Num, ReorderList, Select, ToggleNum, useEditor, usePick, withBreaks } from "./ui";

const RUN = schema.properties.run.properties as Record<string, { enum?: (string | number)[] }>;
const runEnum = (k: string) => RUN[k].enum!.map(String);
const LUX_MODES: string[] = schema.$defs.luxcavation.properties.mode.enum;
/** The task ids, in the order a new file lists them (agent/settings.schema.json $defs.task). */
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

/** A field's label with its settings key after it, small: the key a stop line names. A screen reader reads the label alone. */
function Keyed({ path }: { path: string }) {
  const { t } = useEditor();
  return <>{t(optionLabel(path))}<code className="key" aria-hidden>{path}</code></>;
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

export function RunTab() {
  const { s, update, t, bad } = useEditor();
  const [i, setSel] = usePick("tasks", s.tasks);
  // a task listed twice (a hand edit, which the check names) gets a row of its own: `repeat` counts its rows before this one
  const seen = new Map<string, number>();
  const rows = s.tasks.map((x) => { const repeat = seen.get(x.id) ?? 0; seen.set(x.id, repeat + 1); return { ...x, repeat }; });
  const picked = s.tasks[i];
  return (
    <div className="run-page">
      <EmulatorFields />
      <div className="split">
        <aside className="task-list" data-path="tasks">
          <h3>{t("tasks.title")}</h3>
          <p className="muted">{withBreaks(t("tasks.note"))}</p>
          <ReorderList items={rows} keyOf={(x) => (x.repeat ? `${x.id}#${x.repeat}` : x.id)} selected={i}
            onSelect={(j, list) => setSel(list[j].id)}
            badAt={(j) => bad(`tasks/${j}`) || (TASK_ROOTS[rows[j].id] ?? []).some(bad)}
            onChange={(moved) => update((d) => { d.tasks = moved.map(({ id, enabled }) => ({ id, enabled })); })}
            render={(x, j) => (
              <span className="task-row">
                <Input type="checkbox" checked={x.enabled} aria-label={fill(t("tasks.tick"), { name: taskName(t, x.id) })}
                  onChange={(e) => update((d) => { d.tasks[j].enabled = e.target.checked; })} />
                <span className={x.enabled ? "" : "muted"}>{taskName(t, x.id)}</span>
              </span>
            )} />
        </aside>
        <section className="task-options">
          {picked && <>
            {/* the task's id beside its name: the agent's stop lines name a task by it ("the MirrorDungeon task") */}
            <h3>{taskName(t, picked.id)} <code>{picked.id}</code></h3>
            <TaskOptions id={picked.id} />
          </>}
        </section>
      </div>
      <GlobalOptions />
      {/* the runner's Start, Stop, task states and live log (#811's next ticket) */}
      <section className="runner-slot" aria-label={t("runner.slot")}>
        <p className="muted">{t("runner.slot")}</p>
      </section>
    </div>
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

/** The emulator the runner connects to (spec 04 section 14): its adb address and its MuMu instance; an empty field is none
 * (null). The device scan and its pick list come with the runner's start (#811's next ticket). */
function EmulatorFields() {
  const { s, update, t } = useEditor();
  const set = (patch: Partial<Settings["emulator"]>) => update((d) => { Object.assign(d.emulator, patch); });
  const label = (k: "address" | "mumu_index") => <>{t(`emu.${k}`)}<code className="key" aria-hidden>emulator/{k}</code></>;
  return (
    <fieldset className="emulator" data-path="emulator">
      <legend>{t("emu.title")}</legend>
      <div className="row">
        <Field label={label("address")} path="emulator/address">
          <Input type="text" value={s.emulator.address ?? ""} spellCheck={false}
            onChange={(e) => set({ address: e.target.value.trim() === "" ? null : e.target.value })} />
        </Field>
        <Field label={label("mumu_index")} path="emulator/mumu_index">
          <Input type="number" min={0} step={1} value={s.emulator.mumu_index ?? ""}
            onChange={(e) => set({ mumu_index: e.target.value === "" ? null : Math.max(0, Math.trunc(Number(e.target.value))) })} />
        </Field>
      </div>
      <p className="muted">{withBreaks(t("emu.note"))}</p>
    </fieldset>
  );
}
