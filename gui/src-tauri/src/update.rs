//! The window updates itself from maalc's newest release on GitHub (spec #811 「自動更新」, #817), with no updater plugin:
//! Tauri's installs only signed installers, and maalc ships a folder in a zip.
//!
//! - **Check** (`check`): at start, GitHub's latest release (not a draft, not a prerelease), at most once a day; the record is
//!   cache/update/check.json. The page shows a notice when it is newer than this build. A check that fails says nothing.
//! - **Download** (`download`): on the user's click, the release's zip into cache/update/, checked against the sha256 digest
//!   GitHub gives for it (a mismatch deletes it and stops), then unpacked to cache/update/v<version>/.
//! - **Apply** (`launch`, `apply_mode`): only while no run is under way (lib.rs apply_update). The window starts the unpacked
//!   maalc-gui.exe in its apply-update mode and exits; that process waits for it, moves each root entry the zip has into
//!   cache/update/old/, copies the new one in and starts the new window. config/, logs/, state/, cache/ and debug/ are never
//!   touched (KEEP). A step that fails puts back what it moved and starts the old window. cache/update/apply.json says how it
//!   went, which the next window shows (`settle`); that window deletes old/. The exception: an apply cut short, or one that
//!   failed and could not put everything back, leaves in old/ the only copy of what it replaced, so old/ stays until the
//!   user empties it. Until then each start shows why, no apply runs (`holds_files`) and a scheduled start is skipped
//!   (App.tsx, api.ts keepsOld).
//!
//! The game data's resource package keeps its own hot update (ADR 0012), at a task's start: an update never runs beside one.

use semver::Version;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::ffi::OsString;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::Duration;

/// Where the releases are.
pub const REPO: &str = "EnderWolf50/maalc";
const API: &str = "https://api.github.com";
/// The window's program, at the root of an install and of the zip's folder.
pub const EXE: &str = "maalc-gui.exe";
/// The user's folders under <root>: an update leaves them as they are, also when a zip has one.
pub const KEEP: [&str; 5] = ["config", "logs", "state", "cache", "debug"];
/// How often the window asks GitHub: GitHub allows 60 unauthenticated requests an hour per address.
pub const CHECK_EVERY: Duration = Duration::from_secs(24 * 60 * 60);
/// How long the apply-update mode waits for the old window to exit.
const WAIT_OLD: Duration = Duration::from_secs(60);
/// How often a move is tried, and the wait between tries: a file the old window's processes or a virus scan held a moment ago
/// can be free on the next try.
const TRIES: u32 = 10;
const TRY_WAIT: Duration = Duration::from_millis(200);
/// The start of the error of a download whose sha256 is not the one GitHub gives (api.ts isMismatch).
pub const MISMATCH: &str = "sha256 mismatch";

/// This build's version (Cargo.toml's, which tests/test_version.py keeps equal to tauri.conf.json's and interface.json's).
pub fn current() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// GitHub's API. A debug build (a test, `tauri dev`, a `--debug` build for a check against a local stub) honours
/// MAALC_UPDATE_API instead, as lib.rs root honours MAALC_ROOT; a release build always asks GitHub.
pub fn api_base() -> String {
    if cfg!(debug_assertions) {
        if let Ok(api) = std::env::var("MAALC_UPDATE_API") {
            return api;
        }
    }
    API.into()
}

// ---- the folders ----

/// cache/update/: what the update keeps between its steps.
pub fn update_dir(root: &Path) -> PathBuf {
    root.join("cache").join("update")
}

/// Where the apply moves the root entries it replaces, until the next start deletes them.
pub fn old_dir(root: &Path) -> PathBuf {
    update_dir(root).join("old")
}

/// Where a release's zip is unpacked: cache/update/v<version>/, which holds maalc-gui.exe at its top.
pub fn staged_dir(root: &Path, version: &Version) -> PathBuf {
    update_dir(root).join(format!("v{version}"))
}

fn record_path(root: &Path) -> PathBuf {
    update_dir(root).join("check.json")
}

fn journal_path(root: &Path) -> PathBuf {
    update_dir(root).join("apply.json")
}

/// A value as JSON in `path`, written whole (a temp file, then a rename).
fn write_json(path: &Path, value: &impl Serialize) -> Result<(), String> {
    let text = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    crate::replace(path, &text, || Ok(()))
}

// ---- versions ----

/// A release tag's version: `v1.2.0` or `1.2.0`; None for anything else.
pub fn version_of(tag: &str) -> Option<Version> {
    Version::parse(tag.strip_prefix('v').unwrap_or(tag)).ok()
}

/// Whether release version or tag `version` comes after version `current`. One that is no version never does.
pub fn newer(version: &str, current: &str) -> bool {
    match (version_of(version), Version::parse(current)) {
        (Some(version), Ok(current)) => version > current,
        _ => false,
    }
}

// ---- the release ----

/// A release this window can update to: its version (`1.2.0`), its zip and the sha256 GitHub gives for it.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Release {
    pub version: String,
    pub zip: String,
    pub size: u64,
    /// Lower-case hex.
    pub sha256: String,
}

impl Release {
    pub fn parsed_version(&self) -> Result<Version, String> {
        Version::parse(&self.version).map_err(|e| format!("{}: {e}", self.version))
    }
}

/// The release in GitHub's answer to releases/latest, with its zip `maalc-<tag>.zip` (release.yml names it so) and that asset's
/// `digest`, `sha256:<hex>`. A release whose tag is no version, or that has no such zip or digest, is refused.
pub fn release_of(text: &str) -> Result<Release, String> {
    let json: serde_json::Value = serde_json::from_str(text).map_err(|e| format!("the release: {e}"))?;
    let tag = json["tag_name"].as_str().ok_or("the release has no tag_name")?;
    let version = version_of(tag).ok_or_else(|| format!("{tag}: not a version"))?;
    let name = format!("maalc-{tag}.zip");
    let assets = json["assets"].as_array().map(Vec::as_slice).unwrap_or_default();
    let asset = assets.iter().find(|a| a["name"] == name.as_str()).ok_or_else(|| format!("{tag} has no {name}"))?;
    let digest = asset["digest"].as_str().ok_or_else(|| format!("{name} has no digest"))?;
    let sha256 = digest
        .strip_prefix("sha256:")
        .filter(|hex| hex.len() == 64 && hex.bytes().all(|b| b.is_ascii_hexdigit()))
        .ok_or_else(|| format!("{name}: {digest} is not a sha256"))?;
    Ok(Release {
        version: version.to_string(),
        zip: asset["browser_download_url"].as_str().ok_or_else(|| format!("{name} has no browser_download_url"))?.into(),
        size: asset["size"].as_u64().unwrap_or(0),
        sha256: sha256.to_ascii_lowercase(),
    })
}

