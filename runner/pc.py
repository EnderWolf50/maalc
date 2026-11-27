"""The PC client's window (#940, spec #922 D3-D6, D17): finding it, its client area's size for a run, and the PC window
controller, a MaaFramework custom controller that wraps a Win32 controller of the window and speaks to MaaFramework as
the emulator does (the Android package, back key 4, `dumpsys window`), so the pipeline and the bot stay as they are.

The window's state comes from a Windows object (Win32Windows, or a test's fake): the one seam the controller adds
(spec #922 "Testing Decisions"). Before each screencap and each input the controller looks at the window: gone,
minimized or a client area not 16:9 and it calls nothing of the inner controller, answers with a black frame or a
failure, and holds the problem, which the runner reads each tick and stops the run by (D10). A minimized window is
the point: MaaFramework's background screencap makes a minimized window transparent and shows it unactivated (v5.14.3
PseudoMinimizeHelper.cpp), which changes the user's window. A minimize between the look and the screencap is a known
gap.

No input (D6): the inner controller's mouse and keyboard methods are Null, so MaaFramework builds no input unit for it
(v5.14.3 Win32ControlUnitMgr.cpp: an unknown method, Null among them, gives none, and the connect still succeeds); an
input it cannot take holds the problem PcInputFailed. The methods that move the cursor, take the foreground or need a
driver are listed in FORBIDDEN and refused by name.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

CLASS, TITLE = "UnityWndClass", "LimbusCompany"  # AALC's init_handle (docs/research/aalc/02-recognition-and-input.md)
GAME = "com.ProjectMoon.LimbusCompany"  # the package the pipeline and the bot name (agent/recovery.py GAME)
# device.pc_size: the client area a run sets, by its height at 16:9
SIZES = {"720": (1280, 720), "900": (1600, 900), "1080": (1920, 1080), "1440": (2560, 1440)}
KEYS = {4: 27}  # Android keycode -> Windows virtual key: back is Esc
# MaaWin32InputMethodEnum values (maa/define.py) the PC window never takes, with why (spec #922 D6)
FORBIDDEN = {
    "Seize": 1,  # takes the foreground and the cursor
    "LegacyEvent": 1 << 3,  # moves the cursor
    "PostThreadMessage": 1 << 4,  # not implemented in MaaFramework v5.14.3 (Win32ControlUnitMgr.cpp)
    "SendMessageWithCursorPos": 1 << 5,  # moves the cursor (MessageInput.cpp prepare_mouse_position)
    "PostMessageWithCursorPos": 1 << 6,
    "Interception": 1 << 9,  # a driver
}
NULL = 0  # MaaWin32InputMethodEnum.Null: no input unit
FRAME_POOL, PRINT_WINDOW = 1 << 1, 1 << 4  # MaaWin32ScreencapMethodEnum's background methods
BACKGROUND = FRAME_POOL | PRINT_WINDOW  # MaaWin32ScreencapMethodEnum.Background


class Problem(NamedTuple):
    """Why the window cannot be used: the runner's reason code (runner/session.py OWN_CODES), its params, the English
    reason."""
    code: str
    params: dict
    message: str


@dataclass(frozen=True)
class Look:
    """The window at one look: its client area's size, whether it is minimized, maximized or fullscreen, and its
    window rect (x, y, width, height) to put it back by."""
    width: int
    height: int
    minimized: bool = False
    maximized: bool = False
    fullscreen: bool = False
    rect: tuple = (0, 0, 0, 0)


def games(windows) -> list:
    """The handles of the game's windows among the top-level visible ones (D3)."""
    return [hwnd for hwnd, cls, title in windows.find() if cls == CLASS and title == TITLE]


def listed(windows) -> list[dict]:
    """The game's windows as the protocol's devices event lists them: title, client size, minimized."""
    out = []
    for hwnd in games(windows):
        if (look := windows.look(hwnd)) is not None:
            out.append({"title": TITLE, "width": look.width, "height": look.height, "minimized": look.minimized})
    return out


