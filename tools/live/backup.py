"""Back up and verify the user's `install/`, so a live test leaves it as it found it.

  python tools/live/backup.py backup [--label <name>] [--root <install>]
  python tools/live/backup.py verify [--label <name>] [--root <install>]
  python tools/live/backup.py hold --done <file> [--timeout <seconds>] [--guard <log>] [--stop-recording <profile>] [--label <name>] [--root <install>]

`backup` writes an md5 manifest of every file under the install folder (default: `install/` of the
main checkout) except the runtime output folders (debug, logs, state, cache), and copies
`config/settings.json`, to `<main checkout>/.local/scratch/install-backup/<label>/`.
`verify` lists every file that changed, vanished or appeared since and exits 1 when there is any.
`hold` is backup, then a wait until `<file>` exists (or the timeout, default 2 h), then verify: the one command a
live test queues, so the emulator stays taken while the agent does the interactive steps and then creates `<file>`.
`--guard` names the `--log` of a `queue.py detach` (the bot): while that process runs the timeout does not run, and
it starts again when the bot ends, so the emulator is never handed on under a running bot or right after it. When the bot ends, `hold` prints
`[hold] bot ended <iso time>` (read by `queue.py resume`); with `--stop-recording <profile>` it stops that screen-record
profile 60 s later, so a recording nobody stopped does not grow for hours.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parents[1])

from live.queue import detached_running, pid_file
from local_dir import local_dir, main_checkout

RUNTIME = {"debug", "logs", "state", "cache"}


def manifest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.md5(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.relative_to(root).parts[0] not in RUNTIME}


def backup(root: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    files = manifest(root)
    (dest / "manifest.json").write_text(json.dumps(files, indent=1), encoding="utf-8")
    if (root / "config/settings.json").is_file():
        shutil.copy2(root / "config/settings.json", dest / "settings.json")
    return len(files)


def verify(root: Path, dest: Path) -> list[str]:
    before = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    now = manifest(root)
    return ([f"changed  {f}" for f in before if f in now and now[f] != before[f]]
            + [f"missing  {f}" for f in before if f not in now]
            + [f"new      {f}" for f in now if f not in before])


SCREENREC = Path.home() / ".claude/skills/screen-record/scripts/screenrec.py"  # the global screen-record skill


def stop_recording(profile: str) -> None:
    print(f"[hold] stopping recording '{profile}'", flush=True)
    subprocess.run(["uv", "run", str(SCREENREC), "stop", "--profile", profile], check=False)


def hold(root: Path, dest: Path, done: Path, timeout: float, poll: float = 2.0, guard: Path | None = None,
         running=detached_running, stop_profile: str | None = None, grace: float = 60.0, stop=stop_recording) -> int:
    print(f"backed up {backup(root, dest)} files of {root}; waiting for {done}", flush=True)
    deadline = time.monotonic() + timeout
    seen, ended = False, None  # the bot was seen running; when it ended (monotonic)
    while not done.exists():
        if guard and running(guard):
            seen, ended, deadline = True, None, time.monotonic() + timeout  # a restarted bot re-arms the end note # the agent's own steps after the bot get the whole timeout
        elif time.monotonic() >= deadline:
            break
        elif (seen or guard and pid_file(guard).exists()) and ended is None:  # a bot gone within one poll still counts  # durable for `queue.py resume`: nobody may have been watching
            ended = time.monotonic()
            print(f"[hold] bot ended {datetime.now().isoformat(timespec='seconds')}", flush=True)
        if ended is not None and stop_profile and time.monotonic() >= ended + grace:
            stop(stop_profile)  # a stranded recording must not grow for hours
            stop_profile = None
        time.sleep(poll)
    print("done file found" if done.exists() else f"timed out after {timeout:.0f} s", flush=True)
    diff = verify(root, dest)
    print("\n".join(diff) if diff else "install matches the backup (md5)")
    return 1 if diff else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["backup", "verify", "hold"])
    ap.add_argument("--label", default="latest")
    ap.add_argument("--done", type=Path, help="hold: the file that ends the wait")
    ap.add_argument("--timeout", type=float, default=7200)
    ap.add_argument("--guard", type=Path, help="hold: the --log of the detached bot; the timeout counts from its end")
    ap.add_argument("--stop-recording", metavar="PROFILE", help="hold: stop this screenrec profile 60 s after the bot ended")
    ap.add_argument("--root", type=Path, default=main_checkout() / "install")
    a = ap.parse_args(argv)
    dest = local_dir("scratch", "install-backup", a.label)
    if a.cmd == "hold":
        if not a.done:
            ap.error("hold needs --done")
        return hold(a.root, dest, a.done, a.timeout, guard=a.guard, stop_profile=a.stop_recording)
    if a.cmd == "backup":
        print(f"backed up {backup(a.root, dest)} files of {a.root} -> {dest}")
        return 0
    diff = verify(a.root, dest)
    print("\n".join(diff) if diff else f"install matches the '{a.label}' backup (md5)")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
