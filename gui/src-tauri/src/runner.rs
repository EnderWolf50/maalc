//! The runner (runner/, #812) as the window starts it (#815, spec #811 「執行器」): one Python process a command, `scan` or
//! `start`, in a Job Object of its own, so ending it ends what it started (the bot, the adb server MaaFramework started), and
//! so does the window's exit. Its JSON lines (runner/protocol.py, tests/runner_cases.json) are read here and go to the page
//! as they come, with what the window itself saw: a line that is not the protocol, the stop it sent, the tree it ended, the
//! exit. A stop sends the stop command; when the runner says it cannot stop (`error stop_timeout`) or has not ended
//! `stop_wait` after it, the window ends the whole tree.

use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{ChildStdin, Command as Process, Stdio};
use std::sync::{mpsc, Arc, Condvar, Mutex};
use std::thread;
use std::time::Duration;

/// runner/protocol.py VERSION.
pub const VERSION: i64 = 1;
/// How long the window waits for the runner's end after the stop command before it ends the runner's tree itself: the runner
/// tries for 60 s and then reports stop_timeout (runner/session.py STOP_LIMIT); this is that and the time its end takes.
pub const STOP_WAIT: Duration = Duration::from_secs(75);
/// How long a scan may take before its runner is ended: MaaFramework's toolkit asks every adb it finds.
pub const SCAN_WAIT: Duration = Duration::from_secs(60);
/// The last lines (log events, the lines that are not the protocol) an exit report quotes.
pub const TAIL: usize = 20;
/// How long the output is read on after the runner exited: what it wrote is in the pipe by then.
const DRAIN: Duration = Duration::from_secs(2);

// ---- the protocol (runner/protocol.py) ----

/// A param of a reason code: text or a whole number (runner/protocol.py params_ok).
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
#[serde(untagged)]
pub enum ReasonParam {
    Text(String),
    Number(i64),
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    Runner,
    Agent,
    Console,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    Pending,
    Running,
    Succeeded,
    Failed,
    Stopped,
    Cancelled,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LinkState {
    Launching,
    Waiting,
    Connecting,
    Connected,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResourceState {
    Loading,
    Loaded,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RunResult {
    Succeeded,
    Failed,
    Stopped,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ErrorKind {
    Protocol,
    DeviceMissing,
    LaunchFailed,
    DeviceTimeout,
    ConnectFailed,
    ResourceFailed,
    AgentFailed,
    AgentExit,
    StopTimeout,
    Internal,
}

/// A MuMu device's instance: its number, MuMuManager.exe, the MuMu folder.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Mumu {
    pub index: i64,
    pub manager: String,
    pub path: String,
}

/// A device a scan found. `mumu` is there for every device, null for one that is not MuMu.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Device {
    pub name: String,
    pub address: String,
    pub adb_path: String,
    #[serde(deserialize_with = "Option::deserialize")] // required, though it may be null
    pub mumu: Option<Mumu>,
}

/// An event of the runner, without its "v".
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(tag = "event", rename_all = "snake_case", deny_unknown_fields)]
pub enum Event {
    Ready { pid: i64 },
    Log { t: String, source: Source, line: String },
    Devices { devices: Vec<Device> },
    Connection { state: LinkState, address: String },
    Resource { state: ResourceState },
    Task {
        index: i64,
        entry: String,
        state: TaskState,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reason: Option<String>,
        /// the reason's code of agent/stop_reasons.json and its params, which the page says it by (#881)
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reason_code: Option<String>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reason_params: Option<BTreeMap<String, ReasonParam>>,
    },
    Error {
        kind: ErrorKind,
        message: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        code: Option<i64>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        tail: Option<Vec<String>>,
    },
    End { result: RunResult },
}

/// The device a start asks for; each part null for none (the runner then takes the first device it finds).
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Default)]
#[serde(default, deny_unknown_fields)]
pub struct DeviceWant {
    pub address: Option<String>,
    pub mumu_index: Option<i64>,
    pub mumu_manager: Option<String>,
}

/// A task of a start: its entry node. It reads its options from the settings file at its start (#813).
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TaskSpec {
    pub entry: String,
}

impl TaskSpec {
    pub fn new(entry: String) -> TaskSpec {
        TaskSpec { entry }
    }
}

/// A null device is no device asked for, as the runner reads it.
fn device_or_none<'de, D: Deserializer<'de>>(d: D) -> Result<DeviceWant, D::Error> {
    Ok(Option::<DeviceWant>::deserialize(d)?.unwrap_or_default())
}

