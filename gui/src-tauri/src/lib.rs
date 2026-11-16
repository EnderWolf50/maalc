//! File access for the settings GUI (docs/spec/04-settings.md sections 1, 2 and 12).
//! Validation lives in the frontend; this side only reads and writes files under <root>.

use serde::Serialize;
use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use tauri::Manager;

/// <root> is the folder holding this executable (spec 04 section 1), so the user never picks it.
/// Debug builds honour MAALC_ROOT, because `tauri dev` runs the exe from target/debug.
fn root() -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        if let Some(dir) = std::env::var_os("MAALC_ROOT") {
            return Ok(PathBuf::from(dir));
        }
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    Ok(exe.parent().ok_or("executable has no parent folder")?.to_path_buf())
}

fn settings_path() -> Result<PathBuf, String> {
    Ok(root()?.join("config").join("settings.json"))
}

/// The team options file (#780): assets/interface.json imports it from here (gui/src/teamOptions.test.ts checks the two
/// agree), and config/ is what tools/install.py and both clients' updates leave alone.
fn team_options_path() -> Result<PathBuf, String> {
    Ok(root()?.join("config").join("team_options.json"))
}

/// A settings file of an older version beside the settings file, as it read (#782): config/settings.v<version>.json.
fn old_settings_path(version: u32) -> Result<PathBuf, String> {
    Ok(root()?.join("config").join(old_settings_name(version)))
}

fn old_settings_name(version: u32) -> String {
    format!("settings.v{version}.json")
}

/// A file's text, or None when it does not exist yet.
fn read_if_there(path: &Path) -> std::io::Result<Option<String>> {
    match fs::read_to_string(path) {
        Ok(text) => Ok(Some(text)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e),
    }
}

/// Write text to a temp file next to path, then rename it over path once `ready` agrees, so a crash never leaves half a
/// file. Nothing is written when `ready` refuses or a step fails.
fn replace(path: &Path, text: &str, ready: impl FnOnce() -> std::io::Result<()>) -> Result<(), String> {
    let dir = path.parent().unwrap();
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let tmp = dir.join(format!("{}.tmp", path.file_name().unwrap().to_string_lossy()));
    let written = (|| {
        let mut f = fs::File::create(&tmp)?;
        f.write_all(text.as_bytes())?;
        f.sync_all()?;
        drop(f);
        ready()?;
        fs::rename(&tmp, path) // replaces the old file on Windows too
    })();
    if written.is_err() {
        let _ = fs::remove_file(&tmp);
    }
    written.map_err(|e| e.to_string())
}

#[tauri::command]
fn root_dir() -> Result<String, String> {
    Ok(root()?.display().to_string())
}

/// The settings file text, or None when it does not exist yet.
#[tauri::command]
fn load_settings() -> Result<Option<String>, String> {
    read_if_there(&settings_path()?).map_err(|e| e.to_string())
}

/// The team options file text, or None when it does not exist yet.
#[tauri::command]
fn load_team_options() -> Result<Option<String>, String> {
    read_if_there(&team_options_path()?).map_err(|e| e.to_string())
}

/// Write the team options file as save_settings writes its file: a temp file, then a rename. The GUI is its one writer.
#[tauri::command]
fn save_team_options(text: String) -> Result<(), String> {
    replace(&team_options_path()?, &text, || Ok(()))
}

/// Keep a settings file of an older version as it was, before the GUI writes its migration back (api.ts saveOldSettings):
/// a temp file, then a rename; one already there is written over. The error names the file.
#[tauri::command]
fn save_old_settings(version: u32, text: String) -> Result<(), String> {
    let path = old_settings_path(version)?;
    replace(&path, &text, || Ok(())).map_err(|e| format!("{}: {e}", path.display()))
}

/// <root>/resource/base/data: resource/ sits under <root> in a release and under assets/ in the repo, the same lookup as
/// agent/actions.py.
fn data_dir() -> Result<PathBuf, String> {
    let root = root()?;
    let resource = [root.join("resource"), root.join("assets").join("resource")]
        .into_iter()
        .find(|p| p.is_dir())
        .ok_or_else(|| format!("no resource folder under {}", root.display()))?;
    let dir = resource.join("base").join("data");
    if dir.is_dir() { Ok(dir) } else { Err(format!("{}: no such folder", dir.display())) }
}

/// `rel` (a path under data/, "/" between its parts) inside `dir`; a path that climbs out of it or is absolute is refused.
fn inside(dir: &Path, rel: &str) -> Result<PathBuf, String> {
    let rel_path = Path::new(rel);
    let plain = rel_path.components().count() > 0 && rel_path.components().all(|c| matches!(c, Component::Normal(_)));
    if plain { Ok(dir.join(rel_path)) } else { Err(format!("{rel}: not a path under data/")) }
}

/// The game data the window shows (api.ts GameFiles): read from the install's resource/base/data at run time, so what the
/// Agent downloaded shows without a new build. `dir` is where the page loads images from, through the asset protocol.
#[derive(Serialize)]
struct GameData {
    dir: String,
    texts: BTreeMap<String, String>,
    folders: BTreeMap<String, Vec<String>>,
}