/// An HTTP client on Windows' own TLS and certificate store; `read`: how long a read may wait.
fn agent(read: Duration) -> ureq::Agent {
    use ureq::tls::{RootCerts, TlsConfig, TlsProvider};
    let tls = TlsConfig::builder().provider(TlsProvider::NativeTls).root_certs(RootCerts::PlatformVerifier).build();
    ureq::Agent::config_builder()
        .tls_config(tls)
        .user_agent(format!("maalc-gui/{}", current()))
        .timeout_connect(Some(Duration::from_secs(15)))
        .timeout_per_read(Some(read))
        .build()
        .new_agent()
}

/// GitHub's latest release of maalc, from `api`.
pub fn fetch_latest(api: &str) -> Result<Release, String> {
    let url = format!("{api}/repos/{REPO}/releases/latest");
    let mut answer = agent(Duration::from_secs(20))
        .get(&url)
        .header("Accept", "application/vnd.github+json")
        .header("X-GitHub-Api-Version", "2022-11-28")
        .call()
        .map_err(|e| format!("{url}: {e}"))?;
    release_of(&answer.body_mut().read_to_string().map_err(|e| format!("{url}: {e}"))?)
}

// ---- the check, once a day ----

/// cache/update/check.json: when the window last asked, and the release that check found.
#[derive(Serialize, Deserialize)]
struct Record {
    checked: u64,
    release: Option<Release>,
}

/// Whether a check is due at `now` (Unix seconds): none yet, a day since the last, or a clock set back before it.
pub fn due(last: Option<u64>, now: u64) -> bool {
    last.is_none_or(|last| now < last || now - last >= CHECK_EVERY.as_secs())
}

/// The latest release as the last check found it, asking `api` again when a check is due (`due`). A check that fails counts
/// as the day's too, so the window asks GitHub at most once a day, and keeps the release the check before it found: it says
/// nothing new. A record that cannot be read is no record.
pub fn check(root: &Path, api: &str, now: u64) -> Option<Release> {
    let path = record_path(root);
    let record = fs::read_to_string(&path).ok().and_then(|text| serde_json::from_str::<Record>(&text).ok());
    if !due(record.as_ref().map(|r| r.checked), now) {
        return record.and_then(|r| r.release);
    }
    let release = fetch_latest(api).ok().or(record.and_then(|r| r.release));
    let _ = write_json(&path, &Record { checked: now, release: release.clone() });
    release
}

// ---- the download ----

/// How far a download is, for the page (api.ts UpdateProgress).
#[derive(Serialize, Clone, Debug, PartialEq)]
#[serde(tag = "step", rename_all = "snake_case")]
pub enum Progress {
    Download { received: u64, total: u64 },
    Verify,
    Extract,
}

/// Download `release`'s zip into cache/update/, check it against the release's sha256, and unpack it to its staged folder
/// (`staged_dir`); `progress` hears how far it is. A zip whose sha256 differs is deleted, nothing is unpacked, and the error
/// starts with MISMATCH. A staged folder there already (a download before a restart) is taken as it is.
pub fn download(root: &Path, release: &Release, progress: &mut dyn FnMut(Progress)) -> Result<PathBuf, String> {
    let version = release.parsed_version()?;
    let staged = staged_dir(root, &version);
    if staged.join(EXE).is_file() {
        return Ok(staged);
    }
    if !release.zip.starts_with("https://") && !cfg!(debug_assertions) {
        return Err(format!("{}: not an https address", release.zip));
    }
    let dir = update_dir(root);
    fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    let zip = dir.join(format!("maalc-v{version}.zip"));
    let part = dir.join(format!("maalc-v{version}.zip.part"));
    let got = fetch(release, &part, progress).and_then(|sha256| {
        if sha256 == release.sha256 {
            fs::rename(&part, &zip).map_err(|e| format!("{}: {e}", zip.display()))
        } else {
            Err(format!("{MISMATCH}: GitHub gives {} for {}, the download is {sha256}", release.sha256, release.zip))
        }
    });
    if let Err(e) = got {
        let _ = fs::remove_file(&part);
        return Err(e);
    }
    progress(Progress::Extract);
    let unpacked = unpack(&zip, &dir.join(format!("v{version}.part")), &staged);
    let _ = fs::remove_file(&zip); // unpacked or not, the zip has done its part
    unpacked.map(|()| staged)
}

/// Write the release's zip to `part`, telling `progress` every percent; its sha256 as lower-case hex.
fn fetch(release: &Release, part: &Path, progress: &mut dyn FnMut(Progress)) -> Result<String, String> {
    let url = &release.zip;
    let answer = agent(Duration::from_secs(30)).get(url).call().map_err(|e| format!("{url}: {e}"))?;
    let total = answer.body().content_length().unwrap_or(release.size);
    let mut body = answer.into_body().into_reader();
    let mut file = fs::File::create(part).map_err(|e| format!("{}: {e}", part.display()))?;
    let mut hash = Sha256::new();
    let mut buf = vec![0; 1 << 16];
    let (mut received, mut told) = (0u64, 0u64);
    progress(Progress::Download { received, total });
    loop {
        let n = body.read(&mut buf).map_err(|e| format!("{url}: {e}"))?;
        if n == 0 {
            break;
        }
        hash.update(&buf[..n]);
        file.write_all(&buf[..n]).map_err(|e| format!("{}: {e}", part.display()))?;
        received += n as u64;
        if received - told >= (total / 100).max(1 << 20) {
            told = received;
            progress(Progress::Download { received, total });
        }
    }
    file.sync_all().map_err(|e| format!("{}: {e}", part.display()))?;
    progress(Progress::Download { received, total });
    progress(Progress::Verify);
    Ok(hash.finalize().iter().map(|b| format!("{b:02x}")).collect())
}

