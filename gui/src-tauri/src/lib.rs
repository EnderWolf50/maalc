//! File access for the settings GUI (docs/spec/04-settings.md sections 1, 2 and 12).
//! Validation lives in the frontend; this side only reads and writes files under <root>.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

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

/// The season's theme pack data file text (spec 05 section 2). resource/ sits under <root> in a
/// release and under assets/ in the repo: the same lookup as agent/actions.py.
#[tauri::command]
fn load_theme_packs() -> Result<String, String> {
    let root = root()?;
    let resource = [root.join("resource"), root.join("assets").join("resource")]
        .into_iter()
        .find(|p| p.is_dir())
        .ok_or("no resource folder under <root>")?;
    let path = resource.join("base").join("data").join("theme_packs.yaml");
    fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))
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
        .invoke_handler(tauri::generate_handler![
            root_dir,
            load_settings,
            load_theme_packs,
            save_settings,
            load_team_options,
            save_team_options,
            append_runs_log
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
