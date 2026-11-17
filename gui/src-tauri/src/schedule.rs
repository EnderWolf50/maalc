//! Scheduled runs (#816, spec #811 「定時執行」): one Windows Task Scheduler task per schedule of the settings file, which
//! starts `maalc-gui.exe --run <id>` as the current user, with limited rights, only while that user is logged on, catching
//! up a time it missed and waking the PC when the schedule says so. A task's name carries the maalc folder's key
//! (`maalc-<key>-<id>`), so two installs never write over each other's tasks. The window brings the tasks in line with the
//! settings file at each start and each save (`sync`): a task that is missing or differs is written again, one whose schedule
//! is gone is deleted, and a task another maalc folder left behind is deleted once its maalc-gui.exe is gone (the folder
//! moved, or was deleted).

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// A schedule of the settings file (agent/settings.schema.json `schedules`).
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct Schedule {
    pub id: String,
    pub days: Vec<String>,
    pub time: String,
    pub wake: bool,
}

/// The settings file's weekdays and the Task Scheduler's names of them, Monday first.
const DAYS: [(&str, &str); 7] = [
    ("mon", "Monday"),
    ("tue", "Tuesday"),
    ("wed", "Wednesday"),
    ("thu", "Thursday"),
    ("fri", "Friday"),
    ("sat", "Saturday"),
    ("sun", "Sunday"),
];

/// What every maalc task's name starts with.
const PREFIX: &str = "maalc-";

/// The text of a path as the key and the tasks take it: no `\\?\` before it, `\` between its parts, no `\` after it.
pub fn plain(path: &Path) -> String {
    let text = path.display().to_string().replace('/', "\\");
    let text = match text.strip_prefix(r"\\?\UNC\") {
        Some(share) => format!(r"\\{share}"),
        None => text.strip_prefix(r"\\?\").map(str::to_string).unwrap_or(text),
    };
    let trimmed = text.trim_end_matches('\\');
    // a drive's root keeps its \ (D:\)
    if trimmed.ends_with(':') { format!("{trimmed}\\") } else { trimmed.to_string() }
}

/// The path the Task Scheduler and a second start see of `path`: the real one where it exists (a junction resolved, the case
/// the disk has), as plain text.
pub fn real(path: &Path) -> PathBuf {
    PathBuf::from(plain(&std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf())))
}

/// FNV-1a, 64 bits: the same text gives the same number on every build (Rust's own hasher promises no such thing).
fn fnv1a(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf2_9ce4_8422_2325, |h, b| (h ^ u64::from(*b)).wrapping_mul(0x0100_0000_01b3))
}

/// The key of a maalc folder: 8 hex digits of its path, its case ignored as Windows ignores it. The single-instance lock and
/// the task names use it (spec #811: a schedule belongs to one folder).
pub fn folder_key(root: &Path) -> String {
    let h = fnv1a(plain(root).to_lowercase().as_bytes());
    format!("{:08x}", (h ^ (h >> 32)) as u32)
}

/// What the names of this folder's tasks start with.
pub fn task_prefix(root: &Path) -> String {
    format!("{PREFIX}{}-", folder_key(root))
}

/// Whether a schedule id can be a task name's part and a command line argument as it is.
fn usable_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 64 && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&apos;")
}

fn unescape(text: &str) -> String {
    text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&apos;", "'").replace("&amp;", "&")
}

/// Whether `time` is HH:MM, 00:00 to 23:59.
fn clock(time: &str) -> bool {
    let b = time.as_bytes();
    b.len() == 5 && b[2] == b':' && b.iter().enumerate().all(|(i, c)| i == 2 || c.is_ascii_digit())
        && &time[..2] < "24" && &time[3..] < "60"
}

/// The task of a schedule, as the XML the Task Scheduler registers: `exe --run <id>` from `root`, weekly on its days at its
/// time, catching up a missed time (StartWhenAvailable), waking the PC when it says so (WakeToRun), as the user who registers
/// it while logged on (InteractiveToken) with limited rights (LeastPrivilege), on battery too, at normal priority (the
/// Task Scheduler's 7 runs it and the emulator it starts below normal), with no time limit (a run can take hours), and a
/// start beside one still running (Parallel: the window that one opened may still be open, and takes the run itself).
pub fn task_xml(s: &Schedule, exe: &Path, root: &Path) -> Result<String, String> {
    if !usable_id(&s.id) {
        return Err(format!("schedule id '{}': a task name takes letters, digits, - and _ only", s.id));
    }
    if !clock(&s.time) {
        return Err(format!("schedule {}: time '{}' is not HH:MM", s.id, s.time));
    }
    let mut days = String::new();
    for (key, name) in DAYS {
        if s.days.iter().any(|d| d == key) {
            days.push_str(&format!("<{name} />"));
        }
    }
    if days.is_empty() || s.days.iter().any(|d| !DAYS.iter().any(|(k, _)| k == d)) {
        return Err(format!("schedule {}: days {:?} are not one or more of mon to sun", s.id, s.days));
    }
    let (exe, root) = (escape(&plain(exe)), escape(&plain(root)));
    Ok(format!(
        r#"<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>maalc: runs the task list of {root} (schedule {id})</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2020-01-01T{time}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>{days}</DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>{wake}</WakeToRun>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{exe}"</Command>
      <Arguments>--run {id}</Arguments>
      <WorkingDirectory>{root}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"#,
        id = s.id,
        time = s.time,
        wake = s.wake,
    ))
}

