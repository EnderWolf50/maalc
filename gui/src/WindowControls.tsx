// The window's own controls, which the system's hidden title bar would otherwise give (tauri.conf.json): its buttons at the
// title bar's right end, and the prompt that asks before the window closes or the page reloads with unsaved changes.
import { useEffect, useRef, type ReactNode } from "react";
import * as api from "./api";
import type { Key } from "./i18n";
import { useEditor } from "./ui";

/** What the prompt guards: the window closes, or the page reloads (F5, Ctrl+R). */
export type Leave = "close" | "reload";

/** The window's own buttons at the title bar's right end. Close is a close request, as Alt+F4 is: with unsaved changes the
 * prompt asks first. A call the window refuses (no permission) says why in the save state, as a failed close does. */
export function WindowButtons({ t, maximized, onError }: { t: (k: Key) => string; maximized: boolean; onError: (e: unknown) => void }) {
  const button = (name: string, run: () => Promise<void>, glyph: ReactNode, className?: string) => (
    <button type="button" className={className} aria-label={name} title={name} onClick={() => { run().catch(onError); }}>
      <svg viewBox="0 0 10 10" aria-hidden="true">{glyph}</svg>
    </button>
  );
  return (
    <div className="winctl">
      {button(t("win.minimize"), api.minimizeWindow, <path d="M0 5.5h10" />)}
      {button(t(maximized ? "win.restore" : "win.maximize"), api.toggleMaximize, maximized
        ? <path d="M2.5 2.5V.5h7v7h-2M.5 2.5h7v7h-7z" />
        : <rect x="0.5" y="0.5" width="9" height="9" />)}
      {button(t("win.close"), api.requestClose, <path d="M0 0l10 10M10 0L0 10" />, "close")}
    </div>
  );
}

/** Asked when the window closes, or the page reloads (F5, Ctrl+R), with unsaved changes: save and go on, go on without saving,
 * or stay (Esc). The focus starts on the choice that keeps the edits. */
export function LeavePrompt({ kind, onSave, onDiscard, onCancel }: {
  kind: Leave; onSave: () => void; onDiscard: () => void; onCancel: () => void;
}) {
  const { t } = useEditor();
  const cancel = useRef(onCancel);
  cancel.current = onCancel;
  useEffect(() => {
    // from the document: a click on the dimmed page behind takes the focus out of the prompt
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") cancel.current(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="ask-back">
      <div className="ask" role="alertdialog" aria-modal="true" aria-labelledby="close-ask">
        <p id="close-ask">{t(`${kind}Ask`)}</p>
        <div className="ask-buttons">
          <button type="button" className="primary" autoFocus onClick={onSave}>{t(`${kind}Save`)}</button>
          <button type="button" className="danger" onClick={onDiscard}>{t(`${kind}Discard`)}</button>
          <button type="button" onClick={onCancel}>{t("cancel")}</button>
        </div>
      </div>
    </div>
  );
}
