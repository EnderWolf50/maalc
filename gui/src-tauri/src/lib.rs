//! File access for the settings GUI (docs/spec/04-settings.md sections 1, 2 and 12), and the runner it starts (#815,
//! src/runner.rs): its messages go to the page through a channel, and closing the window during a run hides it in the tray.
//! The scheduled runs (#816): one window per maalc folder (src/instance.rs), the `--run <id>` of a start handed to the page,
//! and the Task Scheduler's tasks brought in line with the settings' schedules (src/schedule.rs).
//! Validation lives in the frontend; this side only reads and writes files under <root>.

use runner::{Command, DeviceWant, Message, Run, TaskSpec};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::{Arc, Mutex};
use tauri::ipc::Channel;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

mod instance;
mod runner;
mod schedule;

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

/// Append one line to <root>/logs/<name>.
fn append_log(name: &str, line: &str) -> Result<(), String> {
    if line.contains('\n') {
        return Err(format!("{name} lines must not contain a newline"));
    }
    let dir = root()?.join("logs");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join(name))
        .map_err(|e| e.to_string())?;
    f.write_all(format!("{line}\n").as_bytes()).map_err(|e| e.to_string())
}

/// Append one JSON line to <root>/logs/runs.jsonl (the GUI only appends reset markers, spec 04 section 12).
#[tauri::command]
fn append_runs_log(line: String) -> Result<(), String> {
    append_log("runs.jsonl", &line)
}

/// Append one line to <root>/logs/schedule.log: what came of a scheduled run's start (#816), which a window the schedule
/// opened and closed again leaves nowhere else.
#[tauri::command]
fn log_schedule(line: String) -> Result<(), String> {
    append_log("schedule.log", &line)
}

/// A scheduled run the page has not taken yet: its schedule's id, and whether this window was opened for it (it closes when
/// the run ends) or was open already.
#[derive(Serialize, Clone, Debug, PartialEq)]
struct Scheduled {
    id: String,
    opened: bool,
}

impl Scheduled {
    /// The scheduled run a start's arguments bring (`--run <id>`), if any: `opened` for this window's own start.
    fn of(args: &[String], opened: bool) -> Option<Scheduled> {
        schedule::run_arg(args).map(|id| Scheduled { id, opened })
    }
}

/// The local time as logs/schedule.log dates a line (the page's schedule.ts stamp): YYYY-MM-DD HH:MM:SS.
#[cfg(windows)]
fn stamp() -> String {
    let mut t = windows_sys::Win32::Foundation::SYSTEMTIME::default();
    unsafe { windows_sys::Win32::System::SystemInformation::GetLocalTime(&mut t) };
    format!("{:04}-{:02}-{:02} {:02}:{:02}:{:02}", t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond)
}

#[cfg(not(windows))]
fn stamp() -> String {
    String::new()
}

/// The `--run <id>` of this window's own start, and of each second start since, in order; the page takes them once its
/// settings are read (and on each `scheduled` event), so one that comes while the page loads waits for it.
#[derive(Default)]
struct Pending(Mutex<Vec<Scheduled>>);

#[tauri::command]
fn take_scheduled(pending: tauri::State<Pending>) -> Vec<Scheduled> {
    std::mem::take(&mut *pending.0.lock().unwrap())
}

/// One sync with the Task Scheduler at a time: the one after the load and a save soon after must not cross.
static SYNCING: Mutex<()> = Mutex::new(());

