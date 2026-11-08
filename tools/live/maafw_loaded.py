"""Which MaaFramework DLLs a client has loaded, and whether its MaaFramework.dll is the fixed one (#497).

    uv run --group probe python tools/live/maafw_loaded.py CLIENT_PID...

Give the PID of MXU or MFAAvalonia. For it and the processes under it, a line per loaded DLL whose name starts with
Maa: size and path. The agent, a child of the client, shows MaaAgentServer.dll and no MaaFramework.dll: recognition
runs in the client. A MaaFramework.dll line ends with `MAAFW_FIX` when its bytes are the DLL tools/install.py pins
(fetched once per run, about 1 MB), `wheel` when they are the installed maafw wheel's, `other` otherwise. The fork
and the wheel both report MaaVersion() v5.14.3, so only the bytes tell them apart.

Exit 0 when at least one MaaFramework.dll is loaded, every one is MAAFW_FIX's and every process could be read;
1 otherwise.
"""

import argparse
import hashlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:  # run as a script, tools/install.py is not importable until tools/ is on the path
    sys.path.insert(0, str(TOOLS))

from install import fixed_framework_dll, wheel_bin  # noqa: E402

FIXED = "MAAFW_FIX"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv=None) -> int:
    import psutil

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pids", type=int, nargs="+")
    args = ap.parse_args(argv)
    known = {sha256(fixed_framework_dll()): FIXED, sha256((wheel_bin / "MaaFramework.dll").read_bytes()): "wheel"}
    frameworks, unread = [], 0
    for pid in args.pids:
        try:
            root = psutil.Process(pid)
            procs = [root, *root.children(recursive=True)]
        except psutil.Error as e:
            print(f"{pid}: {e!r}")
            unread += 1
            continue
        for proc in procs:
            try:
                paths = {Path(m.path) for m in proc.memory_maps(grouped=True)}
                name = proc.name()
            except psutil.Error as e:
                print(f"{proc.pid}: {e!r}")
                unread += 1
                continue
            dlls = sorted(p for p in paths if p.name.lower().startswith("maa") and p.suffix.lower() == ".dll")
            if dlls:
                print(f"{proc.pid} {name}")
            for dll in dlls:
                tag = ""
                if dll.name.lower() == "maaframework.dll":
                    frameworks.append(known.get(sha256(dll.read_bytes()), "other"))
                    tag = f"  {frameworks[-1]}"
                print(f"  {dll.stat().st_size:>10,}  {dll}{tag}")
    if not frameworks:
        print("no MaaFramework.dll loaded")
    return 0 if frameworks and not unread and all(f == FIXED for f in frameworks) else 1


if __name__ == "__main__":
    sys.exit(main())
