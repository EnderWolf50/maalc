//! File access for the settings GUI (docs/spec/04-settings.md sections 1, 2 and 12), and the runner it starts (#815,
//! src/runner.rs): its messages go to the page through a channel, and closing the window during a run hides it in the tray.
//! The window updates itself from maalc's newest release (#817, src/update.rs), never during a run.
//! Validation lives in the frontend; this side only reads and writes files under <root>.

use runner::{Command, DeviceWant, Message, Run, TaskSpec};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::ipc::Channel;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

mod runner;
mod update;

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
pub(crate) fn replace(path: &Path, text: &str, ready: impl FnOnce() -> std::io::Result<()>) -> Result<(), String> {
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

/// Keep a settings file of an older version as it was, before the GUI writes its migration back (api.ts saveOldSettings):
/// a temp file, then a rename; one already there is written over. The error names the file.
#[tauri::command]
fn save_old_settings(version: u32, text: String) -> Result<(), String> {
    let path = old_settings_path(version)?;
    replace(&path, &text, || Ok(())).map_err(|e| format!("{}: {e}", path.display()))
}

/// The files of an older install's config/ the GUI reads back once, when it migrates a settings file older than version 23
/// (20, 21 or 22; #814, readBack.ts READ_BACK_FILES): MXU's config, the team options file v1.0.0's GUI wrote, and the
/// settings file it kept before its own migration (#782). The GUI only reads them.
const READ_BACK: [&str; 3] = ["mxu-maalc.json", "team_options.json", "settings.v20.json"];

/// Where a read-back file is under `root`; any other name is refused.
fn read_back_path(root: &Path, name: &str) -> Result<PathBuf, String> {
    if READ_BACK.contains(&name) {
        Ok(root.join("config").join(name))
    } else {
        Err(format!("{name}: not a file the read-back reads"))
    }
}

/// A read-back file's text, or None when it is not there.
#[tauri::command]
fn load_read_back(name: String) -> Result<Option<String>, String> {
    read_if_there(&read_back_path(&root()?, &name)?).map_err(|e| e.to_string())
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

/// The log lines of a run the window keeps for a page that attaches later, as many as the page shows (Run.tsx LOG_LINES).
const LOG_KEEP: usize = 2000;

/// A message that is a line of the run's log.
fn is_log(m: &Message) -> bool {
    matches!(m, Message::Event(runner::Event::Log { .. }) | Message::Invalid { .. } | Message::Output { .. })
}

/// What a run sent, for a page that attaches after it started (a reload): every message in order, of the log lines the last
/// LOG_KEEP.
#[derive(Default)]
struct History {
    messages: VecDeque<Message>,
    logs: usize,
}

impl History {
    fn push(&mut self, m: Message) {
        if is_log(&m) {
            self.logs += 1;
            if self.logs > LOG_KEEP {
                if let Some(i) = self.messages.iter().position(is_log) {
                    self.messages.remove(i);
                    self.logs -= 1;
                }
            }
        }
        self.messages.push_back(m);
    }
}

/// Where a run's messages go: the page's channel while it has one, and the history.
#[derive(Default)]
struct Relay {
    channel: Option<Channel<Message>>,
    history: History,
}

impl Relay {
    fn push(&mut self, m: Message) {
        if let Some(c) = &self.channel {
            if c.send(m.clone()).is_err() {
                self.channel = None; // the page went (a reload): it attaches again
            }
        }
        self.history.push(m);
    }

    /// Send the page what came so far, then each message as it comes.
    fn attach(&mut self, channel: Channel<Message>) {
        if self.history.messages.iter().all(|m| channel.send(m.clone()).is_ok()) {
            self.channel = Some(channel);
        }
    }
}

/// The last run the window started (one at a time) and where its messages go.
struct Active {
    run: Arc<Run>,
    relay: Arc<Mutex<Relay>>,
}

impl Active {
    fn under_way(&self) -> bool {
        !self.run.done()
    }
}

#[derive(Default)]
struct Runs(Mutex<Option<Active>>);

impl Runs {
    fn running(&self) -> Option<Arc<Run>> {
        self.0.lock().unwrap().as_ref().filter(|a| a.under_way()).map(|a| a.run.clone())
    }
}

/// The error of what a run refuses: a second start, an update's apply.
const RUN_UNDER_WAY: &str = "a run is under way";

/// Start the runner on `tasks` (their entry nodes, in run order) and `device`; its messages go to `on_message`. Each task reads
/// its options from config/settings.json at its start (#813), so the page saves first. Refused while a run is under way.
#[tauri::command]
fn start_run(runs: tauri::State<Runs>, tasks: Vec<String>, device: DeviceWant, on_message: Channel<Message>) -> Result<(), String> {
    let mut slot = runs.0.lock().unwrap();
    if slot.as_ref().is_some_and(Active::under_way) {
        return Err(RUN_UNDER_WAY.into());
    }
    let root = root()?;
    let spawn = runner::runner_spawn(&root)?;
    let tasks = tasks.into_iter().map(TaskSpec::new).collect();
    let start = Command::Start { root: Some(root.display().to_string()), device, tasks };
    let relay = Arc::new(Mutex::new(Relay { channel: Some(on_message), history: History::default() }));
    let to = relay.clone();
    let run = Run::spawn(&spawn, &start, runner::STOP_WAIT, Box::new(move |m| to.lock().unwrap().push(m)))?;
    *slot = Some(Active { run, relay });
    Ok(())
}

/// Ask the run to stop; false when none is under way.
#[tauri::command]
fn stop_run(runs: tauri::State<Runs>) -> bool {
    runs.running().is_some_and(|run| run.stop())
}

/// The page (after a reload) takes the last run's messages so far and the ones to come; true while that run is under way.
#[tauri::command]
fn attach_run(runs: tauri::State<Runs>, on_message: Channel<Message>) -> bool {
    let slot = runs.0.lock().unwrap();
    let Some(active) = slot.as_ref() else { return false };
    active.relay.lock().unwrap().attach(on_message);
    active.under_way()
}

/// The devices a scan finds, MuMu first (runner/devices.py), each with its MuMu instance.
#[tauri::command]
async fn scan_devices() -> Result<Vec<runner::Device>, String> {
    let spawn = runner::runner_spawn(&root()?)?;
    tauri::async_runtime::spawn_blocking(move || runner::scan(&spawn, runner::SCAN_WAIT)).await.map_err(|e| e.to_string())?
}

/// The update (src/update.rs): how the last apply went, read once at the start; the release this start's check found, asked
/// once per start (a page loaded again gets the same answer); whether a download is under way.
#[derive(Default)]
struct Updates {
    outcome: Option<update::Outcome>,
    checked: Mutex<Option<Option<update::Release>>>,
    downloading: AtomicBool,
}

impl Updates {
    /// The release this start's check found, when it is newer than this build.
    fn newer(&self) -> Option<update::Release> {
        self.checked.lock().unwrap().clone().flatten().filter(|r| update::newer(&r.tag, update::current()))
    }
}

/// What the page shows of the update: this build's version, and the newer release the check found.
#[derive(Serialize)]
struct UpdateCheck {
    current: String,
    release: Option<update::Release>,
}

fn now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs())
}