/// The part of `xml` inside the first `<tag>` (its attributes allowed) and its `</tag>`; "" for a `<tag />`.
fn inside<'a>(xml: &'a str, tag: &str) -> Option<&'a str> {
    let open = format!("<{tag}");
    let mut from = 0;
    while let Some(at) = xml[from..].find(&open) {
        let start = from + at + open.len();
        let rest = &xml[start..];
        match rest.chars().next() {
            Some('>') => {
                let body = &rest[1..];
                return body.find(&format!("</{tag}>")).map(|end| &body[..end]);
            }
            Some(c) if c.is_whitespace() || c == '/' => {
                let close = rest.find('>')?;
                if rest[..close].trim_end().ends_with('/') {
                    return Some("");
                }
                let body = &rest[close + 1..];
                return body.find(&format!("</{tag}>")).map(|end| &body[..end]);
            }
            _ => from = start, // a longer tag that starts the same (<Enabled> in <EnabledX>)
        }
    }
    None
}

/// The text of `<tag>` in `xml`, unescaped and trimmed; `default` when it is not there (the Task Scheduler leaves out a
/// setting at its default when it hands a task back).
fn value(xml: &str, tag: &str, default: &str) -> String {
    inside(xml, tag).map(|v| unescape(v.trim())).unwrap_or_else(|| default.to_string())
}

/// What a task does, by the fields this module writes, read the same way from the XML it writes and from the XML the Task
/// Scheduler hands back of a task (which orders them its own way and leaves out the ones at their default): two that are equal
/// do the same. Paths are lower case, as Windows compares them.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Shape {
    pub command: String,
    pub arguments: String,
    pub dir: String,
    pub actions: usize,
    pub triggers: usize,
    pub trigger_on: bool,
    pub time: String,
    pub days: BTreeSet<String>,
    pub weeks: String,
    pub logon: String,
    pub level: String,
    pub wake: bool,
    pub catch_up: bool,
    pub enabled: bool,
    pub battery_start: bool,
    pub battery_stop: bool,
    pub instances: String,
    pub limit: String,
    pub priority: String,
}

/// The shape of a task's XML.
pub fn shape(xml: &str) -> Shape {
    let triggers = inside(xml, "Triggers").unwrap_or("");
    let settings = inside(xml, "Settings").unwrap_or("");
    let actions = inside(xml, "Actions").unwrap_or("");
    let exec = inside(actions, "Exec").unwrap_or("");
    let principal = inside(xml, "Principal").unwrap_or("");
    let week = inside(triggers, "DaysOfWeek").unwrap_or("");
    let boundary = value(triggers, "StartBoundary", "");
    let on = |text: &str, tag: &str, default: &str| value(text, tag, default).eq_ignore_ascii_case("true");
    Shape {
        command: value(exec, "Command", "").trim_matches('"').to_lowercase(),
        arguments: value(exec, "Arguments", ""),
        dir: value(exec, "WorkingDirectory", "").trim_matches('"').to_lowercase(),
        actions: actions.matches("</Exec>").count() + actions.matches("</ComHandler>").count() + actions.matches("</SendEmail>").count()
            + actions.matches("</ShowMessage>").count(),
        // each closing </...Trigger>, and each <...Trigger />
        triggers: triggers.split("</").skip(1).filter(|t| t.split('>').next().is_some_and(|n| n.ends_with("Trigger"))).count()
            + triggers.matches("Trigger />").count(),
        trigger_on: on(triggers, "Enabled", "true"),
        time: boundary.split('T').nth(1).map(|t| t.chars().take(5).collect()).unwrap_or_default(),
        days: DAYS.iter().filter(|(_, name)| inside(week, name).is_some()).map(|(key, _)| key.to_string()).collect(),
        weeks: value(triggers, "WeeksInterval", "1"),
        logon: value(principal, "LogonType", ""),
        level: value(principal, "RunLevel", "LeastPrivilege"),
        wake: on(settings, "WakeToRun", "false"),
        catch_up: on(settings, "StartWhenAvailable", "false"),
        enabled: on(settings, "Enabled", "true"),
        battery_start: on(settings, "DisallowStartIfOnBatteries", "true"),
        battery_stop: on(settings, "StopIfGoingOnBatteries", "true"),
        instances: value(settings, "MultipleInstancesPolicy", "IgnoreNew"),
        limit: value(settings, "ExecutionTimeLimit", "PT72H"),
        priority: value(settings, "Priority", "7"),
    }
}