/// A command to the runner, without its "v". Stop and scan take no fields: `{}` keeps an unknown field refused.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(tag = "cmd", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    Start {
        #[serde(default)]
        root: Option<String>,
        #[serde(default, deserialize_with = "device_or_none")]
        device: DeviceWant,
        tasks: Vec<TaskSpec>,
    },
    Stop {},
    Scan {},
}

/// The object a protocol line holds, its "v" taken out once it is this version.
fn versioned(line: &str) -> Result<Map<String, Value>, String> {
    let value: Value = serde_json::from_str(line).map_err(|e| format!("not JSON: {e}"))?;
    let Value::Object(mut map) = value else { return Err("not a JSON object".into()) };
    match map.remove("v") {
        Some(Value::Number(n)) if n.as_i64() == Some(VERSION) => Ok(map),
        other => Err(format!("protocol version {}, the window speaks {VERSION}", other.map_or("none".into(), |v| v.to_string()))),
    }
}

impl Event {
    /// The event one line of the runner's output holds; why not, when it does not follow the protocol.
    pub fn parse(line: &str) -> Result<Event, String> {
        serde_json::from_value(Value::Object(versioned(line)?)).map_err(|e| e.to_string())
    }
}

impl Command {
    /// The command one line holds, checked as the runner checks it (runner/protocol.py command): the window only writes
    /// commands, and the shared cases read them back with this.
    #[cfg(test)]
    pub fn parse(line: &str) -> Result<Command, String> {
        let cmd: Command = serde_json::from_value(Value::Object(versioned(line)?)).map_err(|e| e.to_string())?;
        cmd.check()?;
        Ok(cmd)
    }

    /// What the runner refuses beyond the fields' types: a start with no task, or a task with no entry.
    pub fn check(&self) -> Result<(), String> {
        if let Command::Start { tasks, .. } = self {
            if tasks.is_empty() {
                return Err("start: tasks must be a list of at least one task".into());
            }
            for (i, t) in tasks.iter().enumerate() {
                if t.entry.is_empty() {
                    return Err(format!("start: tasks[{i}].entry must name the task's entry node"));
                }
            }
        }
        Ok(())
    }

    /// The command as one protocol line, with its "v".
    pub fn line(&self) -> String {
        let mut value = serde_json::to_value(self).expect("a command serialises");
        value.as_object_mut().expect("a command is an object").insert("v".into(), VERSION.into());
        value.to_string()
    }
}

// ---- what the page gets ----

/// What the page gets of a run, in the order it happened. `Exit` comes last, once.
#[derive(Serialize, Debug, Clone, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")] // "type": the error event has a field named kind
pub enum Message {
    /// An event of the runner.
    Event(Event),
    /// A line of the runner's output that is not the protocol, with why.
    Invalid { line: String, error: String },
    /// A line the runner wrote to its stderr: Python's own report before the runner took its output over.
    Output { line: String },
    /// The stop command went to the runner.
    Stopping,
    /// The window ended the runner's process tree, and why.
    Killed { reason: String },
    /// The runner's process ended: its exit code (none when it has none), whether its end event came first, and its last
    /// lines (log events and the lines that were not the protocol).
    Exit { code: Option<i32>, ended: bool, tail: Vec<String> },
}

// ---- the process tree ----

