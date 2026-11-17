// File access through the Rust side (src-tauri/src/lib.rs). In a plain browser (`pnpm dev`,
// screenshots) it falls back to localStorage so the editor can be tried without Tauri.
import { convertFileSrc, invoke, isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

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

/** Ask `keepOpen` each time the user closes the window (its ✕, Alt+F4): true keeps it open. Returns the function that stops
 * asking. With a listener, Tauri leaves the closing to the page, which destroys the window (needs core:window:allow-destroy,
 * capabilities/default.json). A plain browser has no window to keep. */
export function onCloseRequested(keepOpen: () => boolean): () => void {
  if (!tauri) return () => {};
  const listening = getCurrentWindow().onCloseRequested((e) => { if (keepOpen()) e.preventDefault(); });
  return () => { listening.then((stop) => stop()); };
}

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