/// The tasks of the Task Scheduler's root folder, as the sync reaches them (the system's, `TaskService`; a fake in the tests).
pub trait Scheduler {
    /// The names of the tasks in the root folder.
    fn names(&self) -> Result<Vec<String>, String>;
    /// A task's XML, None when there is no such task.
    fn xml(&self, name: &str) -> Result<Option<String>, String>;
    /// Register a task, written over one of that name.
    fn register(&self, name: &str, xml: &str) -> Result<(), String>;
    fn delete(&self, name: &str) -> Result<(), String>;
}

/// What a sync did: the task names it wrote, kept as they were and deleted, and what it could not do. `prefix` is what this
/// folder's task names start with.
#[derive(Serialize, Debug, Default, Clone, PartialEq)]
pub struct Synced {
    pub prefix: String,
    pub written: Vec<String>,
    pub kept: Vec<String>,
    pub deleted: Vec<String>,
    pub errors: Vec<String>,
}

/// Whether `name` is a maalc task of another folder: `maalc-`, a key of 8 hex digits, `-`.
fn other_install(name: &str, prefix: &str) -> bool {
    let Some(rest) = name.strip_prefix(PREFIX) else { return false };
    let key = rest.get(..8).unwrap_or("");
    !name.starts_with(prefix) && key.len() == 8 && key.chars().all(|c| c.is_ascii_hexdigit()) && rest[8..].starts_with('-')
}

/// Bring the tasks of the folder `root` in line with its settings' `schedules`, each to start `exe`: a task that is missing or
/// does something else is written again, a task of this folder whose schedule is gone is deleted. A task of another maalc
/// folder whose program `exists` says is gone (that folder moved or was deleted) is deleted too; one whose program is there
/// is another install's, and stays. A schedule that cannot be a task (a hand-edited id, time or days) is left out with why,
/// and a task of its id stays as it was.
pub fn sync(tasks: &dyn Scheduler, schedules: &[Schedule], exe: &Path, root: &Path, exists: &dyn Fn(&Path) -> bool) -> Result<Synced, String> {
    let prefix = task_prefix(root);
    let names = tasks.names()?;
    let mut done = Synced { prefix: prefix.clone(), ..Synced::default() };
    let mut wanted = BTreeSet::new();
    for s in schedules {
        let name = format!("{prefix}{}", s.id);
        if usable_id(&s.id) && !wanted.insert(name.clone()) {
            done.errors.push(format!("schedules: id '{}' appears twice: its task is the first one's", s.id));
            continue;
        }
        let xml = match task_xml(s, exe, root) {
            Ok(xml) => xml,
            Err(e) => {
                done.errors.push(e);
                continue;
            }
        };
        let same = names.contains(&name) && matches!(tasks.xml(&name), Ok(Some(now)) if shape(&now) == shape(&xml));
        if same {
            done.kept.push(name);
            continue;
        }
        match tasks.register(&name, &xml) {
            Ok(()) => done.written.push(name),
            Err(e) => done.errors.push(format!("{name}: {e}")),
        }
    }
    for name in &names {
        let gone = if name.starts_with(&prefix) {
            !wanted.contains(name)
        } else if other_install(name, &prefix) {
            // a program path the text could not hold reads with '?', which no real path has: never taken for gone
            match tasks.xml(name) {
                Ok(Some(xml)) => {
                    let command = shape(&xml).command;
                    !command.is_empty() && !command.contains('?') && !exists(Path::new(&command))
                }
                _ => false,
            }
        } else {
            false
        };
        if gone {
            match tasks.delete(name) {
                Ok(()) => done.deleted.push(name.clone()),
                Err(e) => done.errors.push(format!("{name}: {e}")),
            }
        }
    }
    Ok(done)
}

/// The id after `--run` in a start's arguments (the first is the program), if any.
pub fn run_arg(args: &[String]) -> Option<String> {
    let at = args.iter().skip(1).position(|a| a == "--run")? + 1;
    args.get(at + 1).filter(|id| !id.is_empty() && !id.starts_with("--")).cloned()
}

