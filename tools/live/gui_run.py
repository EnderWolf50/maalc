"""A live run from the settings window: the window on an install as it is, a recording of that one window, and Start, Stop
and the run's state over its DevTools port.

    uv run python tools/live/gui_run.py <command> ...

  open   --root DIR [--port N] [--data DIR] [--title T] [--timeout S]
  windows SUBSTR
  title  --hwnd H --title T
  record (--hwnd H | --window SUBSTR) --out DIR [--wait S] [--profile P] [--crop-top N] [--height N] [--keep-gb N]
  start  --port N
  stop   --port N [--root DIR --on TEXT [--delay S] [--limit S]]
  state  --port N [--until PHASE[,PHASE...]] [--timeout S]

**open** starts DIR's own `maalc-gui.exe` on DIR's own settings, unlike `tools/gui_devtools.mjs open`, which lays a
throwaway root out again with demo settings. DIR is an install: a worktree's `install/` from `tools/install.py`, its
settings from `tools/live/bot.py prep`; the main checkout's `install/` is refused, since Start saves the settings file.
The window gets a DevTools port (a free one unless --port) and a WebView2 data folder of its own (--data, default
`<local>/scratch/gui-webview2/<port>`), as gui_devtools does. Once the page has drawn, the window's title "maalc" is
set to --title (default `maalc-live-<port>`), a title no other window holds: screen-record's `--window` takes the
largest window whose title holds its substring, and "maalc" alone is also in other windows' titles (an editor, the agent's
own). It prints {"pid", "hwnd", "port", "title", "data", "viewport"} and holds, in the background: the app ends with
this process (a Windows job), and this process ends with the app.

**windows** lists the visible top-level windows whose title holds SUBSTR, case-insensitive, as screen-record matches
them: hwnd, pid, process, size, minimised, and the title only when it is SUBSTR exactly (another title can name the
user's own work).

**title** sets the title of window H, which must be "maalc" now, and checks no other visible window then holds the new one.

**record** runs screen-record's `start` on one window and refuses when more than one visible window matches:
`--hwnd H` records that window by its title (from **open**, or **title**), `--window SUBSTR` the one window that holds
SUBSTR (MuMu's "Android Device"). `--wait S` waits up to S seconds for the window to appear (MuMu starts when the run
does). After the start it reads the recording's state file: a recording of another window is stopped, exit 1. The other
options go to screen-record as they are; `--height` defaults to 720 (the maalc-live-test skill, step 5).

**start** presses the Run tab's Start, which saves the settings first, and waits until the run is under way.
**stop** presses Stop. With `--root DIR --on TEXT` it first waits for TEXT in the run's log under
`DIR/logs/runner/` (the newest log when a run is under way, else the next new one), then --delay seconds (default 0);
a run that ends first, or a --limit (default 600 s) that passes, is exit 1. **state** prints the status line, the phase
(idle, running, stopping, ended), the run's tasks (id, name, reason and state: pending, running, succeeded, failed,
stopped, cancelled) read from the task list's rows, and the page's alerts as JSON; `--until` waits for one of those
phases (--timeout, default 600 s; exit 1 when it passes).
The page commands go through `tools/gui_devtools.mjs` on the port open printed. Windows only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from local_dir import local_dir, main_checkout  # noqa: E402

REPO = TOOLS.parent
DEVTOOLS = TOOLS / "gui_devtools.mjs"
SCREENREC = Path.home() / ".claude" / "skills" / "screen-record" / "scripts" / "screenrec.py"
APP = "maalc-gui.exe"
APP_TITLE = "maalc"  # gui/src-tauri/tauri.conf.json app.windows[0].title; the app never sets it again
PHASES = ("idle", "running", "stopping", "ended")
UNDER_WAY = {"running", "stopping"}
START = ".runner-bar button.primary"
STOP = "js:document.querySelectorAll('.runner-bar button')[1]"
RUN_END = "[run] end "  # runner/session.py: the run's last line
# The Run tab's state, from the page (gui/src/Run.tsx RunControls, TaskList, RunLog). `rows` is every row of the task list
# with the run's state the page writes on it (data-state, absent before a run, "off" on a row the run left out) and its
# task id (data-task); run_tasks() keeps the run's. A row's reason is the English one as the bot and the runner wrote it:
# a coded reason's tooltip, under the sentence the row shows in the window's language (#881). One markup wide and narrow: the run console is drawn in one place or the
# other, with the same classes.
STATE_JS = """(() => { const s = document.querySelector(".runner-status");
  if (!s) return null;
  const text = (el) => el ? el.textContent.trim() : null;
  const english = (el) => el && el.title ? el.title : text(el);
  return { phase: s.dataset.phase, status: text(s),
    rows: [...document.querySelectorAll(".task-list .task-row")].map((row) => ({ id: row.dataset.task, state: row.dataset.state ?? null,
      name: text(row.querySelector(".tr-name")), reason: english(row.querySelector(".tr-reason")) })),
    start: !document.querySelector(".runner-bar button.primary")?.disabled,
    alerts: [...document.querySelectorAll(".run-notes p, .crash[role=alert]")].map(text) }; })()"""
RENDERED_JS = """(() => { const main = document.querySelector("main");
  if (!main) return null;
  if (main.classList.contains("load-error")) return { loadError: main.innerText.slice(0, 300) };
  return { width: innerWidth, height: innerHeight, dpr: devicePixelRatio }; })()"""


class Refused(Exception):
    """A command that cannot go on, with what to do instead; exit 1."""


class Ambiguous(Refused):
    """More than one window matches: waiting does not make it fewer."""


def say(value) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


# --- windows (pure) -----------------------------------------------------------------------------------------------

def matching(windows: list[dict], substr: str) -> list[dict]:
    """The windows ({hwnd, title, ...}, visible top-level ones) whose title holds substr, case-insensitive: what
    screen-record's `--window` matches."""
    return [w for w in windows if w["title"] and substr.lower() in w["title"].lower()]


