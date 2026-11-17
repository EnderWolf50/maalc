// The read-back's one-time notice (#814): where the migrated file's run values came from, what came back and what the user
// sets again, above every tab until dismissed. App.tsx shows it once the migrated file is written.
import { fill, type Key } from "./i18n";
import type { Missed, Report, Source } from "./readBack";
import { taskName, taskOfPath } from "./Run";
import { useEditor } from "./ui";

const FROM: Record<Source, Key> = { mxu: "rb.from_mxu", v20: "rb.from_v20", defaults: "rb.from_defaults", file: "rb.from_file" };
/** The text key of a task option's label (the Run tab's), by its settings path. */
const optionKey = (path: string): Key => {
  const parts = path.split("/");
  const key = parts[parts.length - 1];
  return (parts[0] === "luxcavation" ? `lux.${key}` : parts[0] === "charge_enkephalin" ? "charge.count" : `run.${key}`) as Key;
};

export function ReadBackNotice({ report, onDismiss }: { report: Report; onDismiss: () => void }) {
  const { s, t, tv } = useEditor();
  const where = (path: string) => {
    const task = taskOfPath(path);
    return `${task ? taskName(t, task) : t("globals.title")} · ${t(optionKey(path))}`;
  };
  const none = (path: string) => t(path === "run/start_team" ? "run.start_team_queue" : "lux.team_none");
  const value = (path: string, v: unknown) => {
    const key = path.split("/").pop()!;
    if (path.endsWith("team")) {
      const team = s.teams.find((x) => x.id === v);
      return team ? fill(t("teamPick"), { name: team.name || "—", slot: team.game_team }) : v === null ? none(path) : String(v);
    }
    if (key === "runs" && v === null) return t("rb.no_limit");
    if (key === "webhook_url") return t("rb.set"); // the address stays off the screen: it may be a secret
    if (typeof v === "boolean") return t(v ? "rb.on" : "rb.off");
    if (key === "mode") return tv("lux_mode", String(v));
    return tv(key, String(v));
  };
  const missed = (m: Missed) => {
    if (m.kind === "webhook") return t("rb.webhook");
    if (m.kind === "value") return fill(t("rb.value"), { where: where(m.path), value: m.value });
    if (m.kind === "team") return fill(t("rb.team"), { where: where(m.path), team: m.label ?? m.id, none: none(m.path) });
    if (m.kind === "task") return fill(t("rb.task"), { name: m.name });
    return fill(t("rb.twice"), { task: taskName(t, m.task), n: m.n });
  };
  const ticked = report.tasks?.filter((x) => x.enabled).map((x) => taskName(t, x.id)) ?? [];
  return (
    <section className="readback" aria-labelledby="readback-title">
      <h3 id="readback-title">{t("rb.title")}</h3>
      <p>{fill(t(FROM[report.source]), { version: report.from, instance: report.instance ?? "" })}</p>
      {report.source === "file" && report.instance !== null && <p>{fill(t("rb.file_tasks"), { instance: report.instance })}</p>}
      {report.instances > 1 && <p>{fill(t("rb.instances"), { n: report.instances })}</p>}
      {report.problems.map((why) => <p key={why}>{fill(t("rb.problem"), { why })}</p>)}
      <h4>{t(report.read.length ? "rb.read" : "rb.read_none")}</h4>
      <ul className="read">
        {report.read.map((r) => <li key={r.path}>{fill(t("rb.row"), { where: where(r.path), value: value(r.path, r.value) })}</li>)}
        <li>{report.tasks === null ? t("rb.tasks_default")
          : ticked.length ? fill(t("rb.tasks"), { tasks: ticked.join(t("rb.sep")) }) : t("rb.tasks_none")}</li>
        {report.address !== null && <li>{fill(t("rb.address"), { address: report.address })}</li>}
      </ul>
      {report.missed.length > 0 && <>
        <h4>{t("rb.missed")}</h4>
        <ul className="missed">{report.missed.map((m, i) => <li key={i}>{missed(m)}</li>)}</ul>
      </>}
      <button type="button" onClick={onDismiss}>{t("rb.dismiss")}</button>
    </section>
  );
}
