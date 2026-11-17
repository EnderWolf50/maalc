//! One window per maalc folder (#816): a scheduled run belongs to its folder (its task's name carries the folder's key,
//! src/schedule.rs), so a `maalc-gui.exe --run <id>` of one folder must never reach the window of another folder, which would
//! run that folder's task list there. The window of a folder holds a named mutex of the folder's key in this session; a
//! second start of the same folder hands its arguments and working folder to it through a named pipe of that key and ends.
//! (`tauri-plugin-single-instance` keys its lock by the app's identifier alone: one window for every folder.)

use serde::{Deserialize, Serialize};
use std::time::Duration;

/// A second start of maalc-gui.exe in the same folder: its arguments (the program first) and working folder.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct SecondStart {
    pub args: Vec<String>,
    pub cwd: String,
}

impl SecondStart {
    /// This process's own start.
    pub fn of_this_process() -> SecondStart {
        SecondStart {
            args: std::env::args_os().map(|a| a.to_string_lossy().into_owned()).collect(),
            cwd: std::env::current_dir().map(|d| d.display().to_string()).unwrap_or_default(),
        }
    }
}

/// How long a second start waits for the window's pipe (the window may be starting too).
pub const FORWARD_WAIT: Duration = Duration::from_secs(10);
/// The most a second start may send.
const MAX_FORWARD_BYTES: u64 = 64 * 1024;

/// The mutex the window of a folder holds, per logon session.
fn mutex_name(key: &str) -> String {
    format!("Local\\maalc-gui-{key}")
}

/// The pipe the window of a folder takes second starts on.
fn pipe_name(key: &str) -> String {
    format!(r"\\.\pipe\maalc-gui-{key}")
}

#[cfg(windows)]
fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

/// The folder's lock, held until the process ends.
#[cfg(windows)]
pub struct Lock(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for Lock {}
#[cfg(windows)]
unsafe impl Sync for Lock {}

#[cfg(windows)]
impl Drop for Lock {
    fn drop(&mut self) {
        unsafe { windows_sys::Win32::Foundation::CloseHandle(self.0) };
    }
}

/// Take the lock of the folder `key`: None when a window of that folder holds it already.
#[cfg(windows)]
pub fn claim(key: &str) -> Result<Option<Lock>, String> {
    use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS};
    use windows_sys::Win32::System::Threading::CreateMutexW;
    let name = wide(&mutex_name(key));
    let handle = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
    if handle.is_null() {
        return Err(format!("CreateMutex: {}", std::io::Error::last_os_error()));
    }
    if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
        unsafe { CloseHandle(handle) };
        return Ok(None);
    }
    Ok(Some(Lock(handle)))
}

/// One instance of the folder's pipe, for one second start to write to. Only this user (the pipe's default security lets
/// others read, not write) and only this machine reach it; a pipe of that name made first by another process is refused.
#[cfg(windows)]
fn pipe(key: &str) -> Result<std::fs::File, String> {
    use std::os::windows::io::FromRawHandle;
    use windows_sys::Win32::Foundation::INVALID_HANDLE_VALUE;
    use windows_sys::Win32::Storage::FileSystem::{FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_ACCESS_INBOUND};
    use windows_sys::Win32::System::Pipes::{CreateNamedPipeW, PIPE_REJECT_REMOTE_CLIENTS, PIPE_TYPE_BYTE, PIPE_WAIT};
    let name = wide(&pipe_name(key));
    let handle = unsafe {
        CreateNamedPipeW(name.as_ptr(), PIPE_ACCESS_INBOUND | FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS, 1, 0, MAX_FORWARD_BYTES as u32, 0, std::ptr::null())
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(format!("CreateNamedPipe {}: {}", pipe_name(key), std::io::Error::last_os_error()));
    }
    Ok(unsafe { std::fs::File::from_raw_handle(handle as _) })
}

/// Wait for the second start that connects to `one`, the folder's pipe, and read what it wrote, then let it go: the pipe has
/// one instance, which a start still connected (it wrote more than it may) would keep. None for what is not a start.
#[cfg(windows)]
fn take_start(one: &mut std::fs::File) -> Option<SecondStart> {
    use std::io::Read;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Foundation::{GetLastError, ERROR_NO_DATA, ERROR_PIPE_CONNECTED};
    use windows_sys::Win32::System::Pipes::{ConnectNamedPipe, DisconnectNamedPipe};
    // A start that connected before this wait (ERROR_PIPE_CONNECTED), or that already wrote and closed its end
    // (ERROR_NO_DATA), left its line in the pipe all the same: it is read either way.
    let waited = unsafe { ConnectNamedPipe(one.as_raw_handle() as _, std::ptr::null_mut()) } != 0;
    let connected = waited || matches!(unsafe { GetLastError() }, ERROR_PIPE_CONNECTED | ERROR_NO_DATA);
    let mut text = String::new();
    // the start writes one line and closes its end: the read ends there
    let read = connected && one.by_ref().take(MAX_FORWARD_BYTES).read_to_string(&mut text).is_ok();
    unsafe { DisconnectNamedPipe(one.as_raw_handle() as _) };
    if read { serde_json::from_str(text.trim()).ok() } else { None }
}