/// Unpack `zip` into `part` (made fresh), then move the folder in it that holds maalc-gui.exe to `staged`: the zip's top, or
/// its one folder (release.yml zips the install as `maalc/`). An entry that would land outside `part`, a link, or a zip
/// with no maalc-gui.exe is refused, and nothing is left behind.
fn unpack(zip: &Path, part: &Path, staged: &Path) -> Result<(), String> {
    let _ = fs::remove_dir_all(part);
    let done = (|| {
        let file = fs::File::open(zip).map_err(|e| format!("{}: {e}", zip.display()))?;
        let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("{}: {e}", zip.display()))?;
        for i in 0..archive.len() {
            let mut entry = archive.by_index(i).map_err(|e| format!("{}: {e}", zip.display()))?;
            let name = entry.enclosed_name().ok_or_else(|| format!("{}: {} leaves the zip's folder", zip.display(), entry.name().unwrap_or_default()))?;
            if entry.is_symlink() {
                return Err(format!("{}: {} is a link", zip.display(), name.display()));
            }
            let to = part.join(&name);
            if entry.is_dir() {
                fs::create_dir_all(&to).map_err(|e| format!("{}: {e}", to.display()))?;
                continue;
            }
            if let Some(parent) = to.parent() {
                fs::create_dir_all(parent).map_err(|e| format!("{}: {e}", parent.display()))?;
            }
            let mut out = fs::File::create(&to).map_err(|e| format!("{}: {e}", to.display()))?;
            io::copy(&mut entry, &mut out).map_err(|e| format!("{}: {e}", to.display()))?;
        }
        let top = top_of(part).ok_or_else(|| format!("{}: no {EXE} at its top or in its one folder", zip.display()))?;
        if staged.exists() {
            fs::remove_dir_all(staged).map_err(|e| format!("{}: {e}", staged.display()))?;
        }
        fs::rename(&top, staged).map_err(|e| format!("{}: {e}", staged.display()))
    })();
    let _ = fs::remove_dir_all(part);
    done
}

/// The folder under `part` that holds maalc-gui.exe: `part` itself, or its one entry when that is a folder holding it.
fn top_of(part: &Path) -> Option<PathBuf> {
    if part.join(EXE).is_file() {
        return Some(part.to_path_buf());
    }
    let entries: Vec<_> = fs::read_dir(part).ok()?.filter_map(Result::ok).collect();
    match entries.as_slice() {
        [one] if one.path().join(EXE).is_file() => Some(one.path()),
        _ => None,
    }
}

// ---- the apply ----

/// Why an apply stopped, and whether everything it changed went back.
#[derive(Debug, PartialEq)]
pub struct Failure {
    pub error: String,
    pub restored: bool,
}

/// What the apply did to one root entry, for putting it back.
struct Step {
    name: OsString,
    existed: bool,
    moved: bool,
    copying: bool,
}

/// Whether a root entry is one of the KEEP folders (Windows names ignore case).
fn kept(name: &OsString) -> bool {
    KEEP.iter().any(|k| name.to_string_lossy().eq_ignore_ascii_case(k))
}

/// `f`, tried TRIES times while it fails.
fn retry<T>(mut f: impl FnMut() -> io::Result<T>) -> io::Result<T> {
    let mut tries = 1;
    loop {
        match f() {
            Err(_) if tries < TRIES => {
                tries += 1;
                thread::sleep(TRY_WAIT);
            }
            done => return done,
        }
    }
}

fn copy_tree(from: &Path, to: &Path) -> io::Result<()> {
    if fs::symlink_metadata(from)?.is_dir() {
        fs::create_dir(to)?;
        for entry in fs::read_dir(from)? {
            let entry = entry?;
            copy_tree(&entry.path(), &to.join(entry.file_name()))?;
        }
        Ok(())
    } else {
        fs::copy(from, to).map(|_| ())
    }
}

fn remove_tree(path: &Path) -> io::Result<()> {
    match fs::symlink_metadata(path) {
        Ok(m) if m.is_dir() => fs::remove_dir_all(path),
        Ok(_) => fs::remove_file(path),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}

/// Whether `old` holds files: an earlier apply that was cut short or could not put everything back left there the only copy
/// of what it replaced (`settle` keeps it), and a new apply would take its place.
pub fn holds_files(old: &Path) -> bool {
    fs::read_dir(old).is_ok_and(|mut entries| entries.next().is_some())
}

/// The error of an apply refused while `old` holds files (`holds_files`).
pub fn old_left(old: &Path) -> String {
    format!("{} holds the files an earlier update left: move them back into the maalc folder, or delete them, first", old.display())
}

/// Replace each entry of `root` that `staged` has, but the KEEP folders, with staged's: the root's moves into `old`, then
/// staged's is copied in; an entry the zip does not have stays. A step that fails puts back what it moved and removes what
/// it copied, newest first, and `Failure::restored` says whether all of it went back. An `old` that holds files is never
/// written over: the apply stops before it moves anything.
pub fn apply(root: &Path, staged: &Path, old: &Path) -> Result<(), Failure> {
    let early = |error: String| Failure { error, restored: true };
    let mut names: Vec<OsString> = fs::read_dir(staged)
        .map_err(|e| early(format!("{}: {e}", staged.display())))?
        .filter_map(|e| e.ok().map(|e| e.file_name()))
        .filter(|name| !kept(name))
        .collect();
    names.sort();
    if !names.iter().any(|n| n == EXE) {
        return Err(early(format!("{} has no {EXE}", staged.display())));
    }
    if holds_files(old) {
        return Err(early(old_left(old)));
    }
    remove_tree(old).and_then(|()| fs::create_dir_all(old)).map_err(|e| early(format!("{}: {e}", old.display())))?;
    let mut steps: Vec<Step> = Vec::new();
    let mut replace_all = || -> Result<(), String> {
        for name in &names {
            let (at, aside) = (root.join(name), old.join(name));
            steps.push(Step { name: name.clone(), existed: fs::symlink_metadata(&at).is_ok(), moved: false, copying: false });
            let step = steps.last_mut().unwrap();
            if step.existed {
                retry(|| fs::rename(&at, &aside)).map_err(|e| format!("cannot move {} aside: {e}", at.display()))?;
                step.moved = true;
            }
            step.copying = true;
            copy_tree(&staged.join(name), &at).map_err(|e| format!("cannot copy the new {}: {e}", name.to_string_lossy()))?;
        }
        Ok(())
    };
    let Err(error) = replace_all() else { return Ok(()) };
    let mut restored = true;
    for step in steps.iter().rev() {
        let (at, aside) = (root.join(&step.name), old.join(&step.name));
        if step.copying && (step.moved || !step.existed) && retry(|| remove_tree(&at)).is_err() {
            restored = false;
            continue; // the new copy is still there: the old one stays aside
        }
        if step.moved && retry(|| fs::rename(&aside, &at)).is_err() {
            restored = false;
        }
    }
    Err(Failure { error, restored })
}

// ---- the apply-update mode ----

/// cache/update/apply.json: how the last apply went. The apply-update mode writes `applying` before it moves anything, and
/// `done` or `failed` at its end; the next window shows it (`settle`).
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Outcome {
    pub state: State,
    pub from: String,
    pub to: String,
    #[serde(default)]
    pub error: Option<String>,
    /// For `failed`: everything the apply changed went back, so the old version runs as it was.
    #[serde(default)]
    pub restored: bool,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum State {
    /// Cut short: the process stopped between its first move and its end.
    Applying,
    Done,
    Failed,
}

impl Outcome {
    /// An outcome that leaves cache/update/old/ for the user: the files there are the only copy of what did not go back.
    fn keeps_old(&self) -> bool {
        self.state == State::Applying || (self.state == State::Failed && !self.restored)
    }
}

/// Start the unpacked new version (`staged`) in its apply-update mode, which waits for this window's process `pid` to exit.
pub fn launch(root: &Path, staged: &Path, pid: u32) -> Result<(), String> {
    let exe = staged.join(EXE);
    let mut command = Command::new(&exe);
    command.arg("--apply-update").arg(root).args(["--wait", &pid.to_string(), "--from", current()]).current_dir(staged);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // Out of a job the window may run in (a task the Task Scheduler started), which could end it with the window; a
        // job that allows no breakaway refuses that, and the process then starts inside it.
        const CREATE_BREAKAWAY_FROM_JOB: u32 = 0x0100_0000;
        if command.creation_flags(CREATE_BREAKAWAY_FROM_JOB).spawn().is_ok() {
            return Ok(());
        }
        command.creation_flags(0);
    }
    command.spawn().map(|_| ()).map_err(|e| format!("{}: {e}", exe.display()))
}

/// The apply-update mode: `maalc-gui.exe --apply-update <root> --wait <pid> --from <version>`, which `launch` starts from the
/// unpacked new version. Some(exit code) when the arguments ask for it; None for any other start. lib.rs run calls it before
/// the one window per folder (instance.rs) and Tauri, so this process never hands itself to a window that is still open.
pub fn apply_mode(args: &[String]) -> Option<i32> {
    let at = args.iter().position(|a| a == "--apply-update")?;
    let value = |flag: &str| args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).cloned();
    let (Some(root), Some(pid), Some(from)) = (args.get(at + 1), value("--wait").and_then(|p| p.parse().ok()), value("--from")) else {
        eprintln!("usage: {EXE} --apply-update <root> --wait <pid> --from <version>");
        return Some(2);
    };
    let Some(staged) = std::env::current_exe().ok().and_then(|exe| exe.parent().map(Path::to_path_buf)) else {
        return Some(2);
    };
    let root = PathBuf::from(root);
    let exited = wait_for_exit(pid, WAIT_OLD);
    let outcome = finish(&root, &staged, &from, exited);
    // The new window when it went through, the old one when it did not: either way the user has a window, which says how it
    // went. A window that never exited is still there (one started now would only hand itself to it), and says it at its
    // next start.
    if exited {
        let _ = Command::new(root.join(EXE)).current_dir(&root).spawn();
    }
    Some(if outcome.state == State::Done { 0 } else { 1 })
}

