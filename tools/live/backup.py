"""Back up and verify the user's `install/`, so a live test leaves it as it found it.

  python tools/live/backup.py backup [--label <name>] [--root <install>]
  python tools/live/backup.py verify [--label <name>] [--root <install>]

`backup` writes an md5 manifest of every file under the install folder (default: `install/` of the
main checkout) except the runtime output folders (debug, logs, state, cache), and copies
`config/settings.json`, to `<main checkout>/.local/scratch/install-backup/<label>/`.
`verify` lists every file that changed, vanished or appeared since and exits 1 when there is any.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parents[1])

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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["backup", "verify"])
    ap.add_argument("--label", default="latest")
    ap.add_argument("--root", type=Path, default=main_checkout() / "install")
    a = ap.parse_args(argv)
    dest = local_dir("scratch", "install-backup", a.label)
    if a.cmd == "backup":
        print(f"backed up {backup(a.root, dest)} files of {a.root} -> {dest}")
        return 0
    diff = verify(a.root, dest)
    print("\n".join(diff) if diff else f"install matches the '{a.label}' backup (md5)")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