/// `texts` by path and the file names of each of `folders` under `dir` (a folder the data does not have lists nothing). A text
/// that cannot be read fails with its path and the reason.
fn read_data(dir: &Path, texts: &[String], folders: &[String]) -> Result<GameData, String> {
    let mut data = GameData { dir: dir.display().to_string(), texts: BTreeMap::new(), folders: BTreeMap::new() };
    for name in texts {
        let path = inside(dir, name)?;
        let text = fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        data.texts.insert(name.clone(), text);
    }
    for name in folders {
        let path = inside(dir, name)?;
        let mut files = match fs::read_dir(&path) {
            Ok(entries) => entries
                .filter_map(Result::ok)
                .filter(|e| e.path().is_file())
                .filter_map(|e| e.file_name().into_string().ok())
                .collect::<Vec<_>>(),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Vec::new(),
            Err(e) => return Err(format!("{}: {e}", path.display())),
        };
        files.sort();
        data.folders.insert(name.clone(), files);
    }
    Ok(data)
}

#[tauri::command]
fn load_game_data(texts: Vec<String>, folders: Vec<String>) -> Result<GameData, String> {
    read_data(&data_dir()?, &texts, &folders)
}

/// Error text of a save refused because the file is no longer `expected` (api.ts CHANGED).
const CHANGED: &str = "settings.json changed on disk";

/// Write a temp file next to settings.json, then rename over it, so a crash never leaves half a file.
/// expected: the text the GUI last read or wrote, None for no file then. When the file holds anything else now, another
/// writer changed it since (the Agent moves a team to the end of the queue after a claim, #501): nothing is written, for
/// the GUI to read it again.
#[tauri::command]
fn save_settings(text: String, expected: Option<String>) -> Result<(), String> {
    let path = settings_path()?;
    replace(&path, &text, || {
        if read_if_there(&path)? != expected {
            return Err(std::io::Error::other(CHANGED));
        }
        Ok(())
    })
}

/// Append one JSON line to <root>/logs/runs.jsonl (the GUI only appends reset markers, spec 04 section 12).
#[tauri::command]
fn append_runs_log(line: String) -> Result<(), String> {
    if line.contains('\n') {
        return Err("runs.jsonl lines must not contain a newline".into());
    }
    let dir = root()?.join("logs");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("runs.jsonl"))
        .map_err(|e| e.to_string())?;
    f.write_all(format!("{line}\n").as_bytes()).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // The page loads the game's images from the data folder through the asset protocol, whose static scope
            // (tauri.conf.json) is empty: that folder alone is opened to it, found the way load_game_data finds it. Without
            // one, load_game_data fails and the window says why.
            if let Ok(dir) = data_dir() {
                if let Err(e) = app.asset_protocol_scope().allow_directory(&dir, true) {
                    eprintln!("asset protocol: cannot open {}: {e}", dir.display());
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            root_dir,
            load_settings,
            load_game_data,
            save_settings,
            load_team_options,
            save_team_options,
            save_old_settings,
            append_runs_log
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A fresh folder under the temp dir for one test.
    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("maalc-gui-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn names(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn reads_the_texts_and_lists_the_folders_sorted() {
        let dir = scratch("read");
        fs::create_dir_all(dir.join("gift_icons").join("nested")).unwrap();
        fs::create_dir_all(dir.join("sinner_cards")).unwrap();
        fs::write(dir.join("gift_search.json"), "{}").unwrap();
        fs::write(dir.join("sinner_cards").join("index.json"), "[1]").unwrap();
        fs::write(dir.join("gift_icons").join("2.webp"), "x").unwrap();
        fs::write(dir.join("gift_icons").join("1.webp"), "x").unwrap();
        let data = read_data(&dir, &names(&["gift_search.json", "sinner_cards/index.json"]), &names(&["gift_icons", "grace_icons"])).unwrap();
        assert_eq!(data.texts["gift_search.json"], "{}");
        assert_eq!(data.texts["sinner_cards/index.json"], "[1]");
        assert_eq!(data.folders["gift_icons"], names(&["1.webp", "2.webp"]));
        assert!(data.folders["grace_icons"].is_empty());
        assert_eq!(data.dir, dir.display().to_string());
    }

    #[test]
    fn an_old_settings_file_is_named_by_its_version() {
        assert_eq!(old_settings_name(20), "settings.v20.json");
    }

    #[test]
    fn a_missing_text_fails_with_its_path() {
        let dir = scratch("missing");
        let err = read_data(&dir, &names(&["graces.json"]), &[]).err().unwrap();
        assert!(err.contains("graces.json"), "{err}");
    }

    #[test]
    fn a_path_outside_the_data_folder_is_refused() {
        let dir = scratch("outside");
        for bad in ["../config/settings.json", "/etc/passwd", "a/../../b", "", "C:/Windows/win.ini"] {
            assert!(read_data(&dir, &names(&[bad]), &[]).is_err(), "{bad}");
            assert!(read_data(&dir, &[], &names(&[bad])).is_err(), "{bad}");
        }
    }
}