// ---- the system's Task Scheduler ----

/// The Task Scheduler's root folder through its COM interface (taskschd.dll): Unicode both ways, where `schtasks` hands its
/// output back in the console's code page.
#[cfg(windows)]
pub struct TaskService {
    folder: Option<windows::Win32::System::TaskScheduler::ITaskFolder>,
    uninit: bool,
}

#[cfg(windows)]
impl TaskService {
    pub fn connect() -> Result<TaskService, String> {
        use windows::Win32::System::Com::{CoCreateInstance, CoInitializeEx, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED};
        use windows::Win32::System::TaskScheduler::{ITaskService, TaskScheduler};
        use windows::Win32::System::Variant::VARIANT;
        let e = |what: &str, err: windows::core::Error| format!("Task Scheduler: {what}: {}", err.message());
        // S_OK or S_FALSE (already on this thread) take a CoUninitialize each; another threading model on this thread is
        // used as it is
        let uninit = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) }.is_ok();
        let mut service = TaskService { folder: None, uninit };
        let tasks: ITaskService = unsafe { CoCreateInstance(&TaskScheduler, None, CLSCTX_INPROC_SERVER) }.map_err(|x| e("start", x))?;
        let none = VARIANT::default();
        unsafe { tasks.Connect(&none, &none, &none, &none) }.map_err(|x| e("connect", x))?;
        service.folder = Some(unsafe { tasks.GetFolder(&"\\".into()) }.map_err(|x| e("root folder", x))?);
        Ok(service)
    }

    fn folder(&self) -> &windows::Win32::System::TaskScheduler::ITaskFolder {
        self.folder.as_ref().expect("connected")
    }
}

#[cfg(windows)]
impl Drop for TaskService {
    fn drop(&mut self) {
        self.folder = None; // released before COM ends on this thread
        if self.uninit {
            unsafe { windows::Win32::System::Com::CoUninitialize() };
        }
    }
}

#[cfg(windows)]
impl Scheduler for TaskService {
    fn names(&self) -> Result<Vec<String>, String> {
        use windows::Win32::System::TaskScheduler::TASK_ENUM_HIDDEN;
        use windows::Win32::System::Variant::VARIANT;
        let e = |err: windows::core::Error| format!("Task Scheduler: list the tasks: {}", err.message());
        let all = unsafe { self.folder().GetTasks(TASK_ENUM_HIDDEN.0) }.map_err(e)?;
        let n = unsafe { all.Count() }.map_err(e)?;
        let mut names = Vec::new();
        for i in 1..=n {
            let task = unsafe { all.get_Item(&VARIANT::from(i)) }.map_err(e)?;
            names.push(unsafe { task.Name() }.map_err(e)?.to_string());
        }
        Ok(names)
    }

    fn xml(&self, name: &str) -> Result<Option<String>, String> {
        let task = match unsafe { self.folder().GetTask(&name.into()) } {
            Ok(task) => task,
            Err(_) => return Ok(None), // no such task (ERROR_FILE_NOT_FOUND)
        };
        unsafe { task.Xml() }.map(|x| Some(x.to_string())).map_err(|err| format!("Task Scheduler: read {name}: {}", err.message()))
    }

    fn register(&self, name: &str, xml: &str) -> Result<(), String> {
        use windows::Win32::System::TaskScheduler::{TASK_CREATE_OR_UPDATE, TASK_LOGON_INTERACTIVE_TOKEN};
        use windows::Win32::System::Variant::VARIANT;
        let none = VARIANT::default();
        unsafe { self.folder().RegisterTask(&name.into(), &xml.into(), TASK_CREATE_OR_UPDATE.0, &none, &none, TASK_LOGON_INTERACTIVE_TOKEN, &none) }
            .map(|_| ())
            .map_err(|err| format!("Task Scheduler: register: {}", err.message()))
    }

    fn delete(&self, name: &str) -> Result<(), String> {
        unsafe { self.folder().DeleteTask(&name.into(), 0) }.map_err(|err| format!("Task Scheduler: delete: {}", err.message()))
    }
}

/// Off Windows there is no Task Scheduler (not a target maalc ships for).
#[cfg(not(windows))]
pub struct TaskService;

#[cfg(not(windows))]
impl TaskService {
    pub fn connect() -> Result<TaskService, String> {
        Err("the Task Scheduler is Windows only".into())
    }
}

