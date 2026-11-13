// File access through the Rust side (src-tauri/src/lib.rs). In a plain browser (`pnpm dev`,
// screenshots) it falls back to localStorage so the editor can be tried without Tauri.
import { invoke, isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import bundledThemePacks from "../../assets/resource/base/data/theme_packs.yaml?raw";
import { parseThemePacks, type ThemePacks } from "./model";

const tauri = isTauri();

let themePacks: Promise<ThemePacks> | undefined;
/** Read once from <root>; the browser falls back to the repo's copy. */
export const loadThemePacks = (): Promise<ThemePacks> =>
  (themePacks ??= (tauri ? invoke<string>("load_theme_packs") : Promise.resolve(bundledThemePacks)).then(parseThemePacks));

export const rootDir = (): Promise<string> => (tauri ? invoke("root_dir") : Promise.resolve("(browser)"));

export const loadSettings = (): Promise<string | null> =>
  tauri ? invoke("load_settings") : Promise.resolve(localStorage.getItem("settings.json"));

/** The error text of a save refused because the file no longer holds `expected` (lib.rs save_settings). */
export const CHANGED = "settings.json changed on disk";
export const isChanged = (e: unknown) => String(e).includes(CHANGED);

/** expected: the text last read or written, null for no file then; anything else there now refuses the save (#501). */
export function saveSettings(text: string, expected: string | null): Promise<void> {
  if (tauri) return invoke("save_settings", { text, expected });
  if (localStorage.getItem("settings.json") !== expected) return Promise.reject(CHANGED);
  localStorage.setItem("settings.json", text);
  return Promise.resolve();
}

/** Ask `keepOpen` each time the user closes the window (its ✕, Alt+F4): true keeps it open. Returns the function that stops
 * asking. With a listener, Tauri leaves the closing to the page, which destroys the window (needs core:window:allow-destroy,
 * capabilities/default.json). A plain browser has no window to keep. */
export function onCloseRequested(keepOpen: () => boolean): () => void {
  if (!tauri) return () => {};
  const listening = getCurrentWindow().onCloseRequested((e) => { if (keepOpen()) e.preventDefault(); });
  return () => { listening.then((stop) => stop()); };
}

/** Close the window without asking again. */
export const closeWindow = (): Promise<void> => (tauri ? getCurrentWindow().destroy() : Promise.resolve());

/** Spec 04 section 12 / spec 06: a reset marker holds only the team id and the time. */
export function resetTeamTimes(teamId: string): Promise<void> {
  const line = JSON.stringify({ reset: teamId, time: new Date().toISOString() });
  if (tauri) return invoke("append_runs_log", { line });
  localStorage.setItem("runs.jsonl", (localStorage.getItem("runs.jsonl") ?? "") + line + "\n");
  return Promise.resolve();
}