def sole(windows: list[dict], substr: str) -> dict:
    """The one window whose title holds substr; Refused when none or several do (screen-record would take the largest)."""
    found = matching(windows, substr)
    if len(found) == 1:
        return found[0]
    if not found:
        raise Refused(f"no visible window has {substr!r} in its title")
    raise Ambiguous(f"{len(found)} visible windows have {substr!r} in their title (hwnd {', '.join(str(w['hwnd']) for w in found)}): "
                  "screen-record would take the largest. Give the window a title of its own (`title`), or close the others")


def listing(windows: list[dict], substr: str) -> list[dict]:
    """The `windows` rows: no title but an exact match's, since another title can name the user's own work."""
    return [{"hwnd": w["hwnd"], "pid": w["pid"], "process": w.get("process"), "size": [w["w"], w["h"]],
             "minimised": w["iconic"], **({"title": w["title"]} if w["title"].lower() == substr.lower() else {})}
            for w in matching(windows, substr)]


def default_title(port: int) -> str:
    return f"maalc-live-{port}"


# --- the run log (pure) -------------------------------------------------------------------------------------------

def run_logs(folder: Path) -> list[Path]:
    """The runner's logs in folder, oldest first (runner/runlog.py names them run-YYYYmmdd-HHMMSS[-n].log); one the
    runner prunes meanwhile (it keeps 30) is left out."""
    stamped = []
    for p in folder.glob("run-*.log"):
        try:
            stamped.append((p.stat().st_mtime_ns, p.name, p))
        except FileNotFoundError:
            pass
    return [p for *_, p in sorted(stamped)]


def watched_log(folder: Path, before: set[str], under_way: bool) -> Path | None:
    """The log a run writes: the newest when a run was under way as the watch began, else the first one not in before."""
    logs = run_logs(folder)
    if under_way:
        return logs[-1] if logs else None
    new = [p for p in logs if p.name not in before]
    return new[0] if new else None


