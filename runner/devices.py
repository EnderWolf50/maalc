"""The emulators MaaFramework's toolkit finds, and starting a MuMu instance that is not running.

MaaToolkit finds only emulators that run, a MuMu one through MuMuManager.exe in its adb folder, and puts the instance
in the device's config as {"extras": {"mumu": {"enable": true, "path": <MuMu folder>, "index": <n>}}}
(MaaFramework v5.14.3, source/MaaToolkit/AdbDevice/AdbDeviceWin32Finder.cpp `find_mumu_devices`).
"""
from __future__ import annotations

import subprocess
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


LAUNCH_TIMEOUT = 60  # s MuMuManager may take to answer the launch; the instance boots after it returns


def launch_command(manager: str, index: int) -> list[str]:
    """MuMuManager's start of one instance. Named by a third-party page on MuMuManager
    (skills.sh/site/skills.mumu.163.com/mumu-control); not in MuMu's own documentation."""
    return [manager, "control", "--vmindex", str(index), "launch"]


def launch(manager: str, index: int, run=subprocess.run) -> tuple[int | None, str]:
    """Run the launch: (its exit code, what it printed); (None, why) when it could not run."""
    try:
        r = run(launch_command(manager, index), capture_output=True, timeout=LAUNCH_TIMEOUT,
                stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"{type(e).__name__}: {e}"
    text = b"".join(x or b"" for x in (r.stdout, r.stderr)).decode("utf-8", "replace")
    return r.returncode, " ".join(text.split())