#[cfg(not(windows))]
impl Scheduler for TaskService {
    fn names(&self) -> Result<Vec<String>, String> {
        Ok(vec![])
    }
    fn xml(&self, _name: &str) -> Result<Option<String>, String> {
        Ok(None)
    }
    fn register(&self, _name: &str, _xml: &str) -> Result<(), String> {
        Err("the Task Scheduler is Windows only".into())
    }
    fn delete(&self, _name: &str) -> Result<(), String> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::collections::BTreeMap;

    fn every(days: &[&str], time: &str, wake: bool) -> Schedule {
        Schedule { id: "s1".into(), days: days.iter().map(|d| d.to_string()).collect(), time: time.into(), wake }
    }

    const EXE: &str = r"D:\Games & Tools\maalc\maalc-gui.exe";
    const ROOT: &str = r"D:\Games & Tools\maalc";

    #[test]
    fn a_schedules_task_runs_the_window_on_its_days_and_time_as_the_user_logged_on() {
        let xml = task_xml(&every(&["mon", "wed", "sun"], "05:10", true), Path::new(EXE), Path::new(ROOT)).unwrap();
        let got = shape(&xml);
        assert_eq!(got.days, ["mon", "wed", "sun"].iter().map(|d| d.to_string()).collect::<BTreeSet<_>>());
        assert_eq!((got.time.as_str(), got.weeks.as_str(), got.triggers, got.trigger_on), ("05:10", "1", 1, true));
        assert!(got.wake, "it wakes the PC");
        assert!(got.catch_up, "a missed time runs once the PC is on (StartWhenAvailable)");
        assert_eq!((got.logon.as_str(), got.level.as_str()), ("InteractiveToken", "LeastPrivilege"), "logged on, limited rights");
        assert_eq!(got.command, EXE.to_lowercase());
        assert_eq!(got.arguments, "--run s1");
        assert_eq!(got.dir, ROOT.to_lowercase());
        assert_eq!(got.actions, 1);
        assert!(got.enabled && !got.battery_start && !got.battery_stop, "it starts and keeps running on battery");
        assert_eq!((got.instances.as_str(), got.limit.as_str(), got.priority.as_str()), ("Parallel", "PT0S", "4"));
        // the & of the folder is escaped in the XML, and the program's path is quoted
        assert!(xml.contains(r#"<Command>"D:\Games &amp; Tools\maalc\maalc-gui.exe"</Command>"#), "{xml}");
        assert!(xml.contains("<DaysOfWeek><Monday /><Wednesday /><Sunday /></DaysOfWeek>"), "{xml}");
        assert!(xml.contains("<StartBoundary>2020-01-01T05:10:00</StartBoundary>"), "{xml}");
    }

    #[test]
    fn a_schedule_that_does_not_wake_the_pc_says_so() {
        let xml = task_xml(&every(&["fri"], "21:00", false), Path::new(EXE), Path::new(ROOT)).unwrap();
        assert!(xml.contains("<WakeToRun>false</WakeToRun>"), "{xml}");
        assert!(!shape(&xml).wake);
    }

    #[test]
    fn a_schedule_the_task_cannot_hold_is_refused_with_why() {
        let (exe, root) = (Path::new(EXE), Path::new(ROOT));
        let bad = |s: Schedule| task_xml(&s, exe, root).unwrap_err();
        assert!(bad(Schedule { id: "a b".into(), ..every(&["mon"], "05:10", true) }).contains("a b"));
        assert!(bad(Schedule { id: "".into(), ..every(&["mon"], "05:10", true) }).contains("id"));
        assert!(bad(every(&["mon"], "5:10", true)).contains("5:10"));
        assert!(bad(every(&["mon"], "24:00", true)).contains("24:00"));
        assert!(bad(every(&[], "05:10", true)).contains("days"));
        assert!(bad(every(&["mon", "moon"], "05:10", true)).contains("moon"));
    }

    /// A task as the Task Scheduler handed it back (`schtasks /Query /XML` of one this module wrote, 2026-11-17, its user's
    /// SID replaced): its own order, the settings at their default left out.
    const HANDED_BACK: &str = r#"<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>maalc: runs the task list of D:\Games &amp; Tools\maalc (schedule s1)</Description>
    <URI>\maalc-1a2b3c4d-s1</URI>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-1-2-3-1000</UserId>
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <Priority>4</Priority>
    <StartWhenAvailable>true</StartWhenAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2020-01-01T05:10:00</StartBoundary>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday />
          <Friday />
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>"D:\Games &amp; Tools\maalc\maalc-gui.exe"</Command>
      <Arguments>--run s1</Arguments>
      <WorkingDirectory>D:\Games &amp; Tools\maalc</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"#;

    #[test]
    fn a_task_handed_back_in_the_schedulers_own_order_reads_as_the_task_written() {
        let written = task_xml(&every(&["mon", "fri"], "05:10", false), Path::new(EXE), Path::new(ROOT)).unwrap();
        assert_eq!(shape(HANDED_BACK), shape(&written));
        let woken = HANDED_BACK.replace("<StartWhenAvailable>", "<WakeToRun>true</WakeToRun><StartWhenAvailable>");
        assert_ne!(shape(&woken), shape(&written), "wake on reads apart");
        assert_ne!(shape(&HANDED_BACK.replace("<Friday />", "")), shape(&written), "a day less reads apart");
        assert_ne!(shape(&HANDED_BACK.replace("T05:10", "T05:11")), shape(&written), "another time reads apart");
        let disabled = HANDED_BACK.replace("<StartWhenAvailable>", "<Enabled>false</Enabled><StartWhenAvailable>");
        assert_ne!(shape(&disabled), shape(&written), "a task switched off by hand reads apart");
        let second = HANDED_BACK.replace("</CalendarTrigger>", "</CalendarTrigger><LogonTrigger><Enabled>true</Enabled></LogonTrigger>");
        assert_ne!(shape(&second), shape(&written), "a trigger added by hand reads apart");
    }

    #[test]
    fn a_folders_key_ignores_case_and_a_closing_backslash_and_tells_two_folders_apart() {
        let key = folder_key(Path::new(r"D:\maalc"));
        assert_eq!(key.len(), 8);
        assert!(key.chars().all(|c| c.is_ascii_hexdigit()));
        assert_eq!(folder_key(Path::new(r"d:\MAALC\")), key);
        assert_eq!(folder_key(Path::new("D:/maalc")), key);
        assert_eq!(folder_key(Path::new(r"\\?\D:\maalc")), key);
        assert_ne!(folder_key(Path::new(r"D:\maalc2")), key);
        assert_ne!(folder_key(Path::new(r"E:\maalc")), key);
        assert_eq!(task_prefix(Path::new(r"D:\maalc")), format!("maalc-{key}-"));
        assert_eq!(plain(Path::new(r"\\?\UNC\nas\games\maalc")), r"\\nas\games\maalc");
        assert_eq!(plain(Path::new(r"D:\")), r"D:\");
    }

    #[test]
    fn the_run_argument_is_the_id_after_run() {
        let args = |list: &[&str]| list.iter().map(|a| a.to_string()).collect::<Vec<_>>();
        assert_eq!(run_arg(&args(&["maalc-gui.exe", "--run", "s1"])), Some("s1".into()));
        assert_eq!(run_arg(&args(&["maalc-gui.exe"])), None);
        assert_eq!(run_arg(&args(&["maalc-gui.exe", "--run"])), None);
        assert_eq!(run_arg(&args(&["maalc-gui.exe", "--run", "--other"])), None);
        assert_eq!(run_arg(&args(&["--run", "x"])), None, "the program itself is not an argument");
    }

    /// The Task Scheduler's root folder as a map of task name to XML; `fail` names a task whose register fails.
    #[derive(Default)]
    struct Fake {
        tasks: RefCell<BTreeMap<String, String>>,
        writes: RefCell<Vec<String>>,
        fail: Option<String>,
    }

    impl Scheduler for Fake {
        fn names(&self) -> Result<Vec<String>, String> {
            Ok(self.tasks.borrow().keys().cloned().collect())
        }
        fn xml(&self, name: &str) -> Result<Option<String>, String> {
            Ok(self.tasks.borrow().get(name).cloned())
        }
        fn register(&self, name: &str, xml: &str) -> Result<(), String> {
            if self.fail.as_deref() == Some(name) {
                return Err("Access is denied.".into());
            }
            self.writes.borrow_mut().push(name.to_string());
            self.tasks.borrow_mut().insert(name.to_string(), xml.to_string());
            Ok(())
        }
        fn delete(&self, name: &str) -> Result<(), String> {
            self.tasks.borrow_mut().remove(name);
            Ok(())
        }
    }

    fn sched(id: &str, days: &[&str], time: &str) -> Schedule {
        Schedule { id: id.into(), ..every(days, time, true) }
    }

    const A: &str = r"C:\Games\maalc";
    const B: &str = r"D:\maalc";

    fn exe(root: &str) -> PathBuf {
        Path::new(root).join("maalc-gui.exe")
    }

    /// Every program is there but the ones under `gone`.
    fn there_but(gone: &'static str) -> impl Fn(&Path) -> bool {
        move |p: &Path| !p.display().to_string().to_lowercase().starts_with(&gone.to_lowercase())
    }

    #[test]
    fn a_sync_writes_a_missing_task_keeps_one_that_matches_and_rewrites_one_that_differs() {
        let fake = Fake::default();
        let list = [sched("s1", &["mon"], "05:10"), sched("s2", &["sat", "sun"], "21:00")];
        let done = sync(&fake, &list, &exe(A), Path::new(A), &|_| true).unwrap();
        let prefix = task_prefix(Path::new(A));
        assert_eq!(done.written, [format!("{prefix}s1"), format!("{prefix}s2")]);
        assert!(done.errors.is_empty(), "{:?}", done.errors);
        let task = shape(&fake.tasks.borrow()[&format!("{prefix}s2")]);
        assert_eq!((task.time.as_str(), task.arguments.as_str()), ("21:00", "--run s2"));

        fake.writes.borrow_mut().clear();
        let again = sync(&fake, &list, &exe(A), Path::new(A), &|_| true).unwrap();
        assert_eq!(again.kept.len(), 2);
        assert!(fake.writes.borrow().is_empty(), "a task as the settings say is not written again");

        let moved = [sched("s1", &["mon"], "06:00"), list[1].clone()];
        let changed = sync(&fake, &moved, &exe(A), Path::new(A), &|_| true).unwrap();
        assert_eq!(changed.written, [format!("{prefix}s1")]);
        assert_eq!(shape(&fake.tasks.borrow()[&format!("{prefix}s1")]).time, "06:00");
    }

    #[test]
    fn a_task_edited_by_hand_is_written_back_as_the_settings_say() {
        let fake = Fake::default();
        let list = [sched("s1", &["mon"], "05:10")];
        sync(&fake, &list, &exe(A), Path::new(A), &|_| true).unwrap();
        let name = format!("{}s1", task_prefix(Path::new(A)));
        let edited = fake.tasks.borrow()[&name].replace(r#"<Command>"#, r#"<Command>"C:\elsewhere\x.exe"</Command><Old>"#);
        fake.tasks.borrow_mut().insert(name.clone(), edited);
        let done = sync(&fake, &list, &exe(A), Path::new(A), &|_| true).unwrap();
        assert_eq!(done.written, [name.clone()]);
        assert_eq!(shape(&fake.tasks.borrow()[&name]).command, exe(A).display().to_string().to_lowercase());
    }

    #[test]
    fn a_deleted_schedule_deletes_its_task_and_leaves_other_tasks_alone() {
        let fake = Fake::default();
        fake.tasks.borrow_mut().insert("Hermes_Gateway".into(), "<Task />".into());
        sync(&fake, &[sched("s1", &["mon"], "05:10"), sched("s2", &["tue"], "05:10")], &exe(A), Path::new(A), &|_| true).unwrap();
        let done = sync(&fake, &[sched("s2", &["tue"], "05:10")], &exe(A), Path::new(A), &|_| true).unwrap();
        let prefix = task_prefix(Path::new(A));
        assert_eq!(done.deleted, [format!("{prefix}s1")]);
        assert_eq!(fake.names().unwrap(), ["Hermes_Gateway".to_string(), format!("{prefix}s2")]);
        let none = sync(&fake, &[], &exe(A), Path::new(A), &|_| true).unwrap();
        assert_eq!(none.deleted, [format!("{prefix}s2")]);
        assert_eq!(fake.names().unwrap(), ["Hermes_Gateway"]);
    }

    #[test]
    fn after_the_folder_moved_its_tasks_start_the_window_in_the_new_folder_and_the_old_ones_go() {
        let fake = Fake::default();
        let list = [sched("s1", &["mon"], "05:10"), sched("s2", &["sat"], "09:00")];
        sync(&fake, &list, &exe(A), Path::new(A), &|_| true).unwrap();
        // the folder moved from A to B: A's maalc-gui.exe is gone, and the window opens from B
        let done = sync(&fake, &list, &exe(B), Path::new(B), &there_but(A)).unwrap();
        let (old, new) = (task_prefix(Path::new(A)), task_prefix(Path::new(B)));
        assert_eq!(done.written, [format!("{new}s1"), format!("{new}s2")]);
        assert_eq!(done.deleted, [format!("{old}s1"), format!("{old}s2")]);
        assert_eq!(fake.names().unwrap(), [format!("{new}s1"), format!("{new}s2")]);
        for name in fake.names().unwrap() {
            let task = shape(&fake.tasks.borrow()[&name]);
            assert_eq!(task.command, exe(B).display().to_string().to_lowercase());
            assert_eq!(task.dir, B.to_lowercase());
        }
    }

    #[test]
    fn another_installs_tasks_stay_while_its_program_is_there() {
        let fake = Fake::default();
        sync(&fake, &[sched("s1", &["mon"], "05:10")], &exe(A), Path::new(A), &|_| true).unwrap();
        let done = sync(&fake, &[sched("s1", &["tue"], "06:00")], &exe(B), Path::new(B), &|_| true).unwrap();
        assert!(done.deleted.is_empty());
        let a = shape(&fake.tasks.borrow()[&format!("{}s1", task_prefix(Path::new(A)))]);
        let b = shape(&fake.tasks.borrow()[&format!("{}s1", task_prefix(Path::new(B)))]);
        assert_eq!((a.time.as_str(), b.time.as_str()), ("05:10", "06:00"), "two installs keep a task each");
        // a task named like ours whose path cannot be read (?) or that is not a maalc key is never taken for gone
        let lossy = HANDED_BACK.replace(r"D:\Games &amp; Tools", r"D:\??");
        fake.tasks.borrow_mut().insert("maalc-0badf00d-s9".into(), lossy);
        fake.tasks.borrow_mut().insert("maalc-notes".into(), HANDED_BACK.into());
        let done = sync(&fake, &[sched("s1", &["tue"], "06:00")], &exe(B), Path::new(B), &|_| false).unwrap();
        assert_eq!(done.deleted, [format!("{}s1", task_prefix(Path::new(A)))]);
        assert!(fake.names().unwrap().contains(&"maalc-0badf00d-s9".to_string()));
        assert!(fake.names().unwrap().contains(&"maalc-notes".to_string()));
    }

    #[test]
    fn a_schedule_that_cannot_be_a_task_says_why_and_its_task_stays() {
        let fake = Fake::default();
        sync(&fake, &[sched("s1", &["mon"], "05:10")], &exe(A), Path::new(A), &|_| true).unwrap();
        let list = [sched("s1", &["mon"], "5:10"), sched("a b", &["mon"], "05:10"), sched("s2", &["mon"], "05:10"), sched("s2", &["tue"], "05:10")];
        let done = sync(&fake, &list, &exe(A), Path::new(A), &|_| true).unwrap();
        assert_eq!(done.errors.len(), 3, "{:?}", done.errors);
        assert!(done.errors[0].contains("5:10") && done.errors[1].contains("a b") && done.errors[2].contains("twice"), "{:?}", done.errors);
        assert!(done.deleted.is_empty(), "s1's task stays as it was");
        assert_eq!(shape(&fake.tasks.borrow()[&format!("{}s2", task_prefix(Path::new(A)))]).days, BTreeSet::from(["mon".to_string()]));
    }

    /// The system's Task Scheduler, by hand only (`cargo test --lib -- --ignored`): it writes a real task, which a CI runner
    /// must not, and deletes it again.
    #[cfg(windows)]
    #[test]
    #[ignore]
    fn the_system_task_scheduler_takes_a_task_hands_it_back_as_written_and_deletes_it() {
        let root = std::env::temp_dir().join("maalc-gui-schedule-probe");
        let tasks = TaskService::connect().unwrap();
        let list = [Schedule { id: "probe".into(), ..every(&["mon", "fri"], "05:10", false) }];
        let exe = root.join("maalc-gui.exe");
        let done = sync(&tasks, &list, &exe, &root, &|_| true).unwrap();
        let name = format!("{}probe", task_prefix(&root));
        assert_eq!(done.written, [name.clone()], "{done:?}");
        let back = tasks.xml(&name).unwrap().unwrap();
        assert!(tasks.names().unwrap().contains(&name));
        assert_eq!(shape(&back), shape(&task_xml(&list[0], &exe, &root).unwrap()), "{back}");
        let again = sync(&tasks, &list, &exe, &root, &|_| true).unwrap();
        assert_eq!(again.kept, [name.clone()], "{again:?}");
        let gone = sync(&tasks, &[], &exe, &root, &|_| true).unwrap();
        assert_eq!(gone.deleted, [name.clone()]);
        assert_eq!(tasks.xml(&name).unwrap(), None);
    }

    #[test]
    fn a_task_the_scheduler_refuses_is_named_with_why_and_the_rest_are_written() {
        let prefix = task_prefix(Path::new(A));
        let fake = Fake { fail: Some(format!("{prefix}s1")), ..Fake::default() };
        let done = sync(&fake, &[sched("s1", &["mon"], "05:10"), sched("s2", &["tue"], "05:10")], &exe(A), Path::new(A), &|_| true).unwrap();
        assert_eq!(done.written, [format!("{prefix}s2")]);
        assert_eq!(done.errors, [format!("{prefix}s1: Access is denied.")]);
    }
}
