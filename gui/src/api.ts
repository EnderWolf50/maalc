// File access through the Rust side (src-tauri/src/lib.rs). In a plain browser (`pnpm dev`,
// screenshots) it falls back to localStorage so the editor can be tried without Tauri.
import { Channel, convertFileSrc, invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { Settings } from "./model";
import type { Device, Message } from "./runner";

const tauri = isTauri();

/** The game data the window shows, read at run time from <root>/resource/base/data (lib.rs load_game_data), so what the
 * Agent downloads shows without a new build. `texts`: each file's text by its path under data/; `folders`: the file names
 * in each image folder; `url`: where the page loads an image from, a path under data/. */
export interface GameFiles {
  texts: Record<string, string>;
  folders: Record<string, string[]>;
  url: (path: string) => string;
}

/** Every text file the window reads (paths under data/). */
export const GAME_TEXTS = [
  "gift_effects.json", "gift_lists.yaml", "gift_recipes.json", "gift_search.json", "graces.json", "shop.yaml", "theme_packs.yaml",
  "sinner_cards/index.json", "theme_pack_covers/index.json", "gift_plates/plates.json",
];
/** Every image folder the window lists (under data/). */
export const GAME_FOLDERS = ["gift_icons", "keyword_icons", "buf_icons", "grace_icons", "sinner_cards", "theme_pack_covers", "gift_plates"];

const DATA = "../../assets/resource/base/data/";
const under = (key: string) => key.slice(key.indexOf("/data/") + "/data/".length);

/** A plain browser (`pnpm dev`, the tests): the repo's own data folder. Only the dev server and the tests get here: in a
 * build `import.meta.env.DEV` is false, so none of these files reaches the bundle. */
async function browserFiles(): Promise<GameFiles> {
  if (!import.meta.env.DEV) throw new Error("the game data can be read only by the app (no Tauri here)");
  const raw = import.meta.glob(["../../assets/resource/base/data/*.{json,yaml}", "../../assets/resource/base/data/*/{index,plates}.json"], { query: "?raw", import: "default" });
  const images = import.meta.glob("../../assets/resource/base/data/*/*.webp", { query: "?url", import: "default" });
  const texts: Record<string, string> = {};
  for (const name of GAME_TEXTS) {
    const read = raw[DATA + name];
    if (!read) throw new Error(`${name}: not in the repo's data folder`);
    texts[name] = (await read()) as string;
  }
  const folders: Record<string, string[]> = Object.fromEntries(GAME_FOLDERS.map((f) => [f, []]));
  const urls = new Map<string, string>();
  await Promise.all(Object.entries(images).map(async ([key, load]) => {
    const path = under(key), folder = path.slice(0, path.indexOf("/"));
    urls.set(path, (await load()) as string);
    folders[folder]?.push(path.slice(folder.length + 1));
  }));
  return { texts, folders, url: (path) => urls.get(path) ?? "" };
}

let gameFiles: Promise<GameFiles> | undefined;
/** Read once. Rejects with the reason (a missing folder or file) when the data cannot be read. */
export const loadGameFiles = (): Promise<GameFiles> => (gameFiles ??= tauri
  ? invoke<{ dir: string; texts: Record<string, string>; folders: Record<string, string[]> }>("load_game_data", { texts: GAME_TEXTS, folders: GAME_FOLDERS })
      .then(({ dir, texts, folders }) => ({ texts, folders, url: (path: string) => convertFileSrc(`${dir}/${path}`) }))
  : browserFiles());

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

/** Keep a settings file of an older version beside the settings file, as it was, before its migration is written back
 * (#782): config/settings.v<version>.json, written over when there is one (lib.rs save_old_settings). */
export function saveOldSettings(version: number, text: string): Promise<void> {
  if (tauri) return invoke("save_old_settings", { version, text });
  localStorage.setItem(`settings.v${version}.json`, text);
  return Promise.resolve();
}

/** A file of config/ the read-back reads once (#814, readBack.ts READ_BACK_FILES; lib.rs load_read_back refuses any
 * other): its text, null when it is not there. Nothing here writes one. */
export const loadReadBack = (name: string): Promise<string | null> =>
  tauri ? invoke("load_read_back", { name }) : Promise.resolve(localStorage.getItem(name));

/** Ask `keepOpen` each time the user closes the window (its ✕, Alt+F4): true keeps it open. Returns the function that stops
 * asking. With a listener, Tauri leaves the closing to the page, which destroys the window (needs core:window:allow-destroy,
 * capabilities/default.json). A plain browser has no window to keep. */
export function onCloseRequested(keepOpen: () => boolean | Promise<boolean>): () => void {
  if (!tauri) return () => {};
  const listening = getCurrentWindow().onCloseRequested(async (e) => { if (await keepOpen()) e.preventDefault(); });
  return () => { listening.then((stop) => stop()); };
}

const channel = (onMessage: (m: Message) => void) => {
  const c = new Channel<Message>();
  c.onmessage = onMessage;
  return c;
};

/** Start the runner on `entries` (the ticked tasks' entry nodes, in run order) and `device` (lib.rs start_run): each message
 * of the run goes to `onMessage`, the exit last. Each task reads its options from the settings file at its start, so the
 * page saves first. Refused while a run is under way, and in a plain browser, which has no runner. */
export function startRun(entries: string[], device: Settings["emulator"], onMessage: (m: Message) => void): Promise<void> {
  if (!tauri) return Promise.reject(new Error("the runner runs only in the app"));
  return invoke("start_run", { tasks: entries, device, onMessage: channel(onMessage) });
}

/** Ask the run to stop: the runner stops MaaFramework, and the window ends its tree when it cannot (lib.rs stop_run). False
 * when no run is under way. */
export const stopRun = (): Promise<boolean> => (tauri ? invoke("stop_run") : Promise.resolve(false));

/** The last run's messages so far and the ones to come, for a page loaded again during a run (lib.rs attach_run): true while
 * that run is under way. */
export const attachRun = (onMessage: (m: Message) => void): Promise<boolean> =>
  tauri ? invoke("attach_run", { onMessage: channel(onMessage) }) : Promise.resolve(false);

/** The emulators a scan finds, MuMu first (lib.rs scan_devices). */
export const scanDevices = (): Promise<Device[]> =>
  tauri ? invoke("scan_devices") : Promise.reject(new Error("the device scan runs only in the app"));

/** During a run, hide the window in the tray, its icon's tooltip and items in the page's language (lib.rs hide_to_tray): true
 * when it hid, false when no run is under way. */
export const hideToTray = (text: { tip: string; show: string; stop: string }): Promise<boolean> =>
  tauri ? invoke("hide_to_tray", { text }) : Promise.resolve(false);

/** A release newer than this build that the window can update to (lib.rs check_update, update.rs Release). */
export interface Release { version: string; zip: string; size: number; sha256: string }
/** How far a download is (update.rs Progress): the bytes so far, then the sha256 check, then the unpack. */
export type UpdateProgress = { step: "download"; received: number; total: number } | { step: "verify" } | { step: "extract" };
/** How the last apply went (update.rs Outcome): `applying` is one cut short; `restored`, for `failed`: all of it went back. */
export interface UpdateOutcome { state: "applying" | "done" | "failed"; from: string; to: string; error: string | null; restored: boolean }
/** Whether the last apply left cache/update/old/ holding the only copy of what it replaced (update.rs Outcome::keeps_old):
 * cut short, or failed with not all of it back. Until the user empties old/, the folder may hold half the new version: no
 * update applies, and a scheduled start is skipped. */
export const keepsOld = (o: UpdateOutcome | null) => !!o && (o.state === "applying" || (o.state === "failed" && !o.restored));

/** This build's version and the newer release GitHub has, asked at most once a day (lib.rs check_update); none when the check
 * fails. A plain browser has no update. */
export const checkUpdate = (): Promise<{ current: string; release: Release | null }> =>
  tauri ? invoke("check_update") : Promise.resolve({ current: "", release: null });

/** How the last apply went, for the page to show (lib.rs last_update); null when there is nothing to show. */
export const lastUpdate = (): Promise<UpdateOutcome | null> => (tauri ? invoke("last_update") : Promise.resolve(null));

/** Download the newer release, check its sha256 and unpack it (lib.rs download_update); `onProgress` hears how far it is. */
export function downloadUpdate(onProgress: (p: UpdateProgress) => void): Promise<void> {
  if (!tauri) return Promise.reject(new Error("the update runs only in the app"));
  const c = new Channel<UpdateProgress>();
  c.onmessage = onProgress;
  return invoke("download_update", { onProgress: c });
}

/** Apply the downloaded release: this window exits, and the new version replaces the files and opens (lib.rs apply_update).
 * Refused while a run is under way. */
export const applyUpdate = (): Promise<void> =>
  tauri ? invoke("apply_update") : Promise.reject(new Error("the update runs only in the app"));

/** The start of the error of a download whose sha256 is not GitHub's (update.rs MISMATCH). */
export const MISMATCH = "sha256 mismatch";
export const isMismatch = (e: unknown) => String(e).includes(MISMATCH);
/** The error of what a run refuses, an apply too (lib.rs RUN_UNDER_WAY). */
export const RUN_UNDER_WAY = "a run is under way";
export const isRunUnderWay = (e: unknown) => String(e).includes(RUN_UNDER_WAY);
/** A scheduled run's start the window was handed (`maalc-gui.exe --run <id>`, lib.rs take_scheduled): its schedule's id, and
 * whether this window was opened for it (it closes when the run ends) or was open already. */
export interface Scheduled { id: string; opened: boolean }

/** The scheduled runs' starts the window got since the last call, in order: its own start's, then each second start's. */
export const takeScheduled = (): Promise<Scheduled[]> => (tauri ? invoke("take_scheduled") : Promise.resolve([]));

/** Call `more` each time a second start brings a scheduled run (takeScheduled has it). Returns the function that stops. */
export function onScheduled(more: () => void): () => void {
  if (!tauri) return () => {};
  const listening = listen("scheduled", () => more());
  return () => { listening.then((stop) => stop()); };
}

/** Append a line to logs/schedule.log (lib.rs log_schedule): what came of a scheduled run's start. */
export const logSchedule = (line: string): Promise<void> => (tauri ? invoke("log_schedule", { line }) : Promise.resolve());

/** What bringing the Task Scheduler in line with the schedules did (lib.rs sync_schedules, schedule.rs Synced): the task
 * names written, kept and deleted, and what could not be done; `prefix` begins this folder's task names. */
export interface Synced { prefix: string; written: string[]; kept: string[]; deleted: string[]; errors: string[] }

/** Write this folder's Task Scheduler tasks as `schedules` say, the settings file's: one task each, those of deleted
 * schedules deleted. Rejects with why when the Task Scheduler cannot be reached (and in a plain browser). */
export const syncSchedules = (schedules: Settings["schedules"]): Promise<Synced> =>
  tauri ? invoke("sync_schedules", { schedules }) : Promise.reject(new Error("only the app reaches the Task Scheduler"));

/** Ask the window to close, as Alt+F4 does: the page's title bar ✕ (tauri.conf.json has no system bar). The request goes
 * to the onCloseRequested listener, which keeps the window open while it asks. */
export const requestClose = (): Promise<void> => (tauri ? getCurrentWindow().close() : Promise.resolve());

export const minimizeWindow = (): Promise<void> => (tauri ? getCurrentWindow().minimize() : Promise.resolve());

export const toggleMaximize = (): Promise<void> => (tauri ? getCurrentWindow().toggleMaximize() : Promise.resolve());

/** Tell `seen` whether the window is maximised, now and after each resize (a double click on the title bar, Win+Up, a drag
 * to the screen's top edge). Returns the function that stops telling. A plain browser has no window to maximise. */
export function onMaximized(seen: (on: boolean) => void): () => void {
  if (!tauri) return () => {};
  const w = getCurrentWindow();
  const read = () => { w.isMaximized().then(seen, () => {}); };
  read();
  const listening = w.onResized(read);
  return () => { listening.then((stop) => stop()); };
}

/** Close the window without asking again. */
export const closeWindow = (): Promise<void> => (tauri ? getCurrentWindow().destroy() : Promise.resolve());

/** Load the page again, as F5 does; whatever was not saved is gone. */
export const reloadPage = (): void => window.location.reload();

/** Spec 04 section 12 / spec 06: a reset marker holds only the team id and the time. */
export function resetTeamTimes(teamId: string): Promise<void> {
  const line = JSON.stringify({ reset: teamId, time: new Date().toISOString() });
  if (tauri) return invoke("append_runs_log", { line });
  localStorage.setItem("runs.jsonl", (localStorage.getItem("runs.jsonl") ?? "") + line + "\n");
  return Promise.resolve();
}