/// Bring this folder's Task Scheduler tasks in line with `schedules`, the settings file's as the page last read or saved them
/// (schedule::sync): each to start this maalc-gui.exe with `--run <id>` from <root>. A development build on MAALC_ROOT writes
/// none: its task would start this exe without MAALC_ROOT, on the wrong folder.
#[tauri::command]
async fn sync_schedules(schedules: Vec<schedule::Schedule>) -> Result<schedule::Synced, String> {
    if cfg!(debug_assertions) && std::env::var_os("MAALC_ROOT").is_some() {
        return Err("a development build on MAALC_ROOT writes no scheduled task".into());
    }
    let root = schedule::real_path(&root()?);
    let exe = schedule::real_path(&std::env::current_exe().map_err(|e| e.to_string())?);
    tauri::async_runtime::spawn_blocking(move || {
        let _one = SYNCING.lock().unwrap_or_else(|e| e.into_inner());
        let tasks = schedule::TaskService::connect()?;
        schedule::sync(&tasks, &schedules, &exe, &root, &schedule::program_there)
    })
    .await
    .map_err(|e| e.to_string())?
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

/// Start the runner on `tasks` (their entry nodes, in run order) and `device`; its messages go to `on_message`. Each task reads
/// its options from config/settings.json at its start (#813), so the page saves first. Refused while a run is under way.
#[tauri::command]
fn start_run(runs: tauri::State<Runs>, tasks: Vec<String>, device: DeviceWant, on_message: Channel<Message>) -> Result<(), String> {
    let mut slot = runs.0.lock().unwrap();
    if slot.as_ref().is_some_and(Active::under_way) {
        return Err("a run is under way".into());
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

/// A second start of maalc-gui.exe in this folder (src/instance.rs): the window shows in front, and a scheduled run's
/// `--run <id>` goes to the page, which runs it or says why not (spec #811 「定時執行」).
fn second_start(app: &AppHandle, start: instance::SecondStart) {
    show_window(app);
    if let Some(scheduled) = Scheduled::of(&start.args, false) {
        app.state::<Pending>().0.lock().unwrap().push(scheduled);
        let _ = app.emit("scheduled", ());
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // One window per maalc folder: a start of a folder whose window is open hands it its arguments and ends here. The lock
    // lives as long as this process. With no folder to key it by (no path of this exe), every start opens a window.
    let this = instance::SecondStart::of_this_process();
    let key = root().ok().map(|r| schedule::folder_key(&schedule::real_path(&r)));
    let _lock = match key.as_deref() {
        None => None,
        Some(k) => match instance::claim(k) {
            Ok(Some(lock)) => Some(lock),
            Ok(None) => {
                if let Err(e) = instance::forward(k, &this, instance::FORWARD_WAIT) {
                    // the window that is open never got it: a scheduled run says so where the user looks for it
                    match Scheduled::of(&this.args, false) {
                        Some(s) => {
                            let line = format!("{} [schedule] {}: not run: the open window did not take it: {e}", stamp(), s.id);
                            let _ = append_log("schedule.log", &line);
                        }
                        None => eprintln!("the window of this folder did not take this start: {e}"),
                    }
                }
                return;
            }
            Err(e) => {
                eprintln!("one window per folder: {e}");
                None
            }
        },
    };
    let launch = Scheduled::of(&this.args, true);
    tauri::Builder::default()
        .manage(Runs::default())
        .manage(Pending(Mutex::new(launch.into_iter().collect())))
        .setup(move |app| {
            let handle = app.handle().clone();
            if let Some(key) = &key {
                if let Err(e) = instance::serve(key, move |start| second_start(&handle, start)) {
                    eprintln!("second starts: {e}");
                }
            }
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
            save_old_settings,
            load_read_back,
            append_runs_log,
            start_run,
            stop_run,
            attach_run,
            scan_devices,
            hide_to_tray,
            take_scheduled,
            log_schedule,
            sync_schedules
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

    #[test]
    fn a_start_with_run_brings_its_scheduled_run_and_one_without_brings_none() {
        let run = names(&["maalc-gui.exe", "--run", "s1"]);
        // the window's own start opened it for the run (it closes after); a second start found it open
        assert_eq!(Scheduled::of(&run, true), Some(Scheduled { id: "s1".into(), opened: true }));
        assert_eq!(Scheduled::of(&run, false), Some(Scheduled { id: "s1".into(), opened: false }));
        assert_eq!(Scheduled::of(&names(&["maalc-gui.exe"]), true), None);
    }

    #[cfg(windows)]
    #[test]
    fn a_schedule_log_line_is_dated_as_the_page_dates_it() {
        let t = stamp();
        let shape: String = t.chars().map(|c| if c.is_ascii_digit() { '9' } else { c }).collect();
        assert_eq!(shape, "9999-99-99 99:99:99", "{t}");
    }
}
