"""The tasker's and the agent's memory, one log line at each new floor (#391), free of MaaFramework.

Only recorded: nothing is decided from it. A 15-floor run takes hours, and the 5-floor runs of 2026-10 grew the tasker
by steps of +277 to +425 MB and about +100 MB an hour; the line gives the curve a restart between floors would be
decided on (#853). Windows only, as the bot is: elsewhere each process reads as unknown.
"""
from __future__ import annotations

import ctypes
import os
import sys
from datetime import datetime
from typing import NamedTuple

# runner/session.py puts its own pid here for the agent it starts: the tasker, where MaaFramework recognises. The
# agent's parent is not it in development, where a venv's python.exe is a launcher between the two.
TASKER_PID = "MAALC_TASKER_PID"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MB = 2**20


class Mem(NamedTuple):
    """MB: the working set (what the 2026-10 runs called RSS) and the private bytes (the commit charge)."""
    working_set: float
    private: float


class _Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS_EX
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def process_memory(pid=None):
    """pid's Mem (None: this process), or None off Windows or when pid cannot be read (ended, not allowed)."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenProcess.restype = kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Counters), ctypes.c_ulong]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.GetCurrentProcess() if pid is None else kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:
        return None
    try:
        counters = _Counters(cb=ctypes.sizeof(_Counters))
        if not kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return Mem(counters.WorkingSetSize / MB, counters.PrivateUsage / MB)
    finally:
        if pid is not None:
            kernel32.CloseHandle(handle)


def tasker_pid(environ=os.environ):
    """The tasker's pid the runner handed this agent, or None (started by something else)."""
    try:
        return int(environ[TASKER_PID])
    except (KeyError, ValueError):
        return None


def seconds_since(start, now):
    """Seconds from start to now (UTC ISO times, settlement.now()'s format), or None when start is unknown."""
    try:
        return (datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    except (AttributeError, TypeError, ValueError):
        return None


def floor_line(floor, elapsed, tasker, agent):
    """The log line: the floor, each process's Mem (None: "?"), and the whole minutes since the run began (None: "?")."""
    def mb(m):
        return "?" if m is None else f"{m.working_set:.0f} MB (private {m.private:.0f} MB)"
    minutes = "?" if elapsed is None else f"{elapsed / 60:.0f}"
    return f"floor {floor} memory: tasker {mb(tasker)}, agent {mb(agent)}, {minutes} min into the run"


def floor_memory(floor, start, now):
    """floor_line with both processes read now."""
    pid = tasker_pid()
    return floor_line(floor, seconds_since(start, now), None if pid is None else process_memory(pid), process_memory())
