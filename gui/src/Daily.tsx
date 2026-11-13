// The daily tab: the Luxcavation tasks' options (spec 04 section 12) and Charge Enkephalin's.
import { LUX_MODES, type Luxcavation, type LuxMode, type Settings } from "./model";
import { Field, Input, Mark, Num, Select, useEditor, withBreaks } from "./ui";

/** The daily tasks' options (#362); the client's task list picks and orders the tasks. */
export function DailyTab() {
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
        {/* a switch as on the other tabs: the label's text the size of theirs, the note under it (#721) */}
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
    </fieldset>
  );
}