/// The apply-update mode's work once it waited for the old window (`exited`: it did), from version `from` to this one: the
/// journal says `applying`, the apply runs, and the journal says how it ended. A window that did not exit, or a journal that
/// cannot be written, moves nothing. Nor does an old/ that holds an earlier update's files (lib.rs apply_update refuses that
/// before the window closes): its journal stays as it is, so the next start keeps those files and says so again.
fn finish(root: &Path, staged: &Path, from: &str, exited: bool) -> Outcome {
    let journal = journal_path(root);
    let outcome = |state, error: Option<String>, restored| Outcome { state, from: from.into(), to: current().into(), error, restored };
    let old = old_dir(root);
    if holds_files(&old) {
        return outcome(State::Failed, Some(old_left(&old)), true);
    }
    if !exited {
        let o = outcome(State::Failed, Some(format!("the old window did not exit within {} s", WAIT_OLD.as_secs())), true);
        let _ = write_json(&journal, &o);
        return o;
    }
    if let Err(e) = write_json(&journal, &outcome(State::Applying, None, false)) {
        return outcome(State::Failed, Some(e), true);
    }
    let o = match apply(root, staged, &old) {
        Ok(()) => outcome(State::Done, None, true),
        Err(f) => outcome(State::Failed, Some(f.error), f.restored),
    };
    let _ = write_json(&journal, &o);
    o
}

/// Wait up to `limit` for process `pid` to exit; true when it did (or was gone already).
#[cfg(windows)]
fn wait_for_exit(pid: u32, limit: Duration) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, WAIT_OBJECT_0};
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_SYNCHRONIZE, WaitForSingleObject};
    // SAFETY: a handle OpenProcess gave, waited on and closed here.
    unsafe {
        let process = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
        if process.is_null() {
            return true;
        }
        let waited = WaitForSingleObject(process, limit.as_millis().try_into().unwrap_or(u32::MAX));
        CloseHandle(process);
        waited == WAIT_OBJECT_0
    }
}

#[cfg(not(windows))]
fn wait_for_exit(_pid: u32, _limit: Duration) -> bool {
    true
}

// ---- the next start ----

/// At the window's start: how the last apply went, for the page to show, and the cleanup that allows. An apply that went
/// through, or failed and put everything back, is shown once: old/ and the journal go. One that was cut short or did not put
/// everything back keeps both, since old/ holds the only copy of what did not go back, and is shown at each start until the
/// user empties old/. An old/ with no journal is a leftover, and goes.
pub fn settle(root: &Path) -> Option<Outcome> {
    let journal = journal_path(root);
    let outcome = read_journal(root);
    let old = old_dir(root);
    if outcome.as_ref().is_some_and(Outcome::keeps_old) {
        if old.exists() {
            return outcome;
        }
    } else {
        let _ = remove_tree(&old);
    }
    let _ = fs::remove_file(&journal);
    outcome.filter(|o| !o.keeps_old())
}

/// cache/update/apply.json as the last apply-update mode wrote it; None when there is none, or it cannot be read.
fn read_journal(root: &Path) -> Option<Outcome> {
    fs::read_to_string(journal_path(root)).ok().and_then(|text| serde_json::from_str(&text).ok())
}