/// The latest release, when it is newer than this build: asked of GitHub at most once a day (update::check), and once per
/// start. A check that fails is no release: the page says nothing.
#[tauri::command]
async fn check_update(app: AppHandle) -> Result<UpdateCheck, String> {
    let root = root()?;
    tauri::async_runtime::spawn_blocking(move || {
        let updates = app.state::<Updates>();
        let mut slot = updates.checked.lock().unwrap(); // held through the check: a second call waits for its answer
        if slot.is_none() {
            *slot = Some(update::check(&root, &update::api_base(), now()));
        }
        drop(slot);
        UpdateCheck { current: update::current().into(), release: updates.newer() }
    })
    .await
    .map_err(|e| e.to_string())
}

/// How the last update's apply went (update::settle), for the page to show; None when there was none to show.
#[tauri::command]
fn last_update(updates: tauri::State<Updates>) -> Option<update::Outcome> {
    updates.outcome.clone()
}

/// Download the release the check found, check its sha256 and unpack it (update::download); `on_progress` hears how far it
/// is. A run may go on meanwhile: only the apply waits for it.
#[tauri::command]
async fn download_update(app: AppHandle, on_progress: Channel<update::Progress>) -> Result<(), String> {
    let root = root()?;
    let release = app.state::<Updates>().newer().ok_or("no newer release to download")?;
    if app.state::<Updates>().downloading.swap(true, Ordering::SeqCst) {
        return Err("a download is under way".into());
    }
    let done = tauri::async_runtime::spawn_blocking(move || {
        let got = update::download(&root, &release, &mut |p| {
            let _ = on_progress.send(p);
        });
        app.state::<Updates>().downloading.store(false, Ordering::SeqCst);
        got
    })
    .await
    .map_err(|e| e.to_string())?;
    done.map(|_| ())
}

