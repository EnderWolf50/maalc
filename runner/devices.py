"""The emulators MaaFramework's toolkit finds, what adb says of one, and starting a MuMu instance that is not running.

MaaToolkit finds only emulators that run, a MuMu one through MuMuManager.exe in its adb folder, and puts the instance
in the device's config as {"extras": {"mumu": {"enable": true, "path": <MuMu folder>, "index": <n>}}}
(MaaFramework v5.14.3, source/MaaToolkit/AdbDevice/AdbDeviceWin32Finder.cpp `find_mumu_devices`). It lists a MuMu
instance by what MuMuManager says, seconds before the instance's adb answers (#831).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

LOOPBACK = ("127.0.0.1", "localhost")


def mumu(device) -> dict | None:
    """{index, manager, path} of a MuMu device: its instance number, MuMuManager.exe, the MuMu folder; None for another."""
    cfg = ((device.config or {}).get("extras") or {}).get("mumu") or {}
    if not cfg.get("enable") or not isinstance(cfg.get("index"), int):
        return None
    return {"index": cfg["index"], "manager": str(Path(device.adb_path).parent / "MuMuManager.exe"),
            "path": str(cfg.get("path", ""))}


def describe(device) -> dict:
    """The device as the protocol's devices event lists it."""
    return {"name": device.name, "address": device.address, "adb_path": str(device.adb_path), "mumu": mumu(device)}


def ordered(devices) -> list:
    """MuMu instances first, each group in the toolkit's order."""
    return sorted(devices, key=lambda d: mumu(d) is None)


def same_address(a: str, b: str) -> bool:
    """One adb address: the same text, or the same port on the loopback host (127.0.0.1 and localhost)."""
    if a == b:
        return True
    (ha, _, pa), (hb, _, pb) = a.rpartition(":"), b.rpartition(":")
    return bool(pa) and pa == pb and ha in LOOPBACK and hb in LOOPBACK


def find(devices, address: str):
    """The first device at address, or None."""
    return next((d for d in devices if same_address(d.address, address)), None)


ADB_TIMEOUT = 10  # s each adb call of adb_state may take


def adb_state(device, run=subprocess.run) -> str:
    """What adb says of device: "device" once MaaFramework's connect can take it, else its answer ("error: device
    offline" while a MuMu instance boots). It asks as that connect does, with the device's own adb: `adb connect` for a
    network address, then `adb -s <address> get-state` (MaaFramework v5.14.3,
    source/MaaAdbControlUnit/General/Connection.cpp). The answer goes to a file, not a pipe: an adb server the call
    starts outlives it, and run() would read a pipe that server holds until the server ends."""
    adb, address = str(device.adb_path), device.address
    asks = ([[adb, "connect", address]] if ":" in address else []) + [[adb, "-s", address, "get-state"]]
    with tempfile.TemporaryFile() as said:
        try:
            for cmd in asks:
                said.seek(0)
                said.truncate()
                r = run(cmd, stdin=subprocess.DEVNULL, stdout=said, stderr=subprocess.STDOUT, timeout=ADB_TIMEOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as e:
            return f"{type(e).__name__}: {e}"
        said.seek(0)
        text = " ".join(said.read().decode("utf-8", "replace").split())
    return "device" if r.returncode == 0 and text == "device" else text or f"exit code {r.returncode}"


LAUNCH_TIMEOUT = 60  # s MuMuManager may take to answer the launch; the instance boots after it returns
# Out of the window's Job Object (gui/src-tauri/src/runner.rs Job), which ends its processes at the run's end: MuMu and what
# MuMuManager starts for it outlive the run. A job that allows no breakaway refuses the flag; the launch then runs in it,
# and says so. Off Windows there is no job, and both flags are 0.
CREATE_BREAKAWAY_FROM_JOB = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


def launch_command(manager: str, index: int) -> list[str]:
    """MuMuManager's start of one instance. Named by a third-party page on MuMuManager
    (skills.sh/site/skills.mumu.163.com/mumu-control); not in MuMu's own documentation."""
    return [manager, "control", "--vmindex", str(index), "launch"]


def launch(manager: str, index: int, run=subprocess.run) -> tuple[int | None, str]:
    """Run the launch, out of the caller's job when it may (CREATE_BREAKAWAY_FROM_JOB): (its exit code, what it printed);
    (None, why) when it could not run."""
    quiet = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r, note = None, ""
    for flags in (quiet | CREATE_BREAKAWAY_FROM_JOB, quiet):
        try:
            r = run(launch_command(manager, index), capture_output=True, timeout=LAUNCH_TIMEOUT,
                    stdin=subprocess.DEVNULL, creationflags=flags)
            break
        except OSError as e:
            if not (flags & CREATE_BREAKAWAY_FROM_JOB):
                return None, f"{type(e).__name__}: {e}"
            note = f"inside the caller's job (breakaway refused: {type(e).__name__}: {e}): MuMu ends with the run; "
        except subprocess.SubprocessError as e:
            return None, f"{type(e).__name__}: {e}"
    text = b"".join(x or b"" for x in (r.stdout, r.stderr)).decode("utf-8", "replace")
    return r.returncode, note + " ".join(text.split())
