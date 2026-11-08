// File access through the Rust side (src-tauri/src/lib.rs). In a plain browser (`pnpm dev`,
// screenshots) it falls back to localStorage so the editor can be tried without Tauri.
import { invoke, isTauri } from "@tauri-apps/api/core";
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

/** expected: the text last read or written, null for a file not there then; another text there refuses the save (#501). */
export function saveSettings(text: string, expected: string | null): Promise<void> {
  if (tauri) return invoke("save_settings", { text, expected });
  if (expected !== null && localStorage.getItem("settings.json") !== expected) return Promise.reject(CHANGED);
  localStorage.setItem("settings.json", text);
  return Promise.resolve();
}

/** Spec 04 section 12 / spec 06: a reset marker holds only the team id and the time. */
export function resetTeamTimes(teamId: string): Promise<void> {
  const line = JSON.stringify({ reset: teamId, time: new Date().toISOString() });
  if (tauri) return invoke("append_runs_log", { line });
  localStorage.setItem("runs.jsonl", (localStorage.getItem("runs.jsonl") ?? "") + line + "\n");
  return Promise.resolve();
}
