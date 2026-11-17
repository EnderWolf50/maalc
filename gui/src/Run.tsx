// The Run tab (#814, spec #811 「設定視窗」, spec 04 sections 5, 12 and 14): the emulator on top; the task list on the
// left (ticks, drag or ↑↓: the run order) and the picked task's options on the right; the global options in a frame of their
// own; the place the runner's Start, Stop and live log take (the next ticket of #811). Each control writes the settings key
// the runner or the agent reads at a task's start. A team pick lists the settings' teams as they are now.
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

/** The task whose options hold a settings path: the Run tab shows that task's options to reach the field. Undefined for a
 * global option and anything else. */
export function taskOfPath(path: string): string | undefined {
  const [section, key] = path.split("/");
  if (section === "luxcavation") return ({ exp: "ExpLuxcavation", thread: "ThreadLuxcavation" } as Record<string, string>)[key];
  if (section === "charge_enkephalin") return "ChargeEnkephalin";
  if (section === "run" && key !== undefined && !(GLOBAL_KEYS as readonly string[]).includes(key)) return "MirrorDungeon";
  return undefined;
}
/** A task's name in the GUI's language; an id the GUI does not know (a hand edit, which the schema check names) as it is. */
export const taskName = (t: (k: Key) => string, id: string) => (TASKS.includes(id) ? t(`task.${id}` as Key) : id);
/** The settings paths that hold a task's options: a problem under one marks the task's row. */
const OPTION_ROOTS: Record<string, string[]> = {
  MirrorDungeon: Object.keys(RUN).filter((k) => !(GLOBAL_KEYS as readonly string[]).includes(k)).map((k) => `run/${k}`),
  ExpLuxcavation: ["luxcavation/exp"], ThreadLuxcavation: ["luxcavation/thread"], ChargeEnkephalin: ["charge_enkephalin"],
};

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
            badAt={(j) => bad(`tasks/${j}`) || (OPTION_ROOTS[rows[j].id] ?? []).some(bad)}
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
    <Field label={t(`run.${k}`)} path={`run/${k}`} note={note}>
      <Select value={run[k]} options={runEnum(k)} label={(v) => tv(k, v)} onChange={(v) => set({ [k]: v })} />
    </Field>
  );
  return (
    <div className="groups">
      <fieldset>
        <legend>{t("run.group_run")}</legend>
        <div className="grid">
          {pick("difficulty")}
          <Field label={t("run.target_floor")} path="run/target_floor" note={pastFive ? t("run.target_floor_note") : undefined}>
            <Select value={String(run.target_floor)} options={runEnum("target_floor")} label={(v) => tv("target_floor", v)}
              onChange={(v) => set({ target_floor: Number(v) })} />
            {/* Remove with #434: until the entrance switches Parallel Superposition on, a target above 5 still stops at floor 5. */}
            {pastFive && <small>{t("run.target_floor_entry_note")}</small>}
          </Field>
          <ToggleNum label={t("run.runs")} path="run/runs" value={run.runs} on={1} min={1} note={t("run.runs_note")}
            onChange={(v) => set({ runs: v })} />
          {pick("theme_pack_refresh", t("run.theme_pack_refresh_note"))}
          <Field label={t("run.start_team")} path="run/start_team" note={t("run.start_team_note")}>
            <TeamPick value={run.start_team} none={t("run.start_team_queue")} markOff onChange={(v) => set({ start_team: v })} />
          </Field>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_weekly")}</legend>
        <div className="grid">
          {pick("weekly_bonus_use", run.weekly_bonus_use === "normal" ? t("run.weekly_bonus_normal_note") : undefined)}
          {pick("weekly_bonus_amount")}
          <Mark as="label" className="check wide" path="run/stop_when_weekly_bonus_out">
            <Input type="checkbox" checked={run.stop_when_weekly_bonus_out}
              onChange={(e) => set({ stop_when_weekly_bonus_out: e.target.checked })} />
            {t("run.stop_when_weekly_bonus_out")}
          </Mark>
        </div>
      </fieldset>
      <fieldset>
        <legend>{t("run.group_failure")}</legend>
        <div className="grid">
          {pick("starlight_unaffordable")}
          <Field label={t("run.wipe_retries")} path="run/wipe_retries">
            <Num value={run.wipe_retries} min={0} onChange={(v) => set({ wipe_retries: v })} />
          </Field>
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
        <Field label={t("lux.mode")} path={`${path}/mode`}>
          <Select value={opts.mode} options={LUX_MODES} label={(v) => tv("lux_mode", v)} onChange={(v) => set({ mode: v })} />
        </Field>
        <Field label={t("lux.count")} path={`${path}/count`} note={opts.mode === "daily" ? t("lux.count_unused") : undefined}>
          <Num value={opts.count} min={1} disabled={opts.mode === "daily"} onChange={(v) => set({ count: v })} />
        </Field>
        <Field label={t("lux.team")} path={`${path}/team`} note={t("lux.team_note")}>
          <TeamPick value={opts.team} none={t("lux.team_none")} onChange={(v) => set({ team: v })} />
        </Field>
        <Mark className="toggle" path={`${path}/consecutive`}>
          <label className="check">
            <Input type="checkbox" checked={opts.consecutive} onChange={(e) => set({ consecutive: e.target.checked })} />{t("lux.consecutive")}
          </label>
          <small>{withBreaks(t("lux.consecutive_note"))}</small>
        </Mark>
        <Field label={t("lux.retries")} path={`${path}/retries`} note={t("lux.retries_note")}>
          <Num value={opts.retries} min={0} onChange={(v) => set({ retries: v })} />
        </Field>
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
        <Field label={t("charge.count")} path="charge_enkephalin/count">
          <Num value={s.charge_enkephalin.count} min={0} max={10} onChange={(v) => update((d) => { d.charge_enkephalin.count = v; })} />
        </Field>
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
        <Field label={t("run.webhook_url")} path="run/webhook_url" note={t("run.webhook_url_note")}>
          <Input type="url" value={s.run.webhook_url} onChange={(e) => set({ webhook_url: e.target.value })} />
        </Field>
        {(["auto_accept_terms", "auto_download", "keep_dismissed_screens"] as const).map((k) => (
          <Mark key={k} className="toggle" path={`run/${k}`}>
            <label className="check">
              <Input type="checkbox" checked={s.run[k]} onChange={(e) => set({ [k]: e.target.checked })} />{t(`run.${k}`)}
            </label>
            <small>{withBreaks(t(`run.${k}_note`))}</small>
          </Mark>
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
  return (
    <fieldset className="emulator" data-path="emulator">
      <legend>{t("emu.title")}</legend>
      <div className="row">
        <Field label={t("emu.address")} path="emulator/address">
          <Input type="text" value={s.emulator.address ?? ""} placeholder="127.0.0.1:16384" spellCheck={false}
            onChange={(e) => set({ address: e.target.value.trim() === "" ? null : e.target.value })} />
        </Field>
        <Field label={t("emu.mumu_index")} path="emulator/mumu_index">
          <Input type="number" min={0} step={1} value={s.emulator.mumu_index ?? ""}
            onChange={(e) => set({ mumu_index: e.target.value === "" ? null : Math.max(0, Math.trunc(Number(e.target.value))) })} />
        </Field>
      </div>
      <p className="muted">{withBreaks(t("emu.note"))}</p>
    </fieldset>
  );
}