/// Refused while a run is under way: an update never replaces the files a run uses (spec #811 「自動更新」). A scheduled run
/// due soon is not waited for.
fn ready_to_apply(runs: &Runs) -> Result<(), String> {
    if runs.running().is_some() { Err(RUN_UNDER_WAY.into()) } else { Ok(()) }
}

/// Apply the downloaded release: its maalc-gui.exe starts in the apply-update mode (update::launch), and this window exits for
/// it, which replaces the files and starts the new window. Refused while a run is under way, and before the download.
#[tauri::command]
fn apply_update(app: AppHandle, runs: tauri::State<Runs>, updates: tauri::State<Updates>) -> Result<(), String> {
    ready_to_apply(&runs)?;
    let root = root()?;
    let release = updates.newer().ok_or("no newer release to apply")?;
    let staged = update::staged_dir(&root, &release.parsed_version()?);
    if !staged.join(update::EXE).is_file() {
        return Err(format!("{} is not downloaded", release.tag));
    }
    update::launch(&root, &staged, std::process::id())?;
    app.exit(0);
    Ok(())
}

/// The tray icon's texts, in the page's language.
#[derive(Deserialize)]
struct TrayText {
    tip: String,
    show: String,
    stop: String,
}

const TRAY: &str = "main";

/// The window shows again, in front, and the tray icon goes.
fn show_window(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
    let _ = app.remove_tray_by_id(TRAY);
}

/// During a run the window hides in the tray instead of closing, the run going on (#815): its icon brings the window back (a
/// click, or its first item) or stops the run. True when it hid; false when no run is under way, and the window closes as
/// before.
#[tauri::command]
fn hide_to_tray(app: AppHandle, runs: tauri::State<Runs>, text: TrayText) -> Result<bool, String> {
    if runs.running().is_none() {
        return Ok(false);
    }
    if app.tray_by_id(TRAY).is_none() {
        let show = MenuItem::with_id(&app, "show", &text.show, true, None::<&str>).map_err(|e| e.to_string())?;
        let stop = MenuItem::with_id(&app, "stop", &text.stop, true, None::<&str>).map_err(|e| e.to_string())?;
        let menu = Menu::with_items(&app, &[&show, &stop]).map_err(|e| e.to_string())?;
        let icon = app.default_window_icon().cloned().ok_or("the app has no icon")?;
        TrayIconBuilder::with_id(TRAY)
            .icon(icon)
            .tooltip(&text.tip)
            .menu(&menu)
            .show_menu_on_left_click(false)
            .on_menu_event(|app, e| match e.id().as_ref() {
                "show" => show_window(app),
                "stop" => {
                    if let Some(run) = app.state::<Runs>().running() {
                        run.stop();
                    }
                }
                _ => {}
            })
            .on_tray_icon_event(|tray, e| {
                if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = e {
                    show_window(tray.app_handle());
                }
            })
            .build(&app)
            .map_err(|e| e.to_string())?;
    }
    let window = app.get_webview_window("main").ok_or("no main window")?;
    window.hide().map_err(|e| e.to_string())?;
    Ok(true)
}