def trouble(look: Look | None, aspect: bool = True) -> Problem | None:
    """What keeps the window from use at this look: gone, minimized, or (with aspect) a client area not 16:9."""
    if look is None:
        return Problem("PcWindowGone", {}, "the game's window is gone")
    if look.minimized:
        return Problem("PcMinimized", {}, "the game's window is minimized")
    if aspect and (look.width <= 0 or look.width * 9 != look.height * 16):
        return Problem("PcNot16By9", {"width": look.width, "height": look.height},
                       f"the game's client area is {look.width}x{look.height}, not 16:9")
    return None


def resize(windows, hwnd, size: str, say):
    """Set the client area to device.pc_size for the run (D17): the top-left corner stays, the window is not activated
    and keeps its place in the stack. A fullscreen or maximized window and `keep` stay as they are. The function that
    puts the window back as it was, or None when nothing changed."""
    look = windows.look(hwnd)
    if size == "keep" or look is None:
        return None
    if look.fullscreen or look.maximized:
        say(f"the game's window is {'fullscreen' if look.fullscreen else 'maximized'}: its size stays "
            f"{look.width}x{look.height}")
        return None
    w, h = SIZES[size]
    if (look.width, look.height) == (w, h):
        return None
    windows.resize_client(hwnd, w, h)
    say(f"the game's client area {look.width}x{look.height} -> {w}x{h} for the run")
    rect = look.rect

    def restore():
        windows.place(hwnd, rect)
        say(f"the game's window put back at {rect[0]},{rect[1]} {rect[2]}x{rect[3]}")
    return restore


def win32_controller(hwnd, mouse: int = NULL, keyboard: int = NULL, make=None, screencap: int = BACKGROUND):
    """The inner controller of the window: MaaFramework's Win32 controller, background screencap (both methods, or the
    one named), mouse and keyboard Null unless named. A method of FORBIDDEN, or a screencap method that is not a
    background one, is refused (ValueError) before anything is made."""
    for which, method in (("mouse", mouse), ("keyboard", keyboard)):
        if (name := next((n for n, v in FORBIDDEN.items() if v == method), None)) is not None:
            raise ValueError(f"the {which} method {name} is forbidden for the PC window")
    if not screencap or screencap & ~BACKGROUND:
        from maa.define import MaaWin32ScreencapMethodEnum

        name = next((m.name for m in MaaWin32ScreencapMethodEnum if m.value == screencap), str(screencap))
        raise ValueError(f"the screencap method {name} is not a background one")
    if make is None:
        from maa.controller import Win32Controller as make
    ctl = make(hwnd, screencap, mouse, keyboard)
    ctl.set_screenshot_use_raw_size(True)  # the outer controller scales; coordinates reach the inner one 1:1
    return ctl


