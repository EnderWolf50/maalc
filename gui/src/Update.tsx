// The window's self-update (#817, spec #811 「自動更新」, src-tauri/src/update.rs): the header's notice of a newer release and
// how far its update is, and the page's notices of what went wrong and of how the last apply went. App.tsx holds the state
// and runs the steps: the click downloads, the download checks the sha256 and unpacks, and the apply waits for no run.
import type { CSSProperties } from "react";
import type { Release, UpdateOutcome } from "./api";
import { fill } from "./i18n";
import { useEditor, withBreaks } from "./ui";

/** What failed: the download's sha256 check, the download (or its unpack), or the start of the apply. */
export type Failure = { why: "mismatch" | "download" | "apply"; error: string };

/** Where an update is. `ready`: downloaded and unpacked, waiting for no run (or for the click after a refused save);
 * `failed`: the page's FailureNotice says why. */
export type UpdateStep =
  | { step: "available" }
  | { step: "download"; received: number; total: number }
  | { step: "verify" }
  | { step: "extract" }
  | { step: "ready" }
  | { step: "applying" }
  | { step: "failed" };

/** The newer release, this build's version, and where its update is. */
export interface Update { current: string; release: Release; at: UpdateStep }

/** The notice's words beside its mark, an arrow into a tray. In a header too narrow for its parts (the `label` step of
 * WindowControls.tsx FIT_STEPS) the mark shows alone and the words leave the eye only: they stay the notice's name. */
const markAndWords = (text: string) => (<>
  <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 .5v6M2.5 4 5 6.5 7.5 4M.5 9.5h9" /></svg>
  <span className="words">{text}</span>
</>);

/** The header's notice: a button while there is something to click (update, apply, try again), the step's name while it runs.
 * During a run the apply waits: its button says so and stays off until the run ends. Each one's tooltip says more, or its
 * words when they do not show. */
export function UpdateChip({ update, running, onUpdate, onApply }: {
  update: Update; running: boolean; onUpdate: () => void; onApply: () => void;
}) {
  const { t } = useEditor();
  const { release: { version }, current, at } = update;
  const v = { version, current };
  switch (at.step) {
    case "available":
      return <button type="button" className="update" title={fill(t("update.title"), v)} onClick={onUpdate}>{markAndWords(fill(t("update.available"), v))}</button>;
    case "download": {
      const pct = at.total > 0 ? Math.min(100, Math.floor((at.received / at.total) * 100)) : null;
      const text = pct === null ? fill(t("update.downloading_mb"), { mb: Math.floor(at.received / 2 ** 20) }) : fill(t("update.downloading"), { pct });
      return (
        <span className="update busy" role="progressbar" aria-label={fill(t("update.label"), v)} aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={pct ?? undefined} title={text} style={{ "--done": `${pct ?? 0}%` } as CSSProperties}>
          {markAndWords(text)}
        </span>
      );
    }
    case "verify":
    case "extract":
    case "applying":
      return <span className="update busy" role="status" title={t(`update.${at.step}`)}>{markAndWords(t(`update.${at.step}`))}</span>;
    case "ready":
      return (
        <button type="button" className="update" disabled={running} onClick={onApply}
          title={fill(t(running ? "update.after_run_title" : "update.apply_title"), v)}>
          {markAndWords(fill(t(running ? "update.after_run" : "update.apply"), v))}
        </button>
      );
    case "failed":
      return <button type="button" className="update bad" title={fill(t("update.retry_title"), v)} onClick={onUpdate}>{markAndWords(t("update.retry"))}</button>;
  }
}

/** A notice above every tab until dismissed; `why`: the backend's own words, under the sentence. */
function Notice({ text, why, bad, onDismiss }: { text: string; why?: string; bad: boolean; onDismiss: () => void }) {
  const { t } = useEditor();
  return (
    <section className={"update-notice" + (bad ? " bad" : "")} role={bad ? "alert" : "status"} aria-label={t("update.notice")}>
      <h3>{t("update.notice")}</h3>
      <p>{withBreaks(text)}</p>
      {why && <p className="why">{why}</p>}
      <button type="button" onClick={onDismiss}>{t("update.dismiss")}</button>
    </section>
  );
}

const FAILED = { mismatch: "update.mismatch", download: "update.download_failed", apply: "update.apply_failed" } as const;

/** Why the update of `version` stopped: a sha256 that differs (the two hashes under it), a download that failed, or an apply
 * that could not start. */
export function FailureNotice({ version, failure, onDismiss }: { version: string; failure: Failure; onDismiss: () => void }) {
  const { t } = useEditor();
  const text = fill(t(FAILED[failure.why]), { version, error: failure.error });
  return <Notice text={text} why={failure.why === "mismatch" ? failure.error : undefined} bad onDismiss={onDismiss} />;
}

/** How the last apply went, as the window read it at its start: it went through; it failed and the old version is back; it
 * failed and not all of it went back; or it was cut short. The last two say where the old files are. */
export function OutcomeNotice({ outcome, onDismiss }: { outcome: UpdateOutcome; onDismiss: () => void }) {
  const { t } = useEditor();
  const key = outcome.state === "done" ? "update.done" : outcome.state === "applying" ? "update.cut_short"
    : outcome.restored ? "update.failed_restored" : "update.failed_left";
  const v = { from: outcome.from, to: outcome.to, error: outcome.error ?? "" };
  // where the old files are, when the update left them for the user (update.rs Outcome::keeps_old)
  const left = outcome.state === "applying" || (outcome.state === "failed" && !outcome.restored);
  const text = [fill(t(key), v), ...(left ? [fill(t("update.old_files"), v)] : [])].join("\n");
  return <Notice text={text} bad={outcome.state !== "done"} onDismiss={onDismiss} />;
}