/// Take each second start of the folder `key` on its pipe, in a thread of its own, and hand it to `each`. The first pipe is
/// made before this returns, so a second start that comes at once finds it.
#[cfg(windows)]
pub fn serve(key: &str, each: impl Fn(SecondStart) + Send + 'static) -> Result<(), String> {
    let key = key.to_string();
    let first = pipe(&key)?;
    std::thread::spawn(move || {
        let mut one = first;
        loop {
            if let Some(start) = take_start(&mut one) {
                each(start);
            }
            drop(one);
            // a pipe that cannot be made now is tried again: the window keeps taking second starts as long as it is open
            one = loop {
                match pipe(&key) {
                    Ok(p) => break p,
                    Err(e) => {
                        eprintln!("second starts: {e}");
                        std::thread::sleep(Duration::from_secs(1));
                    }
                }
            };
        }
    });
    Ok(())
}

/// Hand `start` to the window of the folder `key`, waiting up to `limit` for its pipe, and let that window come to the front
/// (Windows lets the process the user started do that, not the window it wakes).
#[cfg(windows)]
pub fn forward(key: &str, start: &SecondStart, limit: Duration) -> Result<(), String> {
    use std::io::Write;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::System::Pipes::GetNamedPipeServerProcessId;
    use windows_sys::Win32::UI::WindowsAndMessaging::AllowSetForegroundWindow;
    let end = std::time::Instant::now() + limit;
    let mut pipe = loop {
        match std::fs::OpenOptions::new().write(true).open(pipe_name(key)) {
            Ok(p) => break p,
            // not made yet (the window is starting), or taken by another second start
            Err(_) if std::time::Instant::now() < end => std::thread::sleep(Duration::from_millis(50)),
            Err(e) => return Err(format!("{}: {e}", pipe_name(key))),
        }
    };
    let mut pid = 0u32;
    if unsafe { GetNamedPipeServerProcessId(pipe.as_raw_handle() as _, &mut pid) } != 0 {
        unsafe { AllowSetForegroundWindow(pid) };
    }
    let line = serde_json::to_string(start).map_err(|e| e.to_string())?;
    pipe.write_all(format!("{line}\n").as_bytes()).map_err(|e| format!("{}: {e}", pipe_name(key)))
}

// Off Windows (not a target maalc ships for) every start opens its own window.
#[cfg(not(windows))]
pub struct Lock;
#[cfg(not(windows))]
pub fn claim(_key: &str) -> Result<Option<Lock>, String> {
    Ok(Some(Lock))
}
#[cfg(not(windows))]
pub fn serve(_key: &str, _each: impl Fn(SecondStart) + Send + 'static) -> Result<(), String> {
    Ok(())
}
#[cfg(not(windows))]
pub fn forward(_key: &str, _start: &SecondStart, _limit: Duration) -> Result<(), String> {
    Err("one window per folder is Windows only".into())
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use std::sync::mpsc;

    /// A key no maalc folder has, for one test.
    fn key(name: &str) -> String {
        format!("test-{name}-{}", std::process::id())
    }

    #[test]
    fn a_folder_has_one_window_and_another_folder_its_own() {
        let a = key("one");
        let first = claim(&a).unwrap();
        assert!(first.is_some());
        assert!(claim(&a).unwrap().is_none(), "a second start of the same folder finds the window there");
        let other = claim(&key("other")).unwrap();
        assert!(other.is_some(), "a start of another folder opens a window of its own");
        drop(first);
        assert!(claim(&a).unwrap().is_some(), "once the window ended, a start opens one again");
    }

    #[test]
    fn a_second_start_hands_its_arguments_to_the_window_of_its_folder() {
        let k = key("forward");
        let (tx, rx) = mpsc::channel();
        serve(&k, move |s| { let _ = tx.send(s); }).unwrap();
        for id in ["s1", "s2"] {
            let start = SecondStart { args: vec!["maalc-gui.exe".into(), "--run".into(), id.into()], cwd: r"C:\Windows\system32".into() };
            forward(&k, &start, FORWARD_WAIT).unwrap();
            assert_eq!(rx.recv_timeout(Duration::from_secs(5)).unwrap(), start, "each start in turn");
        }
    }

    #[test]
    fn a_second_start_that_wrote_and_ended_before_the_window_waited_for_it_is_still_taken() {
        // the window was slow to wait on its pipe (a busy machine): the start connected, wrote its line and ended first
        let k = key("early");
        let mut one = pipe(&k).unwrap();
        let start = SecondStart { args: vec!["maalc-gui.exe".into(), "--run".into(), "s1".into()], cwd: "C:\\".into() };
        forward(&k, &start, FORWARD_WAIT).unwrap();
        assert_eq!(take_start(&mut one), Some(start));
    }

    #[test]
    fn a_second_start_with_no_window_to_take_it_fails_after_its_wait() {
        let started = std::time::Instant::now();
        let err = forward(&key("nobody"), &SecondStart::of_this_process(), Duration::from_millis(300)).unwrap_err();
        assert!(err.contains("maalc-gui-test-nobody"), "{err}");
        assert!(started.elapsed() >= Duration::from_millis(300));
    }
}