class Controller:
    """What the PC window controller does (D4), without MaaFramework: runner/pc_controller.py makes it a custom
    controller, and a test drives it as it is. It speaks through inner(hwnd), made at the connect. Each screencap and
    input looks at the window first (trouble); `problem` holds the first problem found, for the runner."""

    def __init__(self, hwnd, windows, inner=win32_controller):
        self.hwnd, self.windows, self.make_inner = hwnd, windows, inner
        self.inner, self.problem, self.shape = None, None, (720, 1280, 3)

    def hold(self, problem: Problem) -> bool:
        if self.problem is None:
            self.problem = problem
        return False

    def usable(self) -> bool:
        p = trouble(self.windows.look(self.hwnd))
        return True if p is None else self.hold(p)

    def done(self, job) -> bool:
        """An input the inner controller took; one it did not holds PcInputFailed."""
        if job.wait().succeeded:
            return True
        return self.hold(Problem("PcInputFailed", {}, "the game's window did not take an input"))

    # MaaFramework's custom controller
    def connect(self) -> bool:
        if not self.usable():
            return False
        self.inner = self.make_inner(self.hwnd)
        # .succeeded, not .connected: a custom controller's connected is a method (maa/controller.py CustomController)
        return self.inner.post_connection().wait().succeeded

    def request_uuid(self) -> str:
        return f"pc-{self.hwnd}"

    def get_custom_info(self) -> dict:
        return {"device": "pc"}

    def start_app(self, intent: str) -> bool:  # #948 starts and stops the game; until then the run stops (D4)
        return self.hold(Problem("PcRestartOff", {}, "restarting the game is off for the PC client"))

    def stop_app(self, intent: str) -> bool:
        return self.start_app(intent)

    def screencap(self):
        if not self.usable():
            return np.zeros(self.shape, dtype=np.uint8)  # a black frame; the run stops on the problem
        image = self.inner.post_screencap().wait().get()
        self.shape = image.shape
        return image

    def click(self, x: int, y: int) -> bool:
        return self.usable() and self.done(self.inner.post_click(x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        return self.usable() and self.done(self.inner.post_swipe(x1, y1, x2, y2, duration))

    def touch_down(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return self.usable() and self.done(self.inner.post_touch_down(x, y, contact, pressure))

    def touch_move(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return self.usable() and self.done(self.inner.post_touch_move(x, y, contact, pressure))

    def touch_up(self, contact: int) -> bool:
        return self.usable() and self.done(self.inner.post_touch_up(contact))

    def click_key(self, keycode: int) -> bool:
        return keycode in KEYS and self.usable() and self.done(self.inner.post_click_key(KEYS[keycode]))

    def key_down(self, keycode: int) -> bool:
        return keycode in KEYS and self.usable() and self.done(self.inner.post_key_down(KEYS[keycode]))

    def key_up(self, keycode: int) -> bool:
        return keycode in KEYS and self.usable() and self.done(self.inner.post_key_up(KEYS[keycode]))

    def input_text(self, text: str) -> bool:
        return False

    def shell(self, cmd: str, timeout: int):
        """`dumpsys window` as Android says it (agent/recovery.py focused_package): the game has the focus while its
        window is there, no window has it once it is gone."""
        if not cmd.startswith("dumpsys window"):
            return None
        if self.windows.look(self.hwnd) is None:
            self.hold(trouble(None))
            return "  mCurrentFocus=null"
        return f"  mCurrentFocus=Window{{0 u0 {GAME}/com.unity3d.player.UnityPlayerActivity}}"

    def inactive(self) -> bool:
        return self.inner is None or self.inner.post_inactive().wait().succeeded


class Win32Windows:
    """The windows as Windows says (user32, read through ctypes); off Windows it finds none. Sizes are read and set
    per-monitor DPI aware (aware): a DPI-unaware caller gets a scaled window's sizes scaled too."""

    PER_MONITOR_AWARE_V2 = -4  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2

    @contextmanager
    def aware(self):
        """This thread per-monitor DPI aware while it lasts (SetThreadDpiAwarenessContext, Windows 10 1607 and later;
        without it the thread stays as it is)."""
        set_context = getattr(self.user32, "SetThreadDpiAwarenessContext", None)
        if set_context is None:
            yield
            return
        set_context.restype, set_context.argtypes = self.ctypes.c_void_p, [self.ctypes.c_void_p]
        before = set_context(self.PER_MONITOR_AWARE_V2)
        try:
            yield
        finally:
            if before:
                set_context(before)

    def __init__(self):
        self.user32 = None
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            self.ctypes, self.wintypes, self.user32 = ctypes, wintypes, ctypes.windll.user32

    def find(self) -> list:
        """(hwnd, class, title) of each top-level visible window, as MaaToolkit's finder lists them (v5.14.3
        DesktopWindowWin32Finder.cpp: EnumWindows, IsWindowVisible), read here without MaaFramework: a scan lists
        them before it loads it."""
        if self.user32 is None:
            return []
        ctypes, wt, u = self.ctypes, self.wintypes, self.user32
        out = []

        def each(hwnd, _):
            if u.IsWindowVisible(hwnd):
                cls, title = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(512)
                u.GetClassNameW(hwnd, cls, 256)
                u.GetWindowTextW(hwnd, title, 512)
                out.append((int(hwnd), cls.value, title.value))
            return True

        u.EnumWindows(ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(each), 0)
        return out

    def _rect(self, get, hwnd):
        r = self.wintypes.RECT()
        return r if get(self.wintypes.HWND(hwnd), self.ctypes.byref(r)) else None

    def look(self, hwnd) -> Look | None:
        u = self.user32
        if u is None or not u.IsWindow(self.wintypes.HWND(hwnd)):
            return None
        with self.aware():
            return self._look(hwnd)

    def _look(self, hwnd) -> Look | None:
        u = self.user32
        client, window = self._rect(u.GetClientRect, hwnd), self._rect(u.GetWindowRect, hwnd)
        if client is None or window is None:
            return None
        rect = (window.left, window.top, window.right - window.left, window.bottom - window.top)
        return Look(width=client.right - client.left, height=client.bottom - client.top,
                    minimized=bool(u.IsIconic(self.wintypes.HWND(hwnd))),
                    maximized=bool(u.IsZoomed(self.wintypes.HWND(hwnd))),
                    fullscreen=self._fullscreen(hwnd, window), rect=rect)

    def _fullscreen(self, hwnd, window) -> bool:
        """The window covers its monitor whole and has no caption: Unity's fullscreen window."""
        class MONITORINFO(self.ctypes.Structure):
            _fields_ = [("cbSize", self.wintypes.DWORD), ("rcMonitor", self.wintypes.RECT),
                        ("rcWork", self.wintypes.RECT), ("dwFlags", self.wintypes.DWORD)]

        u, info = self.user32, MONITORINFO()
        info.cbSize = self.ctypes.sizeof(MONITORINFO)
        u.MonitorFromWindow.restype = self.wintypes.HMONITOR
        u.GetWindowLongW.restype = self.ctypes.c_long
        monitor = u.MonitorFromWindow(self.wintypes.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor or not u.GetMonitorInfoW(monitor, self.ctypes.byref(info)):
            return False
        m = info.rcMonitor
        caption = u.GetWindowLongW(self.wintypes.HWND(hwnd), -16) & 0x00C00000  # GWL_STYLE, WS_CAPTION
        return not caption and (window.left, window.top, window.right, window.bottom) == (m.left, m.top, m.right, m.bottom)

    # SetWindowPos flags: SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_NOOWNERZORDER
    NOMOVE, NOZORDER, NOACTIVATE, NOOWNERZORDER = 0x2, 0x4, 0x10, 0x200

    def resize_client(self, hwnd, width: int, height: int) -> bool:
        """The client area width x height, the window's frame kept: the top-left corner stays, nothing activates."""
        look = self.look(hwnd)
        if look is None:
            return False
        w, h = width + look.rect[2] - look.width, height + look.rect[3] - look.height
        with self.aware():
            return bool(self.user32.SetWindowPos(self.wintypes.HWND(hwnd), None, 0, 0, w, h,
                                                 self.NOMOVE | self.NOZORDER | self.NOACTIVATE | self.NOOWNERZORDER))

    def place(self, hwnd, rect) -> bool:
        """The window back at rect (x, y, width, height), nothing activated, its place in the stack kept."""
        if self.look(hwnd) is None:
            return False
        x, y, w, h = rect
        with self.aware():
            return bool(self.user32.SetWindowPos(self.wintypes.HWND(hwnd), None, x, y, w, h,
                                                 self.NOZORDER | self.NOACTIVATE | self.NOOWNERZORDER))