/// A second start of maalc-gui.exe: its arguments and working folder, which go to the open window as the `second-start`
/// event (a scheduled run's `--run`, spec #811 「定時執行」, reads them).
#[derive(Serialize, Clone)]
struct SecondStart {
    args: Vec<String>,
    cwd: String,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // the apply-update mode replaces the files and ends, before Tauri: no window, and no hand-off to the window still open
    if let Some(code) = update::apply_mode(&std::env::args().collect::<Vec<_>>()) {
        std::process::exit(code);
    }
    tauri::Builder::default()
        // first, as the plugin asks: a second start ends at once, and the window that is open shows in front
        .plugin(tauri_plugin_single_instance::init(|app, args, cwd| {
            show_window(app);
            let _ = app.emit("second-start", SecondStart { args, cwd });
        }))
        .manage(Runs::default())
        .setup(|app| {
            // The page loads the game's images from the data folder through the asset protocol, whose static scope
            // (tauri.conf.json) is empty: that folder alone is opened to it, found the way load_game_data finds it. Without
            // one, load_game_data fails and the window says why.
            if let Ok(dir) = data_dir() {
                if let Err(e) = app.asset_protocol_scope().allow_directory(&dir, true) {
                    eprintln!("asset protocol: cannot open {}: {e}", dir.display());
                }
            }
            // How the last update went, and what it left in cache/update/. The apply-update process that started this
            // window may hold its own files a moment longer, so the cleanup tries again a few times.
            let root = root().ok();
            app.manage(Updates { outcome: root.as_deref().and_then(update::settle), ..Updates::default() });
            if let Some(root) = root {
                std::thread::spawn(move || {
                    for _ in 0..10 {
                        if update::clean(&root) {
                            break;
                        }
                        std::thread::sleep(Duration::from_secs(3));
                    }
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            root_dir,
            load_settings,
            load_game_data,
            save_settings,
            save_old_settings,
            load_read_back,
            append_runs_log,
            start_run,
            stop_run,
            attach_run,
            scan_devices,
            hide_to_tray,
            check_update,
            last_update,
            download_update,
            apply_update
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
    fn the_read_back_reads_its_three_files_under_config_and_nothing_else() {
        let root = Path::new("R");
        for name in ["mxu-maalc.json", "team_options.json", "settings.v20.json"] {
            assert_eq!(read_back_path(root, name).unwrap(), root.join("config").join(name));
        }
        for bad in ["settings.json", "settings.v22.json", "../mxu-maalc.json", "config/mxu-maalc.json", ""] {
            assert!(read_back_path(root, bad).is_err(), "{bad}");
        }
    }

    fn log(i: usize) -> Message {
        Message::Output { line: format!("line {i}") }
    }

    #[test]
    fn the_history_keeps_every_event_and_the_last_log_lines() {
        let mut h = History::default();
        h.push(Message::Stopping);
        for i in 0..LOG_KEEP + 5 {
            h.push(log(i));
        }
        h.push(Message::Exit { code: Some(0), ended: true, tail: vec![] });
        assert_eq!(h.messages.len(), LOG_KEEP + 2);
        assert_eq!(h.messages[0], Message::Stopping);
        assert_eq!(h.messages[1], log(5));
        assert_eq!(h.messages[LOG_KEEP], log(LOG_KEEP + 4));
        assert!(matches!(h.messages.back(), Some(Message::Exit { .. })));
    }

    /// A run whose runner is cmd.exe waiting a minute (it never says ready), as the window holds it once started.
    fn hanging_run() -> Arc<Run> {
        let spawn = runner::Spawn {
            program: "cmd.exe".into(),
            args: vec!["/d".into(), "/c".into(), "ping -n 60 127.0.0.1 >nul".into()],
            dir: std::env::temp_dir(),
        };
        let start = Command::Start { root: None, device: DeviceWant::default(), tasks: vec![TaskSpec::new("ClaimMail".into())] };
        Run::spawn(&spawn, &start, runner::STOP_WAIT, Box::new(|_| {})).unwrap()
    }

    #[test]
    fn an_update_is_not_applied_while_a_run_is_under_way() {
        let runs = Runs::default();
        assert_eq!(ready_to_apply(&runs), Ok(()), "no run yet");
        let run = hanging_run();
        *runs.0.lock().unwrap() = Some(Active { run: run.clone(), relay: Arc::default() });
        assert_eq!(ready_to_apply(&runs), Err(RUN_UNDER_WAY.into()));
        run.kill("the test ends it".into());
        assert!(run.wait(Duration::from_secs(10)));
        assert_eq!(ready_to_apply(&runs), Ok(()), "the run ended");
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