/// A Job Object that ends every process in it when it is ended or its last handle closes (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE):
/// a process the runner starts joins it. One started with CREATE_BREAKAWAY_FROM_JOB does not (JOB_OBJECT_LIMIT_BREAKAWAY_OK):
/// the runner starts MuMuManager so (runner/devices.py launch), and the emulator outlives the run.
#[cfg(windows)]
pub struct Job(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for Job {}
#[cfg(windows)]
unsafe impl Sync for Job {}

#[cfg(windows)]
impl Job {
    pub fn new() -> Result<Job, String> {
        use windows_sys::Win32::System::JobObjects::*;
        let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if handle.is_null() {
            return Err(format!("CreateJobObject: {}", std::io::Error::last_os_error()));
        }
        let job = Job(handle);
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;
        let size = std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32;
        let set = unsafe {
            SetInformationJobObject(job.0, JobObjectExtendedLimitInformation, &limits as *const _ as *const _, size)
        };
        if set == 0 {
            return Err(format!("SetInformationJobObject: {}", std::io::Error::last_os_error()));
        }
        Ok(job)
    }

    pub fn assign(&self, child: &std::process::Child) -> Result<(), String> {
        use std::os::windows::io::AsRawHandle;
        let done = unsafe { windows_sys::Win32::System::JobObjects::AssignProcessToJobObject(self.0, child.as_raw_handle()) };
        if done == 0 { Err(format!("AssignProcessToJobObject: {}", std::io::Error::last_os_error())) } else { Ok(()) }
    }

    /// End every process in the job.
    pub fn terminate(&self) {
        unsafe { windows_sys::Win32::System::JobObjects::TerminateJobObject(self.0, 1) };
    }

    /// The job's limit flags.
    #[cfg(test)]
    pub fn limits(&self) -> u32 {
        use windows_sys::Win32::System::JobObjects::*;
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        let size = std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32;
        let read = unsafe {
            QueryInformationJobObject(self.0, JobObjectExtendedLimitInformation, &mut info as *mut _ as *mut _, size, std::ptr::null_mut())
        };
        if read == 0 { 0 } else { info.BasicLimitInformation.LimitFlags }
    }

    /// How many processes of the job are still running.
    #[cfg(test)]
    pub fn active(&self) -> u32 {
        use windows_sys::Win32::System::JobObjects::*;
        let mut info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
        let size = std::mem::size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32;
        let read = unsafe {
            QueryInformationJobObject(self.0, JobObjectBasicAccountingInformation, &mut info as *mut _ as *mut _, size, std::ptr::null_mut())
        };
        if read == 0 { 0 } else { info.ActiveProcesses }
    }
}

#[cfg(windows)]
impl Drop for Job {
    fn drop(&mut self) {
        unsafe { windows_sys::Win32::Foundation::CloseHandle(self.0) };
    }
}

/// Off Windows there is no job: the runner alone is started, and ending it is left to its own end.
#[cfg(not(windows))]
pub struct Job;

#[cfg(not(windows))]
impl Job {
    pub fn new() -> Result<Job, String> {
        Ok(Job)
    }
    pub fn assign(&self, _child: &std::process::Child) -> Result<(), String> {
        Ok(())
    }
    pub fn terminate(&self) {}
    #[cfg(test)]
    pub fn active(&self) -> u32 {
        0
    }
}

// ---- a run ----

/// The program that runs the runner, its arguments and its working folder.
#[derive(Debug, Clone)]
pub struct Spawn {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub dir: PathBuf,
}

/// The install's Python: the zip's python/python.exe, or, in an install tools/install.py made without --release, the Python
/// interface.json names as the agent's child_exec (the venv's).
pub fn python(root: &Path) -> Result<PathBuf, String> {
    let bundled = root.join("python").join("python.exe");
    if bundled.is_file() {
        return Ok(bundled);
    }
    let missing = || format!("no Python for the runner: {} has no python\\python.exe", root.display());
    let text = fs::read_to_string(root.join("interface.json")).map_err(|_| missing())?;
    // interface.json allows whole-line // comments, as the pipeline does
    let plain: String = text.lines().filter(|l| !l.trim_start().starts_with("//")).collect::<Vec<_>>().join("\n");
    let json: Value = serde_json::from_str(&plain).map_err(|e| format!("{}: {e}", root.join("interface.json").display()))?;
    let exec = json["agent"]["child_exec"].as_str().ok_or_else(missing)?;
    let path = root.join(exec);
    if path.is_file() { Ok(path) } else { Err(format!("{}, and interface.json's child_exec {exec} is not a file", missing())) }
}

/// `python <root>/runner/__main__.py`, from <root>.
pub fn runner_spawn(root: &Path) -> Result<Spawn, String> {
    let main = root.join("runner").join("__main__.py");
    if !main.is_file() {
        return Err(format!("{} has no runner\\__main__.py", root.display()));
    }
    Ok(Spawn { program: python(root)?, args: vec![main.display().to_string()], dir: root.to_path_buf() })
}

pub type Sink = Box<dyn Fn(Message) + Send + Sync>;

#[derive(Default)]
struct State {
    end_event: bool, // the end event came
    stopping: bool, // the stop command went
    killed: bool,
    done: bool, // Exit went: nothing more is sent
    tail: VecDeque<String>,
}

impl State {
    fn keep(&mut self, line: &str) {
        if self.tail.len() == TAIL {
            self.tail.pop_front();
        }
        self.tail.push_back(line.to_string());
    }
}

/// One runner process and its tree. Every message goes to the sink under one lock, so the sink sees them in one order.
pub struct Run {
    stdin: Mutex<Option<ChildStdin>>,
    job: Job,
    state: Mutex<State>,
    exited: Condvar,
    sink: Sink,
    stop_wait: Duration,
}

impl Run {
    /// Start the runner on `first` (a start or a scan) and follow it; every message goes to `sink` until `Exit`.
    pub fn spawn(spawn: &Spawn, first: &Command, stop_wait: Duration, sink: Sink) -> Result<Arc<Run>, String> {
        first.check()?;
        let job = Job::new()?;
        let mut process = Process::new(&spawn.program);
        process
            .args(&spawn.args)
            .current_dir(&spawn.dir)
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            process.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: the window's Python opens no console
        }
        let mut child = process.spawn().map_err(|e| format!("{}: {e}", spawn.program.display()))?;
        if let Err(e) = job.assign(&child) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
        let mut stdin = child.stdin.take().expect("stdin is piped");
        let stdout = child.stdout.take().expect("stdout is piped");
        let stderr = child.stderr.take().expect("stderr is piped");
        // the first command goes before anything reads: a runner that exits at once still has it
        let _ = writeln!(stdin, "{}", first.line()).and_then(|_| stdin.flush());
        let run = Arc::new(Run {
            stdin: Mutex::new(Some(stdin)),
            job,
            state: Mutex::new(State::default()),
            exited: Condvar::new(),
            sink,
            stop_wait,
        });
        let (read, drained) = mpsc::channel::<()>();
        for (pipe, out) in [(Box::new(stdout) as Box<dyn Read + Send>, true), (Box::new(stderr), false)] {
            let (run, read) = (run.clone(), read.clone());
            thread::spawn(move || {
                each_line(pipe, |line| if out { run.out_line(line) } else { run.err_line(line) });
                let _ = read.send(());
            });
        }
        drop(read);
        let waiter = run.clone();
        thread::spawn(move || {
            let code = child.wait().ok().and_then(|s| s.code());
            for _ in 0..2 {
                if drained.recv_timeout(DRAIN).is_err() {
                    break; // a process the runner started may hold a pipe open
                }
            }
            // what the runner left running (the adb server MaaFramework started, a process that holds its output) ends with
            // it, as on a stop (spec #811: the next connect starts the adb server again)
            waiter.job.terminate();
            let mut st = waiter.state.lock().unwrap();
            *waiter.stdin.lock().unwrap() = None;
            let exit = Message::Exit { code, ended: st.end_event, tail: st.tail.iter().cloned().collect() };
            (waiter.sink)(exit);
            st.done = true;
            waiter.exited.notify_all();
        });
        Ok(run)
    }

    fn out_line(self: &Arc<Self>, line: &str) {
        let mut st = self.state.lock().unwrap();
        if st.done {
            return;
        }
        let message = match Event::parse(line) {
            Ok(event) => {
                match &event {
                    Event::Log { line, .. } => st.keep(line),
                    Event::End { .. } => st.end_event = true,
                    _ => {}
                }
                let cannot_stop = matches!(event, Event::Error { kind: ErrorKind::StopTimeout, .. });
                (self.sink)(Message::Event(event));
                if cannot_stop {
                    self.kill_locked(&mut st, "the runner cannot stop MaaFramework".into());
                }
                return;
            }
            Err(error) => Message::Invalid { line: line.to_string(), error },
        };
        st.keep(line);
        (self.sink)(message);
    }

    fn err_line(&self, line: &str) {
        let mut st = self.state.lock().unwrap();
        if !st.done {
            st.keep(line);
            (self.sink)(Message::Output { line: line.to_string() });
        }
    }

    /// Ask the runner to stop. True when it was asked now or before; false when it has already ended. When it has not ended
    /// `stop_wait` later, the window ends its tree.
    pub fn stop(self: &Arc<Self>) -> bool {
        {
            let mut st = self.state.lock().unwrap();
            if st.done {
                return false;
            }
            if st.stopping {
                return true;
            }
            st.stopping = true;
            (self.sink)(Message::Stopping);
        }
        let line = Command::Stop {}.line();
        let wrote = match self.stdin.lock().unwrap().as_mut() {
            Some(stdin) => writeln!(stdin, "{line}").and_then(|_| stdin.flush()),
            None => Err(std::io::ErrorKind::BrokenPipe.into()),
        };
        if let Err(e) = wrote {
            self.kill(format!("the runner does not take the stop command: {e}"));
            return true;
        }
        let run = self.clone();
        thread::spawn(move || {
            let st = run.state.lock().unwrap();
            let (mut st, _) = run.exited.wait_timeout_while(st, run.stop_wait, |s| !s.done).unwrap();
            if !st.done {
                let reason = format!("the runner did not end {} s after the stop", run.stop_wait.as_secs_f32());
                run.kill_locked(&mut st, reason);
            }
        });
        true
    }

    /// End the runner's whole tree now, saying why.
    pub fn kill(&self, reason: String) {
        let mut st = self.state.lock().unwrap();
        self.kill_locked(&mut st, reason);
    }

    fn kill_locked(&self, st: &mut State, reason: String) {
        if st.done || st.killed {
            return;
        }
        st.killed = true;
        self.job.terminate();
        (self.sink)(Message::Killed { reason });
    }

    /// Whether the runner's process has ended and its Exit went.
    pub fn done(&self) -> bool {
        self.state.lock().unwrap().done
    }

    /// Wait up to `limit` for the Exit; whether it went.
    pub fn wait(&self, limit: Duration) -> bool {
        let st = self.state.lock().unwrap();
        self.exited.wait_timeout_while(st, limit, |s| !s.done).unwrap().0.done
    }

    /// How many processes of its tree still run.
    #[cfg(test)]
    pub fn active(&self) -> u32 {
        self.job.active()
    }
}

