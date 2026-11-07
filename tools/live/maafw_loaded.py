"""Which MaaFramework DLLs a client or an agent has loaded, and whether its MaaFramework.dll is the fixed one (#497).

    uv run --group probe python tools/live/maafw_loaded.py PID...

For each PID and the processes under it (MXU and MFAAvalonia start the agent as a child), a line per loaded DLL whose
name starts with Maa: size and path. A MaaFramework.dll line ends with `MAAFW_FIX` when its bytes are the DLL
tools/install.py pins, `wheel` when they are the installed maafw wheel's, `other` otherwise. The fork and the wheel
both report MaaVersion() v5.14.3, so only the bytes tell them apart.

Exit 0 when at least one MaaFramework.dll is loaded and every one is MAAFW_FIX's, 1 otherwise.
"""

import argparse
import hashlib
import sys
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import maa  # noqa: E402
from install import MAAFW_FIX, fetch_zip  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def loaded_maa_dlls(proc: psutil.Process) -> list[Path]:
    paths = {Path(m.path) for m in proc.memory_maps(grouped=True)}
    return sorted(p for p in paths if p.name.lower().startswith("maa") and p.suffix.lower() == ".dll")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pids", type=int, nargs="+")
    args = ap.parse_args(argv)
    known = {sha256(fetch_zip(*MAAFW_FIX).read("MaaFramework.dll")): "MAAFW_FIX",
             sha256((Path(maa.__file__).parent / "bin" / "MaaFramework.dll").read_bytes()): "wheel"}
    frameworks = []
    for pid in args.pids:
        root = psutil.Process(pid)
        for proc in [root, *root.children(recursive=True)]:
            try:
                dlls = loaded_maa_dlls(proc)
            except psutil.Error as e:
                print(f"{proc.pid}: {e}")
                continue
            if not dlls:
                continue
            print(f"{proc.pid} {proc.name()}")
            for dll in dlls:
                tag = ""
                if dll.name.lower() == "maaframework.dll":
                    frameworks.append(known.get(sha256(dll.read_bytes()), "other"))
                    tag = f"  {frameworks[-1]}"
                print(f"  {dll.stat().st_size:>10,}  {dll}{tag}")
    if not frameworks:
        print("no MaaFramework.dll loaded")
    return 0 if frameworks and all(f == "MAAFW_FIX" for f in frameworks) else 1


if __name__ == "__main__":
    sys.exit(main())