def seen(text: str, needle: str) -> str | None:
    """"line" when needle is on a line of text, "ended" when the run's end line comes before any such line, else None."""
    for line in text.splitlines():
        if needle in line:
            return "line"
        if RUN_END in line:
            return "ended"
    return None


# --- Win32 --------------------------------------------------------------------------------------------------------

def _user32():
    import ctypes

    u = ctypes.windll.user32
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # client sizes in physical pixels, as screen-record reads them
    return u


def top_windows() -> list[dict]:
    """[{hwnd, pid, title, w, h, iconic}] of the visible top-level windows with a title, as screen-record enumerates them."""
    import ctypes
    from ctypes import wintypes

    u = _user32()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if u.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            u.GetWindowTextW(hwnd, buf, 512)
            if buf.value:
                r, pid = wintypes.RECT(), wintypes.DWORD()
                u.GetClientRect(hwnd, ctypes.byref(r))
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                found.append({"hwnd": hwnd, "pid": pid.value, "title": buf.value, "w": r.right, "h": r.bottom,
                              "iconic": bool(u.IsIconic(hwnd))})
        return True

    u.EnumWindows(visit, 0)
    return found


def window_title(hwnd: int) -> str | None:
    """The title of window hwnd, None when there is no such window."""
    import ctypes

    u = _user32()
    if not u.IsWindow(hwnd):
        return None
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def window_pid(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    pid = wintypes.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def users_window(hwnd: int) -> bool:
    """Whether window hwnd is the user's own settings window: the app running from the main checkout's install/."""
    return window_pid(hwnd) in apps_running(main_checkout() / "install" / APP)


def set_title(hwnd: int, title: str, windows=top_windows) -> None:
    """Window hwnd, titled "maalc" now, titled `title`; Refused when it is not, when it is the user's own settings window, or
    when another window then holds the title."""
    before = window_title(hwnd)
    if before is None:
        raise Refused(f"no window {hwnd}")
    if before != APP_TITLE and before != title:
        raise Refused(f"window {hwnd} is titled {before!r}, not {APP_TITLE!r}: not the settings window")
    if users_window(hwnd):
        raise Refused(f"window {hwnd} is the user's own settings window (the main checkout's install/): not one `open` started")
    if title.lower() == APP_TITLE:
        raise Refused(f"the title {title!r} is the one other windows also hold")
    others = [w for w in matching(windows(), title) if w["hwnd"] != hwnd]
    if others:
        raise Refused(f"{len(others)} other window(s) already hold {title!r} in their title: pick another --title")
    if before != title and not _user32().SetWindowTextW(hwnd, title):
        raise Refused(f"could not set the title of window {hwnd}")
    sole(windows(), title)  # a window that took the title meanwhile


def process_names(pids) -> dict[int, str]:
    """{pid: image name} of the given pids (tasklist)."""
    import csv

    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {int(row[1]): row[0] for row in csv.reader(out.stdout.splitlines())
            if len(row) > 1 and row[1].isdigit() and int(row[1]) in pids}


def apps_running(exe: Path) -> list[int]:
    """The pids of maalc-gui.exe processes running from exe."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        f"@(Get-CimInstance Win32_Process -Filter \"Name='{APP}'\" | ForEach-Object {{ "
                        "[pscustomobject]@{ pid = $_.ProcessId; exe = $_.ExecutablePath } }) | ConvertTo-Json -Compress"],
                       capture_output=True, text=True, encoding="utf-8")
    text = r.stdout.strip()
    rows = json.loads(text) if text else []
    rows = rows if isinstance(rows, list) else [rows]
    want = os.path.normcase(str(exe.resolve()))
    return [row["pid"] for row in rows if row.get("exe") and os.path.normcase(row["exe"]) == want]


def kill_with_me() -> None:
    """Put this process in a job that kills everything in it when its last handle closes: the app started after this, and
    its WebView2, end when this process ends, however it ends (gui_devtools.mjs gets the same from libuv)."""
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("Io", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = ctypes.windll.kernel32
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k.CreateJobObjectW(None, None)
    info = Extended()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (job and k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # JobObjectExtendedLimitInformation
            and k.AssignProcessToJobObject(job, k.GetCurrentProcess())):
        raise Refused(f"could not make the job that ends the app with this process (error {k.GetLastError()})")
    kill_with_me.job = job  # held open for the life of the process


def taskkill(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


# --- the page -----------------------------------------------------------------------------------------------------

def devtools(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    node = shutil.which("node") or "node"
    return subprocess.run([node, str(DEVTOOLS), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=str(REPO))


def evaluate(port: int, expression: str):
    """The page's value of expression, as JSON; RuntimeError when nothing answers on the port."""
    r = devtools("eval", expression, "--port", str(port))
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return json.loads(r.stdout.strip().splitlines()[-1])


def press(port: int, target: str) -> None:
    r = devtools("press", target, "--port", str(port))
    if r.returncode != 0:
        raise Refused(f"the press did not go through: {(r.stderr or r.stdout).strip()}")


def run_tasks(rows: list[dict]) -> list[dict]:
    """The run's tasks from the task list's rows, in the list's order, which is the run's: the page writes a state on each
    row while it shows a run, "off" on a row the run left out (unticked), and none before a run or once an edit ended the
    list's reading with the run."""
    return [r for r in rows if r["state"] not in (None, "off")]


def run_state(port: int) -> dict:
    state = evaluate(port, STATE_JS)
    if state is None:
        raise Refused("the page shows no Run tab runner (.runner-status): open the 執行 tab")
    return {**{k: v for k, v in state.items() if k != "rows"}, "tasks": run_tasks(state["rows"])}


def wait_phase(port: int, phases: set[str], timeout: float, every: float = 0.5, past: dict | None = None) -> dict:
    """The Run tab's state once its phase is one of phases; with `past`, a state equal to it (what the page showed before
    a press: the last run's `ended`) does not count."""
    end = time.monotonic() + timeout
    while True:
        state = run_state(port)
        if state["phase"] in phases and state != past:
            return state
        if time.monotonic() > end:
            raise Refused(f"the run is still {state['phase']!r} after {timeout:g} s ({state['status']})")
        time.sleep(every)


# --- commands -----------------------------------------------------------------------------------------------------

def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_free(port: int) -> bool:
    import socket

    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def check_root(root: Path) -> Path:
    """root's exe; Refused for the main checkout's install/ (Start saves its settings) and a root that is no install."""
    exe = root / APP
    if not exe.is_file():
        raise Refused(f"no {APP} in {root}: build an install (tools/install.py) or pass the folder that holds it")
    if not (root / "config" / "settings.json").is_file():
        raise Refused(f"no config/settings.json in {root}: `tools/live/bot.py prep --install {root}` writes one")
    if root.resolve() == (main_checkout() / "install").resolve():
        raise Refused("the main checkout's install/ is the user's own, and Start saves its settings file: open a worktree's "
                      "install (tools/install.py) with its settings from tools/live/bot.py prep")
    return exe


def open_cmd(a) -> int:
    root = Path(a.root).resolve()
    exe = check_root(root)
    if running := apps_running(exe):
        raise Refused(f"{APP} already runs from {root} (pid {', '.join(map(str, running))}): close it first; two windows on "
                      "one settings file overwrite each other")
    port = a.port or free_port()
    if not port_free(port):
        raise Refused(f"port {port} is in use: pass another --port")
    data = Path(a.data).resolve() if a.data else local_dir("scratch", "gui-webview2", str(port))
    title = a.title or default_title(port)
    kill_with_me()
    env = {**os.environ, "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={port}",
           "WEBVIEW2_USER_DATA_FOLDER": str(data)}
    app = subprocess.Popen([str(exe)], cwd=str(root), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        end = time.monotonic() + a.timeout
        viewport = None
        while viewport is None:
            if app.poll() is not None:
                raise Refused(f"the app exited ({app.returncode}) before its page rendered")
            if time.monotonic() > end:
                raise Refused(f"the page did not render within {a.timeout:g} s on DevTools port {port}")
            try:
                viewport = evaluate(port, RENDERED_JS)
            except (RuntimeError, ValueError):
                viewport = None
            if isinstance(viewport, dict) and viewport.get("loadError"):
                raise Refused(f"the app could not read its settings: {viewport['loadError']}")
            if viewport is None:
                time.sleep(0.2)
        hwnd = next((w["hwnd"] for w in top_windows() if w["pid"] == app.pid and w["title"] == APP_TITLE), None)
        if hwnd is None:
            raise Refused(f"no top-level window titled {APP_TITLE!r} of pid {app.pid}")
        set_title(hwnd, title)
    except BaseException:
        taskkill(app.pid)
        raise
    say({"pid": app.pid, "hwnd": hwnd, "port": port, "title": title, "data": str(data), "viewport": viewport})
    say({"holding": "until stopped (the app ends with this process) or the window closes"})

    def stop(*_):
        taskkill(app.pid)
        say({"stopped": "signal"})
        sys.exit(0)

    for sig in ("SIGINT", "SIGBREAK", "SIGTERM"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), stop)
    code = app.wait()
    say({"exited": code})
    return 0


def windows_cmd(a) -> int:
    rows = listing(top_windows(), a.substr)
    names = process_names({r["pid"] for r in rows})
    for r in rows:
        r["process"] = names.get(r["pid"], "?")
        say(r)
    say({"matches": len(rows)})
    return 0


def title_cmd(a) -> int:
    set_title(a.hwnd, a.title)
    say({"hwnd": a.hwnd, "title": a.title})
    return 0


def screenrec(*args: str) -> subprocess.CompletedProcess:
    if not SCREENREC.is_file():
        raise Refused(f"no {SCREENREC}: the screen-record skill is not installed")
    return subprocess.run(["uv", "run", str(SCREENREC), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def record_cmd(a) -> int:
    end = time.monotonic() + a.wait
    while True:
        try:
            if a.hwnd is not None:
                title = window_title(a.hwnd)
                if title is None:
                    raise Refused(f"no window {a.hwnd}")
                if title.lower() == APP_TITLE:
                    raise Refused(f"window {a.hwnd} is still titled {APP_TITLE!r}, which other windows also hold: "
                                  "give it a title of its own first (`title`, or `open` does it)")
                target = sole(top_windows(), title)
                if target["hwnd"] != a.hwnd:
                    raise Refused(f"the window holding {title!r} is {target['hwnd']}, not {a.hwnd}")
            else:
                title, target = a.window, sole(top_windows(), a.window)
            if target["iconic"] or not (target["w"] and target["h"]):  # screen-record refuses both; MuMu may show so first
                raise Refused(f"window {target['hwnd']} is minimised or has no size: restore it first")
            break
        except Refused as e:
            if isinstance(e, Ambiguous) or a.wait <= 0 or time.monotonic() > end:
                raise
            time.sleep(0.5)
    args = ["start", "--window", title, "--out", a.out, "--profile", a.profile, "--height", str(a.height)]
    if a.crop_top is not None:
        args += ["--crop-top", str(a.crop_top)]
    if a.keep_gb is not None:
        args += ["--keep-gb", str(a.keep_gb)]
    r = screenrec(*args)
    print(r.stdout, end="", flush=True)
    if r.returncode != 0:
        print(r.stderr, end="", file=sys.stderr)
        return r.returncode
    state = json.loads((Path(a.out) / f"rec_{a.profile}.state.json").read_text(encoding="utf-8"))
    if state.get("hwnd") != target["hwnd"]:
        screenrec("stop", "--profile", a.profile)
        raise Refused(f"screen-record took window {state.get('hwnd')}, not {target['hwnd']}: stopped it")
    say({"recording": target["hwnd"], "title": title, "profile": a.profile, "started": state["started"], "mkv": state["mkv"]})
    return 0


def start_cmd(a) -> int:
    state = run_state(a.port)
    if state["phase"] in UNDER_WAY:
        raise Refused(f"a run is already {state['phase']}: {state['status']}")
    if not state["start"]:
        raise Refused(f"Start is disabled: {'; '.join(x for x in state['alerts'] if x) or state['status']}")
    press(a.port, START)
    # the page shows the last run's end until this run's begin comes: that state is not this run's
    say(wait_phase(a.port, UNDER_WAY | {"ended"}, a.timeout, every=0.2, past=state if state["phase"] == "ended" else None))
    return 0


def stop_cmd(a) -> int:
    if a.on:
        if not a.root:
            raise Refused("--on reads the run's log: pass --root, the install the window runs from")
        folder = Path(a.root) / "logs" / "runner"
        before = {p.name for p in folder.glob("run-*.log")}
        under_way = run_state(a.port)["phase"] in UNDER_WAY
        end = time.monotonic() + a.limit
        say({"watching": str(folder), "for": a.on, "log": "the newest" if under_way else "the next new one"})
        log = None
        while log is None:
            if time.monotonic() > end:
                raise Refused(f"no run log in {folder} within {a.limit:g} s")
            log = watched_log(folder, before, under_way)
            if log is None:
                time.sleep(0.1)
        say({"log": log.name})
        while (hit := seen(log.read_text(encoding="utf-8", errors="replace"), a.on)) is None:
            if time.monotonic() > end:
                raise Refused(f"{a.on!r} did not come within {a.limit:g} s")
            time.sleep(0.05)
        if hit == "ended":
            raise Refused(f"the run ended before {a.on!r}")
        say({"seen": a.on, "at": time.strftime("%H:%M:%S"), "stopping_in": a.delay})
        time.sleep(a.delay)
    state = run_state(a.port)
    if state["phase"] != "running":
        raise Refused(f"no run to stop: the run is {state['phase']!r} ({state['status']})")
    press(a.port, STOP)
    say({"pressed": "stop", "at": time.strftime("%H:%M:%S")})
    say(wait_phase(a.port, {"stopping", "ended"}, a.timeout))
    return 0


def state_cmd(a) -> int:
    if a.until:
        want = set(a.until.split(","))
        if bad := want - set(PHASES):
            raise Refused(f"--until takes {', '.join(PHASES)}, not {', '.join(sorted(bad))}")
        say(wait_phase(a.port, want, a.timeout))
    else:
        say(run_state(a.port))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("--root", required=True)
    p.add_argument("--port", type=int)
    p.add_argument("--data")
    p.add_argument("--title")
    p.add_argument("--timeout", type=float, default=60)
    p.set_defaults(fn=open_cmd)
    p = sub.add_parser("windows")
    p.add_argument("substr")
    p.set_defaults(fn=windows_cmd)
    p = sub.add_parser("title")
    p.add_argument("--hwnd", type=int, required=True)
    p.add_argument("--title", required=True)
    p.set_defaults(fn=title_cmd)
    p = sub.add_parser("record")
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--hwnd", type=int)
    which.add_argument("--window")
    p.add_argument("--out", required=True)
    p.add_argument("--wait", type=float, default=0)
    p.add_argument("--profile", default="default")
    p.add_argument("--crop-top", type=int)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--keep-gb", type=float)
    p.set_defaults(fn=record_cmd)
    for name, fn in (("start", start_cmd), ("stop", stop_cmd), ("state", state_cmd)):
        p = sub.add_parser(name)
        p.add_argument("--port", type=int, required=True)
        p.add_argument("--timeout", type=float, default=600 if name == "state" else 30)
        p.set_defaults(fn=fn)
        if name == "stop":
            p.add_argument("--root")
            p.add_argument("--on")
            p.add_argument("--delay", type=float, default=0)
            p.add_argument("--limit", type=float, default=600)
        if name == "state":
            p.add_argument("--until")
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    if sys.platform != "win32" and a.cmd in ("open", "windows", "title", "record"):
        print("gui_run: windows only", file=sys.stderr)
        return 1
    try:
        return a.fn(a)
    except Refused as e:
        print(f"gui_run: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