/// Delete what an update left in cache/update/ that no update needs any more: the unpacked versions up to this one, and the
/// zips and part files. A newer version unpacked stays, for an update that waits (a run was under way, the window restarted).
/// Nothing goes while the journal says `applying`: a window that starts halfway through an apply (a scheduled start, #816)
/// may be the new version, whose unpacked folder the apply still copies from; the start after the apply cleans up.
/// True when nothing was left: a file still held (the apply-update process that just started this window) waits for a try.
pub fn clean(root: &Path) -> bool {
    if read_journal(root).is_some_and(|o| o.state == State::Applying) {
        return true;
    }
    let Ok(entries) = fs::read_dir(update_dir(root)) else { return true };
    let current = Version::parse(current()).ok();
    let mut clean = true;
    for entry in entries.filter_map(Result::ok) {
        let name = entry.file_name().to_string_lossy().into_owned();
        let stale = name.ends_with(".zip") || name.ends_with(".part")
            || (entry.path().is_dir() && version_of(&name).is_some_and(|v| name.starts_with('v') && current.as_ref().is_none_or(|c| &v <= c)));
        if stale && remove_tree(&entry.path()).is_err() {
            clean = false;
        }
    }
    clean
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    use std::io::BufRead;
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};

    /// A fresh folder under the temp dir for one test.
    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("maalc-update-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// Every file under `dir` with its bytes, by its path under `dir` ("/" between the parts), and each empty folder.
    fn tree(dir: &Path) -> BTreeMap<String, Vec<u8>> {
        fn walk(dir: &Path, base: &Path, out: &mut BTreeMap<String, Vec<u8>>) {
            let mut empty = true;
            for entry in fs::read_dir(dir).unwrap().map(Result::unwrap) {
                empty = false;
                let path = entry.path();
                if path.is_dir() {
                    walk(&path, base, out);
                } else {
                    let name = path.strip_prefix(base).unwrap().to_string_lossy().replace('\\', "/");
                    out.insert(name, fs::read(&path).unwrap());
                }
            }
            if empty && dir != base {
                out.insert(dir.strip_prefix(base).unwrap().to_string_lossy().replace('\\', "/") + "/", vec![]);
            }
        }
        let mut out = BTreeMap::new();
        walk(dir, dir, &mut out);
        out
    }

    fn put(root: &Path, files: &[(&str, &str)]) {
        for (name, text) in files {
            let path = root.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text).unwrap();
        }
    }

    /// An install of version 1.0.0 with the user's folders filled in.
    fn old_install(root: &Path) {
        put(root, &[
            ("maalc-gui.exe", "gui 1.0.0"),
            ("python/python.exe", "python 1.0.0"),
            ("python/Lib/old_only.py", "gone in 1.1.0"),
            ("agent/main.py", "agent 1.0.0"),
            ("NOTICE.md", "notice 1.0.0"),
            ("extra.txt", "the user's own file at the root"),
            ("config/settings.json", "{\"version\": 23}"),
            ("logs/runs.jsonl", "{}\n"),
            ("state/x.json", "state"),
            ("cache/keep.bin", "cache"),
            ("debug/maa.log", "debug"),
        ]);
    }

    /// The files of version 1.1.0's zip, under its one folder `maalc/`.
    const NEW: [(&str, &str); 5] = [
        ("maalc/maalc-gui.exe", "gui 1.1.0"),
        ("maalc/python/python.exe", "python 1.1.0"),
        ("maalc/agent/main.py", "agent 1.1.0"),
        ("maalc/NOTICE.md", "notice 1.1.0"),
        ("maalc/runner/__main__.py", "runner, new in 1.1.0"),
    ];

    /// A zip of `files` (deflated, as release.yml's 7z makes it).
    fn zip_of(files: &[(&str, &str)]) -> Vec<u8> {
        let mut w = zip::ZipWriter::new(io::Cursor::new(Vec::new()));
        let options = zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, text) in files {
            w.start_file(*name, options).unwrap();
            w.write_all(text.as_bytes()).unwrap();
        }
        w.finish().unwrap().into_inner()
    }

    fn sha256_of(bytes: &[u8]) -> String {
        Sha256::digest(bytes).iter().map(|b| format!("{b:02x}")).collect()
    }

    /// A local HTTP server standing in for GitHub: each path's status and body; `hits` lists the paths asked for, in order.
    struct Stub {
        base: String,
        hits: Arc<Mutex<Vec<String>>>,
        routes: Arc<Mutex<BTreeMap<String, (u16, Vec<u8>)>>>,
    }

    impl Stub {
        fn new() -> Stub {
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            let base = format!("http://{}", listener.local_addr().unwrap());
            let hits = Arc::new(Mutex::new(Vec::new()));
            let routes = Arc::new(Mutex::new(BTreeMap::new()));
            let (h, r) = (hits.clone(), routes.clone());
            thread::spawn(move || {
                for stream in listener.incoming() {
                    let Ok(stream) = stream else { continue };
                    let mut reader = io::BufReader::new(&stream);
                    let mut first = String::new();
                    if reader.read_line(&mut first).is_err() {
                        continue;
                    }
                    let mut line = String::new();
                    while reader.read_line(&mut line).is_ok_and(|n| n > 2) {
                        line.clear();
                    }
                    let path = first.split_whitespace().nth(1).unwrap_or("").to_string();
                    h.lock().unwrap().push(path.clone());
                    let (status, body) = r.lock().unwrap().get(&path).cloned().unwrap_or((404, b"not found".to_vec()));
                    let head = format!("HTTP/1.1 {status} X\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len());
                    let _ = (&stream).write_all(head.as_bytes()).and_then(|()| (&stream).write_all(&body));
                    // a graceful close: the write side shuts, and the socket stays until the client closes its own
                    let _ = stream.shutdown(std::net::Shutdown::Write);
                    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
                    let _ = io::copy(&mut reader, &mut io::sink());
                }
            });
            Stub { base, hits, routes }
        }

        fn serve(&self, path: &str, status: u16, body: impl Into<Vec<u8>>) {
            self.routes.lock().unwrap().insert(path.into(), (status, body.into()));
        }

        /// releases/latest answering with `tag`, its zip `zip` at /dl/<name> and the digest `digest`.
        fn release(&self, tag: &str, zip: &[u8], digest: &str) {
            let name = format!("maalc-{tag}.zip");
            self.serve(&format!("/dl/{name}"), 200, zip.to_vec());
            let json = serde_json::json!({
                "tag_name": tag, "html_url": format!("{}/releases/{tag}", self.base), "draft": false, "prerelease": false,
                "assets": [
                    {"name": "notes.txt", "browser_download_url": format!("{}/dl/notes.txt", self.base), "size": 1, "digest": null},
                    {"name": name, "browser_download_url": format!("{}/dl/{name}", self.base), "size": zip.len(), "digest": digest},
                ],
            });
            self.serve(&format!("/repos/{REPO}/releases/latest"), 200, json.to_string());
        }

        fn hits(&self) -> Vec<String> {
            self.hits.lock().unwrap().clone()
        }
    }

    // ---- versions ----

    #[test]
    fn a_tag_is_newer_only_when_its_version_comes_after_this_one() {
        assert!(newer("v1.1.0", "1.0.0"));
        assert!(newer("v1.10.0", "1.9.0"), "numbers, not text");
        assert!(newer("2.0.0", "1.99.99"));
        assert!(!newer("v1.0.0", "1.0.0"));
        assert!(!newer("v0.9.0", "1.0.0"));
        assert!(!newer("v1.1.0-rc.1", "1.1.0"), "a prerelease comes before its release");
        for bad in ["latest", "v1.1", "", "vv1.1.0"] {
            assert!(!newer(bad, "1.0.0"), "{bad}");
        }
    }

    // ---- the release ----

    #[test]
    fn the_release_is_its_zip_and_the_sha256_github_gives_for_it() {
        let stub = Stub::new();
        let digest = format!("sha256:{}", "AB".repeat(32));
        stub.release("v1.1.0", b"zip", &digest);
        let release = fetch_latest(&stub.base).unwrap();
        assert_eq!(release.version, "1.1.0");
        assert_eq!(release.zip, format!("{}/dl/maalc-v1.1.0.zip", stub.base));
        assert_eq!(release.size, 3);
        assert_eq!(release.sha256, "ab".repeat(32));
        assert_eq!(stub.hits(), [format!("/repos/{REPO}/releases/latest")]);
    }

    #[test]
    fn a_release_without_its_zip_or_a_sha256_digest_is_refused() {
        let base = |tag: &str, assets: serde_json::Value| serde_json::json!({"tag_name": tag, "assets": assets}).to_string();
        let asset = |digest: serde_json::Value| serde_json::json!([{"name": "maalc-v1.1.0.zip", "browser_download_url": "https://x/z", "size": 1, "digest": digest}]);
        let sha = serde_json::json!(format!("sha256:{}", "0".repeat(64)));
        assert!(release_of(&base("v1.1.0", asset(sha.clone()))).is_ok());
        assert!(release_of(&base("v1.1.0", asset(serde_json::Value::Null))).is_err(), "no digest");
        assert!(release_of(&base("v1.1.0", asset(serde_json::json!(format!("sha1:{}", "0".repeat(40)))))).is_err());
        assert!(release_of(&base("v1.1.0", asset(serde_json::json!("sha256:xyz")))).is_err());
        assert!(release_of(&base("v1.2.0", asset(sha.clone()))).is_err(), "the zip of another tag");
        assert!(release_of(&base("nightly", asset(sha))).is_err(), "a tag that is no version");
        assert!(release_of("not json").is_err());
    }

    // ---- the check, once a day ----

    #[test]
    fn the_window_asks_at_most_once_a_day_and_a_failed_check_says_nothing_new() {
        let root = scratch("daily");
        let stub = Stub::new();
        let latest = format!("/repos/{REPO}/releases/latest");
        stub.release("v1.1.0", b"zip", &format!("sha256:{}", "0".repeat(64)));
        let day = CHECK_EVERY.as_secs();
        let t0 = 1_800_000_000;
        assert_eq!(check(&root, &stub.base, t0).unwrap().version, "1.1.0");
        assert_eq!(check(&root, &stub.base, t0 + 3600).unwrap().version, "1.1.0", "the day's check, from the record");
        assert_eq!(check(&root, &stub.base, t0 + day - 1).unwrap().version, "1.1.0");
        assert_eq!(stub.hits().len(), 1);
        // a day later it asks again, and GitHub fails: the release the last check found stays, and that was the day's check
        stub.serve(&latest, 500, "down");
        assert_eq!(check(&root, &stub.base, t0 + day).unwrap().version, "1.1.0");
        assert_eq!(check(&root, &stub.base, t0 + day + 60).unwrap().version, "1.1.0");
        assert_eq!(stub.hits().len(), 2);
        // a clock set back before the last check asks again
        stub.release("v1.2.0", b"zip", &format!("sha256:{}", "0".repeat(64)));
        assert_eq!(check(&root, &stub.base, t0 - 1).unwrap().version, "1.2.0");
        assert_eq!(stub.hits().len(), 3);
    }

    #[test]
    fn with_no_record_and_no_answer_there_is_no_release() {
        let root = scratch("silent");
        assert_eq!(check(&root, "http://127.0.0.1:9", 1_800_000_000), None);
        assert!(!due(Some(1_800_000_000), 1_800_000_000 + 10));
        assert!(due(None, 0));
    }

    // ---- the download ----

    #[test]
    fn a_download_that_matches_its_sha256_unpacks_the_zips_folder() {
        let root = scratch("download");
        let stub = Stub::new();
        let zip = zip_of(&NEW);
        stub.release("v1.1.0", &zip, &format!("sha256:{}", sha256_of(&zip)));
        let release = fetch_latest(&stub.base).unwrap();
        let mut heard = Vec::new();
        let staged = download(&root, &release, &mut |p| heard.push(p)).unwrap();
        assert_eq!(staged, root.join("cache/update/v1.1.0"));
        assert_eq!(tree(&staged), NEW.iter().map(|(n, t)| (n["maalc/".len()..].to_string(), t.as_bytes().to_vec())).collect());
        let total = zip.len() as u64;
        assert_eq!(heard.first(), Some(&Progress::Download { received: 0, total }));
        assert_eq!(heard[heard.len() - 3..], [Progress::Download { received: total, total }, Progress::Verify, Progress::Extract]);
        // the zip and the part files are gone; a second download takes the unpacked folder as it is
        assert_eq!(fs::read_dir(update_dir(&root)).unwrap().count(), 1);
        let asked = stub.hits().len();
        assert_eq!(download(&root, &release, &mut |_| {}).unwrap(), staged);
        assert_eq!(stub.hits().len(), asked);
    }

    #[test]
    fn a_download_whose_sha256_differs_is_deleted_and_nothing_is_unpacked() {
        let root = scratch("mismatch");
        let stub = Stub::new();
        let zip = zip_of(&NEW);
        stub.release("v1.1.0", &zip, &format!("sha256:{}", sha256_of(b"another zip")));
        let release = fetch_latest(&stub.base).unwrap();
        let mut heard = Vec::new();
        let err = download(&root, &release, &mut |p| heard.push(p)).unwrap_err();
        assert!(err.starts_with(MISMATCH), "{err}");
        assert!(err.contains(&sha256_of(&zip)) && err.contains(&sha256_of(b"another zip")), "{err}");
        assert!(!heard.contains(&Progress::Extract));
        assert_eq!(fs::read_dir(update_dir(&root)).unwrap().count(), 0, "no zip, part file or folder is left");
    }

    #[test]
    fn a_download_that_fails_leaves_nothing() {
        let root = scratch("fails");
        let stub = Stub::new();
        stub.release("v1.1.0", b"zip", &format!("sha256:{}", sha256_of(b"zip")));
        stub.serve("/dl/maalc-v1.1.0.zip", 404, "gone");
        let release = fetch_latest(&stub.base).unwrap();
        assert!(download(&root, &release, &mut |_| {}).unwrap_err().contains("404"));
        assert_eq!(fs::read_dir(update_dir(&root)).unwrap().count(), 0);
    }

    #[test]
    fn a_zip_with_no_maalc_gui_exe_or_an_entry_outside_its_folder_is_refused() {
        let root = scratch("unpack");
        let (part, staged) = (root.join("v1.1.0.part"), root.join("v1.1.0"));
        let bad = |files: &[(&str, &str)]| {
            fs::write(root.join("z.zip"), zip_of(files)).unwrap();
            let err = unpack(&root.join("z.zip"), &part, &staged).unwrap_err();
            assert!(!part.exists() && !staged.exists(), "{err}");
            err
        };
        assert!(bad(&[("maalc/agent/main.py", "x")]).contains(EXE));
        assert!(bad(&[("a/maalc-gui.exe", "x"), ("b/maalc-gui.exe", "x")]).contains(EXE), "two folders");
        assert!(bad(&[("maalc-gui.exe", "x"), ("../evil.txt", "x")]).contains("leaves"));
        // a zip without the top folder unpacks as well
        fs::write(root.join("z.zip"), zip_of(&[("maalc-gui.exe", "x"), ("agent/main.py", "y")])).unwrap();
        unpack(&root.join("z.zip"), &part, &staged).unwrap();
        assert_eq!(tree(&staged).keys().collect::<Vec<_>>(), ["agent/main.py", "maalc-gui.exe"]);
        assert!(!part.exists());
    }

    // ---- the apply ----

    /// An install of 1.0.0 under `root` and 1.1.0 unpacked in its cache, as `download` leaves it.
    fn staged_install(name: &str) -> (PathBuf, PathBuf) {
        let root = scratch(name);
        old_install(&root);
        let staged = staged_dir(&root, &Version::new(1, 1, 0));
        put(&staged, &NEW.map(|(n, t)| (&n["maalc/".len()..], t)));
        (root, staged)
    }

    /// The tree of `root` but cache/, which holds the staged version and old/.
    fn outside_cache(root: &Path) -> BTreeMap<String, Vec<u8>> {
        tree(root).into_iter().filter(|(k, _)| !k.starts_with("cache/")).collect()
    }

    #[test]
    fn an_apply_replaces_the_zips_entries_and_leaves_the_users_folders_alone() {
        let (root, staged) = staged_install("apply");
        // a zip with a config/ and a Logs/ of its own: the user's stay as they are
        put(&staged, &[("config/settings.json", "{}"), ("Logs/x", "zip's")]);
        let before = tree(&root);
        apply(&root, &staged, &old_dir(&root)).unwrap();
        let after = tree(&root);
        for kept in ["config/settings.json", "logs/runs.jsonl", "state/x.json", "cache/keep.bin", "debug/maa.log", "extra.txt"] {
            assert_eq!(after[kept], before[kept], "{kept}");
        }
        assert_eq!(after["maalc-gui.exe"], b"gui 1.1.0");
        assert_eq!(after["python/python.exe"], b"python 1.1.0");
        assert_eq!(after["runner/__main__.py"], b"runner, new in 1.1.0");
        assert!(!after.contains_key("python/Lib/old_only.py"), "an entry the zip has is replaced whole");
        // what it replaced waits in old/ for the next start
        let old = tree(&old_dir(&root));
        assert_eq!(old.keys().collect::<Vec<_>>(), ["NOTICE.md", "agent/main.py", "maalc-gui.exe", "python/Lib/old_only.py", "python/python.exe"]);
        assert_eq!(old["maalc-gui.exe"], b"gui 1.0.0");
    }

    /// Open `path` so that no other handle may read, write, rename or delete it, as a running program holds its files.
    #[cfg(windows)]
    fn hold(path: &Path) -> fs::File {
        use std::os::windows::fs::OpenOptionsExt;
        fs::OpenOptions::new().read(true).share_mode(0).open(path).unwrap()
    }

    #[cfg(windows)]
    #[test]
    fn an_apply_that_fails_midway_puts_everything_back() {
        let (root, staged) = staged_install("rollback");
        let before = outside_cache(&root);
        // the new runner/ (after NOTICE.md, agent/, maalc-gui.exe and python/ in the apply's order) cannot be read
        let held = hold(&staged.join("runner/__main__.py"));
        let failed = apply(&root, &staged, &old_dir(&root)).unwrap_err();
        drop(held);
        assert!(failed.error.contains("runner"), "{}", failed.error);
        assert!(failed.restored);
        assert_eq!(outside_cache(&root), before, "the old version, as it was");
        assert_eq!(tree(&old_dir(&root)), BTreeMap::new());
    }

    #[cfg(windows)]
    #[test]
    fn a_root_entry_that_cannot_move_aside_stops_the_apply_with_the_rest_put_back() {
        let (root, staged) = staged_install("held");
        let before = outside_cache(&root);
        // a running Python holds python/: NOTICE.md, agent/ and maalc-gui.exe moved before it
        let held = hold(&root.join("python/python.exe"));
        let failed = apply(&root, &staged, &old_dir(&root)).unwrap_err();
        drop(held);
        assert!(failed.error.contains("python"), "{}", failed.error);
        assert!(failed.restored);
        assert_eq!(outside_cache(&root), before);
    }

    #[test]
    fn a_staged_folder_without_maalc_gui_exe_changes_nothing() {
        let (root, staged) = staged_install("noexe");
        fs::remove_file(staged.join(EXE)).unwrap();
        let before = tree(&root);
        let failed = apply(&root, &staged, &old_dir(&root)).unwrap_err();
        assert!(failed.restored && failed.error.contains(EXE));
        assert_eq!(tree(&root), before);
    }

    // ---- the apply-update mode and the next start ----

    fn journal(root: &Path) -> Outcome {
        serde_json::from_str(&fs::read_to_string(journal_path(root)).unwrap()).unwrap()
    }

    #[test]
    fn an_update_that_went_through_says_so_once_and_the_next_start_deletes_the_old_version() {
        let (root, staged) = staged_install("done");
        let outcome = finish(&root, &staged, "1.0.0", true);
        assert_eq!(outcome, Outcome { state: State::Done, from: "1.0.0".into(), to: current().into(), error: None, restored: true });
        assert_eq!(journal(&root), outcome);
        assert!(old_dir(&root).join(EXE).is_file());
        assert_eq!(settle(&root), Some(outcome));
        assert!(!old_dir(&root).exists() && !journal_path(&root).exists());
        assert_eq!(settle(&root), None, "once");
    }

    #[cfg(windows)]
    #[test]
    fn an_update_that_failed_and_went_back_says_why_once_and_the_next_start_deletes_old() {
        let (root, staged) = staged_install("failed");
        let before = outside_cache(&root);
        let held = hold(&staged.join("runner/__main__.py"));
        let outcome = finish(&root, &staged, "1.0.0", true);
        drop(held);
        assert_eq!((outcome.state, outcome.restored), (State::Failed, true));
        assert!(outcome.error.as_deref().unwrap().contains("runner"));
        assert_eq!(outside_cache(&root), before);
        assert_eq!(settle(&root), Some(outcome));
        assert!(!old_dir(&root).exists());
        assert_eq!(settle(&root), None);
    }

    #[test]
    fn a_window_that_never_exits_moves_nothing() {
        let (root, staged) = staged_install("stays");
        let before = outside_cache(&root);
        let outcome = finish(&root, &staged, "1.0.0", false);
        assert_eq!((outcome.state, outcome.restored), (State::Failed, true));
        assert!(outcome.error.as_deref().unwrap().contains("did not exit"));
        assert_eq!(outside_cache(&root), before);
        assert_eq!(settle(&root), Some(outcome));
    }

    #[test]
    fn the_files_an_earlier_update_left_in_old_are_never_written_over() {
        let (root, staged) = staged_install("again");
        put(&old_dir(&root), &[("python/python.exe", "the only copy of python 0.9.0")]);
        let left = Outcome { state: State::Failed, from: "0.9.0".into(), to: "1.0.0".into(), error: Some("disk full".into()), restored: false };
        write_json(&journal_path(&root), &left).unwrap();
        let before = tree(&root);
        let outcome = finish(&root, &staged, "1.0.0", true);
        assert_eq!((outcome.state, outcome.restored), (State::Failed, true));
        assert!(outcome.error.as_deref().unwrap().contains("earlier update"), "{outcome:?}");
        assert_eq!(tree(&root), before, "nothing moved, old/ and the earlier journal as they were");
        assert_eq!(settle(&root), Some(left), "the next start still keeps old/ and says why");
        assert!(old_dir(&root).join("python/python.exe").is_file());
        let failed = apply(&root, &staged, &old_dir(&root)).unwrap_err();
        assert!(failed.restored && failed.error.contains("earlier update"));
    }

    #[test]
    fn an_apply_cut_short_keeps_old_and_says_so_until_old_is_gone() {
        let root = scratch("cut");
        put(&old_dir(&root), &[("python/python.exe", "python 1.0.0")]);
        let cut = Outcome { state: State::Applying, from: "1.0.0".into(), to: "1.1.0".into(), error: None, restored: false };
        write_json(&journal_path(&root), &cut).unwrap();
        assert_eq!(settle(&root), Some(cut.clone()));
        assert_eq!(settle(&root), Some(cut), "at each start");
        assert!(old_dir(&root).join("python/python.exe").is_file());
        fs::remove_dir_all(old_dir(&root)).unwrap(); // the user put the files back
        assert_eq!(settle(&root), None);
        assert!(!journal_path(&root).exists());
        // an old/ with no journal is a leftover
        put(&old_dir(&root), &[("x", "y")]);
        assert_eq!(settle(&root), None);
        assert!(!old_dir(&root).exists());
    }

    #[test]
    fn the_next_start_deletes_the_versions_it_no_longer_needs_and_keeps_a_newer_one() {
        let root = scratch("clean");
        let ahead = Version::parse(current()).unwrap();
        let ahead = Version::new(ahead.major, ahead.minor + 1, 0);
        put(&update_dir(&root), &[
            ("check.json", "{}"),
            (&format!("v{}/maalc-gui.exe", current()), "this one, applied"),
            ("v0.1.0/maalc-gui.exe", "older"),
            (&format!("v{ahead}/maalc-gui.exe"), "newer, waiting to apply"),
            (&format!("maalc-v{ahead}.zip"), "a zip left by a crash"),
            (&format!("maalc-v{ahead}.zip.part"), "half a download"),
            (&format!("v{ahead}.part/x"), "half an unpack"),
        ]);
        assert!(clean(&root));
        assert_eq!(tree(&update_dir(&root)).keys().cloned().collect::<Vec<_>>(), ["check.json".to_string(), format!("v{ahead}/maalc-gui.exe")]);
    }

    #[test]
    fn a_window_that_starts_while_an_apply_runs_leaves_the_version_it_copies_from() {
        // a scheduled start opens this version's window halfway through its own apply: apply.json says `applying`
        let root = scratch("clean-applying");
        put(&update_dir(&root), &[(&format!("v{}/maalc-gui.exe", current()), "the version the apply copies from")]);
        put(&old_dir(&root), &[("python/python.exe", "moved aside")]);
        let applying = Outcome { state: State::Applying, from: "1.0.0".into(), to: current().into(), error: None, restored: false };
        write_json(&journal_path(&root), &applying).unwrap();
        assert!(clean(&root));
        assert!(staged_dir(&root, &Version::parse(current()).unwrap()).join(EXE).is_file());
        // once it went through, the next start cleans up
        write_json(&journal_path(&root), &Outcome { state: State::Done, restored: true, ..applying }).unwrap();
        assert!(clean(&root));
        assert!(!staged_dir(&root, &Version::parse(current()).unwrap()).exists());
    }

    #[test]
    fn the_apply_update_mode_takes_only_its_own_arguments() {
        let args = |list: &[&str]| list.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert_eq!(apply_mode(&args(&["maalc-gui.exe"])), None);
        assert_eq!(apply_mode(&args(&["maalc-gui.exe", "--run", "s1"])), None);
        assert_eq!(apply_mode(&args(&["maalc-gui.exe", "--apply-update"])), Some(2));
        assert_eq!(apply_mode(&args(&["maalc-gui.exe", "--apply-update", "R", "--wait", "x", "--from", "1.0.0"])), Some(2));
    }
}
