// The window's own controls, which the system's hidden title bar would otherwise give (tauri.conf.json): its buttons at the
// title bar's right end, and the prompt that asks before the window closes or the page reloads with unsaved changes.
import { useEffect, useLayoutEffect, useRef, type ReactNode } from "react";
import * as api from "./api";
import type { Key } from "./i18n";
import { useEditor } from "./ui";

/** What the title bar gives up, in this order, while its parts ask more room than the window has (#746; English at 800 px wide
 * with unsaved changes asks 906 px), each step on top of the ones before: the gaps tighten and the file path's place goes
 * (the path has shrunk to nothing by then), the name plate and Save take less room inside, the language select's label
 * leaves the eye (the select keeps it as its name), and the save state's text may wrap. Save, Discard and the window buttons
 * keep their labels and their corner. index.css draws each step, `header[data-fit~="<step>"]`. */
export const FIT_STEPS = ["spacing", "padding", "label", "wrap"] as const;

/** The window's title bar: the system's is hidden (tauri.conf.json). Tauri drags the window from any of its parts that is not a
 * control (drag.js "deep"), and a double click there maximises it. It takes the steps of FIT_STEPS until its parts fit, again
 * each time what it holds or the window's width changes. */
export function TitleBar({ inert, children }: { inert?: boolean; children: ReactNode }) {
  const bar = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const el = bar.current!;
    const fit = () => {
      let n = 0;
      el.dataset.fit = "";
      while (n < FIT_STEPS.length && el.scrollWidth > el.clientWidth) el.dataset.fit = FIT_STEPS.slice(0, ++n).join(" ");
    };
    fit();
    // what it holds: the save state's text, Discard and Undo coming and going, Save's look, the language
    const held = new MutationObserver(fit);
    held.observe(el, { subtree: true, childList: true, characterData: true, attributeFilter: ["class"] });
    // the window's width: in the next frame, so the size a fit changes is not measured inside the observer's own callback
    let frame = 0;
    const width = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(fit);
    });
    width?.observe(el);
    let live = true;
    document.fonts?.ready.then(() => { if (live) fit(); }); // the name plate's face can load after the first fit
    return () => { live = false; held.disconnect(); width?.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  return <header ref={bar} inert={inert} data-tauri-drag-region="deep">{children}</header>;
}

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
