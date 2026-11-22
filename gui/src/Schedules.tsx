// The Run tab's scheduled runs (#816, spec #811 「定時執行」, spec 04 section 14): add and delete a schedule, pick its weekdays,
// its time and whether it wakes the PC. A save writes each schedule's Windows Task Scheduler task (App, api.syncSchedules);
// the section says how that went, each task's name, and what came of the last scheduled run's start. A run reads none of
// this, so it stays open to edits during a run.
import { fill, type Key } from "./i18n";
import { DAYS, newSchedule, useSchedules, type ScheduleView } from "./schedule";
import { Field, Input, Mark, useEditor, useHelp } from "./ui";

/** The last scheduled start as the section says it, in the window's language. */
function sayOutcome(t: (k: Key) => string, { id, at, outcome: o }: NonNullable<ScheduleView["last"]>) {
  const why = o.kind !== "refused" ? ""
    : typeof o.why === "object" ? o.why.error : t(o.why === "save" ? "sched.why_save" : `runner.blocked_${o.why}` as Key);
  const code = o.kind === "crashed" ? o.code ?? "—" : ""; // as the Run tab writes a crash's exit code
  return fill(t(`sched.last.${o.kind}` as Key), { id, at, why, code });
}

export function SchedulesSection() {
  const { s, update, t } = useEditor();
  const { synced, saved, last } = useSchedules();
  const list = s.schedules;
  const unsaved = JSON.stringify(list) !== saved;
  // the task of each schedule the last sync wrote or found as it should be: one it could not write has none to name
  const done = synced && "done" in synced ? synced.done : null;
  const taskOf = (id: string) => {
    const name = done ? done.prefix + id : "";
    return done && (done.written.includes(name) || done.kept.includes(name)) ? name : null;
  };
  const setDay = (i: number, day: string, on: boolean) => update((d) => {
    const had = d.schedules[i].days;
    d.schedules[i].days = DAYS.filter((x) => (x === day ? on : had.includes(x)));
  });
  // how the schedules work is the title's tooltip and the section's description (spec #871 「說明文字」); on the page, while
  // there is one, only when it will not run
  const help = useHelp(t("sched.note"));
  return (
    <fieldset className="schedules" data-path="schedules" aria-describedby={help.describes}>
      <legend title={help.title}>{t("sched.title")}</legend>
      {list.length > 0 && <p className="muted">{t("sched.logged_on_only")}</p>}
      {list.length ? (
        <ol className="schedule-list" aria-label={t("sched.title")}>
          {list.map((x, i) => {
            const path = `schedules/${i}`;
            return (
              <li key={i} data-path={path}>
                <Mark className="days" path={`${path}/days`}>
                  <span className="label">{t("sched.days")}</span>
                  {DAYS.map((day) => {
                    const on = x.days.includes(day);
                    // the last day ticked stays ticked: a schedule runs on a day at least
                    const last = on && x.days.length === 1;
                    return (
                      <label key={day} className="day" title={last ? t("sched.days_note") : undefined}>
                        <Input type="checkbox" checked={on} disabled={last} onChange={(e) => setDay(i, day, e.target.checked)} />
                        {t(`sched.day.${day}` as Key)}
                      </label>
                    );
                  })}
                </Mark>
                <Field label={t("sched.time")} path={`${path}/time`}>
                  {/* cleared, it keeps the time it had: a schedule has one */}
                  <Input type="time" value={x.time} required
                    onChange={(e) => { const v = e.target.value; if (v) update((d) => { d.schedules[i].time = v; }); }} />
                </Field>
                {/* what it does, its tooltip; what it needs from Windows, under it while it is on */}
                <Mark className="toggle" path={`${path}/wake`} help={t("sched.wake_note")}>
                  <label className="check">
                    <Input type="checkbox" checked={x.wake} onChange={(e) => update((d) => { d.schedules[i].wake = e.target.checked; })} />
                    {t("sched.wake")}
                  </label>
                  {x.wake && <small>{t("sched.wake_needs")}</small>}
                </Mark>
                <button type="button" className="danger" aria-label={fill(t("sched.remove"), { n: i + 1 })}
                  onClick={() => update((d) => { d.schedules.splice(i, 1); })}>{t("remove")}</button>
                {!unsaved && taskOf(x.id) && <small className="task-name">{fill(t("sched.task"), { name: taskOf(x.id)! })}</small>}
              </li>
            );
          })}
        </ol>
      ) : <p className="muted">{t("sched.none")}</p>}
      <div className="row">
        <button type="button" onClick={() => update((d) => { d.schedules.push(newSchedule(d.schedules)); })}>{t("sched.add")}</button>
      </div>
      <SyncState unsaved={unsaved} />
      {last && <p className="sched-last" role="status">{sayOutcome(t, last)}</p>}
      {help.copy}
    </fieldset>
  );
}

/** How the Task Scheduler stands: an edit not saved yet, the last sync's tasks, what it could not write, or why it failed. */
function SyncState({ unsaved }: { unsaved: boolean }) {
  const { t } = useEditor();
  const { synced } = useSchedules();
  if (unsaved) return <p className="caution">{t("sched.unsaved")}</p>;
  if (!synced) return null;
  // the state the window found the Task Scheduler in, not an action of the user's that failed: no alert
  if ("error" in synced) return <p className="caution">{fill(t("sched.sync_failed"), { error: synced.error })}</p>;
  const { written, kept, errors } = synced.done;
  const n = written.length + kept.length;
  return (<>
    {/* no task and none refused: 「還沒有排程。」 says it already */}
    {(n > 0 || errors.length > 0) && <p className="muted">{fill(t("sched.synced"), { n })}</p>}
    {errors.length > 0 && (
      <div className="caution">
        <p>{t("sched.sync_errors")}</p>
        <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
      </div>
    )}
  </>);
}
