// The daily tab: the Luxcavation tasks' team (spec 04 section 12). Their mode, count, retries and Consecutive Battle, and
// Charge Enkephalin's Daily Count, are the client's task options (#781); #780 moves the team too.
import type { Settings } from "./model";
import { Field, Select, useEditor, withBreaks } from "./ui";

/** The Luxcavation tasks' team (#362); the client's task list picks and orders the tasks and sets their options. */
export function DailyTab() {
  const { t } = useEditor();
  return (
    <div className="stack">
      <p className="muted">{withBreaks(t("daily.note"))}</p>
      <LuxFields task="exp" />
      <LuxFields task="thread" />
    </div>
  );
}

function LuxFields({ task }: { task: keyof Settings["luxcavation"] }) {
  const { s, update, t } = useEditor();
  const opts = s.luxcavation[task];
  return (
    <fieldset>
      <legend>{t(`lux.${task}`)}</legend>
      <div className="grid">
        <Field label={t("lux.team")} path={`luxcavation/${task}/team`} note={t("lux.team_note")}>
          <Select value={opts.team ?? ""} options={["", ...s.teams.map((x) => x.id)]}
            label={(id) => { const x = s.teams.find((x) => x.id === id); return x ? `${x.name || "—"} (#${x.game_team})` : t("lux.team_none"); }}
            onChange={(v) => update((d) => { d.luxcavation[task].team = v || null; })} />
        </Field>
      </div>
    </fieldset>
  );
}
