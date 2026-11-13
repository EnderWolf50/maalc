// The run options tab (spec 04 section 5): what a run plays, the weekly bonuses, what happens when something fails, what the bot
// does on its own.
import { runEnum, type Settings } from "./model";
import { Field, Input, Mark, Num, Select, ToggleNum, useEditor } from "./ui";

export function RunTab() {
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