/// Each line of a pipe, as UTF-8 (a bad byte replaced), without its line end, until the pipe ends.
fn each_line(pipe: Box<dyn Read + Send>, mut each: impl FnMut(&str)) {
    let mut reader = BufReader::new(pipe);
    let mut buf = Vec::new();
    loop {
        buf.clear();
        match reader.read_until(b'\n', &mut buf) {
            Ok(0) | Err(_) => return,
            Ok(_) => each(String::from_utf8_lossy(&buf).trim_end_matches(['\r', '\n'])),
        }
    }
}

/// Scan for devices with a runner of its own: the devices it found, MuMu first, or why there are none. A scan that has not
/// ended `limit` later is ended.
pub fn scan(spawn: &Spawn, limit: Duration) -> Result<Vec<Device>, String> {
    let (tx, rx) = mpsc::channel::<Message>();
    let tx = Mutex::new(tx);
    let run = Run::spawn(spawn, &Command::Scan {}, limit, Box::new(move |m| { let _ = tx.lock().unwrap().send(m); }))?;
    if !run.wait(limit) {
        run.kill(format!("the scan did not end in {} s", limit.as_secs()));
        run.wait(DRAIN);
    }
    let (mut devices, mut errors, mut tail) = (None, Vec::new(), Vec::new());
    for m in rx.try_iter() {
        match m {
            Message::Event(Event::Devices { devices: found }) => devices = Some(found),
            Message::Event(Event::Error { message, .. }) => errors.push(message),
            Message::Killed { reason } => errors.push(reason),
            Message::Exit { tail: last, .. } => tail = last,
            _ => {}
        }
    }
    devices.ok_or_else(|| {
        let said = if errors.is_empty() { tail } else { errors };
        format!("the scan found no device list{}", if said.is_empty() { String::new() } else { format!(": {}", said.join(" / ")) })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    /// tests/runner_cases.json: the protocol's shared cases, which tests/test_runner_protocol.py runs on the runner.
    fn cases() -> Value {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/runner_cases.json");
        serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
    }

    #[test]
    fn the_shared_cases_speak_this_version() {
        assert_eq!(cases()["version"], VERSION);
    }

    #[test]
    fn each_command_line_parses_as_the_runner_reads_it_or_is_refused() {
        for case in cases()["commands"].as_array().unwrap() {
            let line = case["line"].as_str().unwrap();
            match case.get("command") {
                Some(want) => {
                    let cmd = Command::parse(line).unwrap_or_else(|e| panic!("{line}: {e}"));
                    assert_eq!(&serde_json::to_value(&cmd).unwrap(), want, "{line}");
                    // what the window sends of it reads back as the same command
                    assert_eq!(Command::parse(&cmd.line()).unwrap(), cmd, "{line}");
                }
                None => assert!(Command::parse(line).is_err(), "{line} parsed"),
            }
        }
    }

    #[test]
    fn the_window_waits_out_the_runners_own_stop_before_it_ends_the_tree() {
        // the runner reports stop_timeout after its STOP_LIMIT; only after STOP_WAIT does the window end the tree itself
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../runner/session.py");
        let session = fs::read_to_string(path).unwrap();
        let limit: f64 = session.lines().find_map(|l| l.strip_prefix("STOP_LIMIT = "))
            .and_then(|rest| rest.split_whitespace().next()).and_then(|n| n.parse().ok()).expect("session.py STOP_LIMIT");
        assert!(STOP_WAIT.as_secs_f64() > limit, "STOP_WAIT {STOP_WAIT:?} <= STOP_LIMIT {limit} s");
    }

    #[test]
    fn each_event_is_taken_or_refused_as_the_cases_say() {
        for case in cases()["events"].as_array().unwrap() {
            let line = case["event"].to_string();
            let parsed = Event::parse(&line);
            assert_eq!(parsed.is_ok(), case["valid"].as_bool().unwrap(), "{line}: {parsed:?}");
        }
    }

    #[test]
    fn an_error_event_keeps_its_own_kind_beside_the_message_type() {
        let e = Event::parse(r#"{"v":1,"event":"error","kind":"stop_timeout","message":"MaaFramework did not stop in 60 s"}"#).unwrap();
        let sent = serde_json::to_string(&Message::Event(e)).unwrap();
        let read: Value = serde_json::from_str(&sent).unwrap();
        assert_eq!(read, serde_json::json!({"type": "event", "event": "error", "kind": "stop_timeout", "message": "MaaFramework did not stop in 60 s"}));
        assert_eq!(sent.matches("\"kind\"").count(), 1, "{sent}");
    }

    #[test]
    fn the_page_gets_an_event_with_its_fields_under_type_event() {
        let e = Event::parse(r#"{"v":1,"event":"task","index":1,"entry":"ClaimMail","state":"cancelled","reason":"maintenance"}"#).unwrap();
        let sent = serde_json::to_value(Message::Event(e)).unwrap();
        assert_eq!(sent, serde_json::json!({"type": "event", "event": "task", "index": 1, "entry": "ClaimMail", "state": "cancelled", "reason": "maintenance"}));
        assert_eq!(serde_json::to_value(Message::Stopping).unwrap(), serde_json::json!({"type": "stopping"}));
        // a reason's code and its params (#881) go to the page as they came
        let e = Event::parse(r#"{"v":1,"event":"task","index":0,"entry":"MirrorDungeon","state":"failed","reason":"x","reason_code":"ConnectFailed","reason_params":{"address":"127.0.0.1:16384","n":3}}"#).unwrap();
        assert_eq!(serde_json::to_value(Message::Event(e)).unwrap(), serde_json::json!({"type": "event", "event": "task", "index": 0,
            "entry": "MirrorDungeon", "state": "failed", "reason": "x", "reason_code": "ConnectFailed", "reason_params": {"address": "127.0.0.1:16384", "n": 3}}));
    }

    #[cfg(windows)]
    #[test]
    fn the_job_ends_its_processes_and_lets_the_emulators_launch_break_away() {
        use windows_sys::Win32::System::JobObjects::{JOB_OBJECT_LIMIT_BREAKAWAY_OK, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE};
        // runner/devices.py launch starts MuMuManager with CREATE_BREAKAWAY_FROM_JOB: MuMu outlives the run
        let flags = Job::new().unwrap().limits();
        assert_eq!(flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE);
        assert_eq!(flags & JOB_OBJECT_LIMIT_BREAKAWAY_OK, JOB_OBJECT_LIMIT_BREAKAWAY_OK);
    }

    #[test]
    fn a_start_with_no_task_or_an_empty_entry_is_refused_before_anything_starts() {
        let start = |tasks: Vec<TaskSpec>| Command::Start { root: None, device: DeviceWant::default(), tasks };
        assert!(start(vec![]).check().is_err());
        assert!(start(vec![TaskSpec::new("".into())]).check().is_err());
        let spawn = Spawn { program: "cmd.exe".into(), args: vec![], dir: std::env::temp_dir() };
        assert!(Run::spawn(&spawn, &start(vec![]), STOP_WAIT, Box::new(|_| {})).is_err());
    }

    // ---- a run, with cmd.exe scripts standing in for the runner ----

    /// A fresh folder under the temp dir for one test.
    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("maalc-runner-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// A batch file as the runner: `lines` are its lines after @echo off.
    fn fake(name: &str, lines: &[&str]) -> Spawn {
        let dir = scratch(name);
        let script = dir.join("runner.cmd");
        fs::write(&script, format!("@echo off\r\n{}\r\n", lines.join("\r\n"))).unwrap();
        Spawn { program: "cmd.exe".into(), args: vec!["/d".into(), "/c".into(), script.display().to_string()], dir }
    }

    const READY: &str = r#"echo {"v":1,"event":"ready","pid":1}"#;
    /// cmd's own wait: a child process of the script, which the job holds too.
    const HANG: &str = "ping -n 60 127.0.0.1 >nul";

    fn start_mail() -> Command {
        Command::Start { root: None, device: DeviceWant::default(), tasks: vec![TaskSpec::new("ClaimMail".into())] }
    }

    /// The run's messages, as the sink got them.
    fn collect() -> (Arc<Mutex<Vec<Message>>>, Sink) {
        let got = Arc::new(Mutex::new(Vec::new()));
        let sink = got.clone();
        (got, Box::new(move |m| sink.lock().unwrap().push(m)))
    }

    /// Wait until the sink got a message `pick` takes; panics after 10 s.
    fn wait_for(got: &Arc<Mutex<Vec<Message>>>, pick: impl Fn(&Message) -> bool) {
        let end = Instant::now() + Duration::from_secs(10);
        while !got.lock().unwrap().iter().any(&pick) {
            assert!(Instant::now() < end, "never came: {:?}", got.lock().unwrap());
            thread::sleep(Duration::from_millis(20));
        }
    }

    fn the_exit(got: &Arc<Mutex<Vec<Message>>>) -> Message {
        let got = got.lock().unwrap();
        assert_eq!(got.iter().filter(|m| matches!(m, Message::Exit { .. })).count(), 1, "{got:?}");
        got.last().cloned().unwrap()
    }

    #[test]
    fn what_the_runner_left_running_ends_with_it_though_it_holds_the_output() {
        // `start /b` leaves ping running with the script's stdout: the pipe stays open after the script exits
        let spawn = fake("left", &[READY, "start /b ping -n 60 127.0.0.1", r#"echo {"v":1,"event":"end","result":"succeeded"}"#, "exit /b 0"]);
        let (got, sink) = collect();
        let started = Instant::now();
        let run = Run::spawn(&spawn, &start_mail(), STOP_WAIT, sink).unwrap();
        assert!(run.wait(Duration::from_secs(15)));
        assert!(started.elapsed() < Duration::from_secs(15));
        assert!(matches!(the_exit(&got), Message::Exit { code: Some(0), ended: true, .. }));
        let end = Instant::now() + Duration::from_secs(5);
        while run.active() > 0 && Instant::now() < end {
            thread::sleep(Duration::from_millis(20));
        }
        assert_eq!(run.active(), 0, "ping ended with the run");
    }

    #[test]
    fn a_runner_that_ends_after_its_end_event_exits_with_its_code_and_nothing_is_ended() {
        let spawn = fake("ends", &[READY, r#"echo {"v":1,"event":"task","index":0,"entry":"ClaimMail","state":"succeeded"}"#,
            r#"echo {"v":1,"event":"end","result":"succeeded"}"#, "exit /b 0"]);
        let (got, sink) = collect();
        let run = Run::spawn(&spawn, &start_mail(), STOP_WAIT, sink).unwrap();
        assert!(run.wait(Duration::from_secs(10)));
        assert_eq!(the_exit(&got), Message::Exit { code: Some(0), ended: true, tail: vec![] });
        let got = got.lock().unwrap();
        assert!(matches!(got[0], Message::Event(Event::Ready { pid: 1 })), "{got:?}");
        assert!(!got.iter().any(|m| matches!(m, Message::Killed { .. })));
    }

    #[test]
    fn a_runner_that_dies_before_its_end_reports_its_exit_code_and_last_lines() {
        let spawn = fake("crash", &[READY,
            r#"echo {"v":1,"event":"log","t":"10:00:00.000","source":"runner","line":"[run] start ClaimMail"}"#,
            "echo Fatal Python error: access violation", "1>&2 echo the traceback", "exit /b 3"]);
        let (got, sink) = collect();
        let run = Run::spawn(&spawn, &start_mail(), STOP_WAIT, sink).unwrap();
        assert!(run.wait(Duration::from_secs(10)));
        let Message::Exit { code, ended, tail } = the_exit(&got) else { unreachable!() };
        assert_eq!((code, ended), (Some(3), false));
        // stdout and stderr are two pipes: their lines keep each pipe's order, not one between them
        for line in ["[run] start ClaimMail", "Fatal Python error: access violation", "the traceback"] {
            assert!(tail.iter().any(|t| t == line), "{line} not in {tail:?}");
        }
        let got = got.lock().unwrap();
        assert!(got.iter().any(|m| matches!(m, Message::Invalid { line, .. } if line == "Fatal Python error: access violation")), "{got:?}");
        assert!(got.iter().any(|m| matches!(m, Message::Output { line } if line == "the traceback")), "{got:?}");
    }

    #[test]
    fn a_runner_that_does_not_end_after_the_stop_has_its_whole_tree_ended() {
        let spawn = fake("hang", &[READY, HANG]);
        let (got, sink) = collect();
        let started = Instant::now();
        let run = Run::spawn(&spawn, &start_mail(), Duration::from_millis(300), sink).unwrap();
        wait_for(&got, |m| matches!(m, Message::Event(Event::Ready { .. })));
        let end = Instant::now() + Duration::from_secs(5);
        while run.active() < 2 {
            assert!(Instant::now() < end, "cmd and its ping are in the job: {}", run.active());
            thread::sleep(Duration::from_millis(20));
        }
        assert!(run.stop());
        assert!(run.wait(Duration::from_secs(10)));
        assert!(started.elapsed() < Duration::from_secs(20), "ended by the job, not by ping's 60 s");
        let got = got.lock().unwrap();
        let kinds: Vec<_> = got.iter().filter(|m| !matches!(m, Message::Event(_))).collect();
        assert!(matches!(kinds[..], [Message::Stopping, Message::Killed { .. }, Message::Exit { ended: false, .. }]), "{kinds:?}");
        let end = Instant::now() + Duration::from_secs(5);
        while run.active() > 0 && Instant::now() < end {
            thread::sleep(Duration::from_millis(20));
        }
        assert_eq!(run.active(), 0, "the script's ping ended with it");
    }

    #[test]
    fn a_runner_that_says_it_cannot_stop_has_its_tree_ended_at_once() {
        let spawn = fake("cannot", &[READY,
            r#"echo {"v":1,"event":"error","kind":"stop_timeout","message":"MaaFramework did not stop in 60 s"}"#, HANG]);
        let (got, sink) = collect();
        let started = Instant::now();
        let run = Run::spawn(&spawn, &start_mail(), STOP_WAIT, sink).unwrap();
        assert!(run.wait(Duration::from_secs(10)));
        assert!(started.elapsed() < Duration::from_secs(20));
        let got = got.lock().unwrap();
        assert!(got.iter().any(|m| matches!(m, Message::Killed { reason } if reason.contains("cannot stop"))), "{got:?}");
    }

    #[test]
    fn a_runner_that_ends_on_the_stop_is_not_ended_by_the_window() {
        // the first `set /p` takes the start line, the second waits for the stop
        let spawn = fake("stops", &[READY, "set /p first=", "set /p second=", r#"echo {"v":1,"event":"end","result":"stopped"}"#, "exit /b 1"]);
        let (got, sink) = collect();
        let run = Run::spawn(&spawn, &start_mail(), Duration::from_millis(1500), sink).unwrap();
        wait_for(&got, |m| matches!(m, Message::Event(Event::Ready { .. })));
        thread::sleep(Duration::from_millis(200)); // the script reads the start line before the stop is there
        assert!(run.stop());
        assert!(run.wait(Duration::from_secs(10)));
        thread::sleep(Duration::from_millis(1600)); // past the stop's wait: an ended run is not ended again
        assert_eq!(the_exit(&got), Message::Exit { code: Some(1), ended: true, tail: vec![] });
        assert!(!got.lock().unwrap().iter().any(|m| matches!(m, Message::Killed { .. })));
        assert!(!run.stop(), "a stop after the end asks nothing");
    }

    #[test]
    fn a_scan_returns_the_devices_its_runner_found() {
        let spawn = fake("scan", &[READY,
            r#"echo {"v":1,"event":"devices","devices":[{"name":"MuMu","address":"127.0.0.1:16384","adb_path":"C:/MuMu/adb.exe","mumu":{"index":0,"manager":"C:/MuMu/MuMuManager.exe","path":"C:/MuMu"}}]}"#,
            r#"echo {"v":1,"event":"end","result":"succeeded"}"#]);
        let found = scan(&spawn, SCAN_WAIT).unwrap();
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].mumu.as_ref().map(|m| m.index), Some(0));
        let broken = fake("scan-broken", &[READY, "1>&2 echo no module named maa", "exit /b 1"]);
        let err = scan(&broken, SCAN_WAIT).unwrap_err();
        assert!(err.contains("no module named maa"), "{err}");
    }

    #[test]
    fn the_runner_runs_on_the_zips_python_else_on_the_python_interface_json_names() {
        let root = scratch("python");
        assert!(python(&root).is_err());
        let venv = root.join("venv").join("python.exe");
        fs::create_dir_all(venv.parent().unwrap()).unwrap();
        fs::write(&venv, "").unwrap();
        fs::write(root.join("interface.json"), format!("// a comment\n{{\"agent\": {{\"child_exec\": {}}}}}\n", Value::from(venv.display().to_string()))).unwrap();
        assert_eq!(python(&root).unwrap(), venv);
        fs::write(root.join("interface.json"), "{\"agent\": {\"child_exec\": \"./venv/python.exe\"}}").unwrap();
        assert_eq!(python(&root).unwrap(), root.join("./venv/python.exe"));
        fs::write(root.join("interface.json"), "{\"agent\": {\"child_exec\": \"python\"}}").unwrap();
        assert!(python(&root).is_err(), "a bare python is no file of the install");
        let bundled = root.join("python").join("python.exe");
        fs::create_dir_all(bundled.parent().unwrap()).unwrap();
        fs::write(&bundled, "").unwrap();
        assert_eq!(python(&root).unwrap(), bundled);
    }
}
