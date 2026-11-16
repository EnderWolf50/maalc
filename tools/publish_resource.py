"""Publish the resource package to the public maalc-resource repository (ADR 0012, spec #759, #770).

Usage: uv run python tools/publish_resource.py --remote <git url> [--work <folder>] [--version-date YYYY.MM.DD]
                                                [--client <game client>] [--source <url> ...]

Builds the package of assets/resource/base with tools/build_resource_package.py and, unless it equals the latest
published one, pushes it as one commit on `main` plus a tag named after its version. `main` holds exactly one package:
data/, image/, pipeline/ and manifest.json from the build, and LICENSE and NOTICE.md from this repository; nothing else
survives. The version is the publish date, YYYY.MM.DD (UTC), and YYYY.MM.DD.2, .3 for later publishes of the same day,
numbered from the tags already in the remote. The package equals the latest published one when its manifest (version
aside: files, client, format, template, sources) and its LICENSE and NOTICE.md are the same, so a change outside the
package publishes nothing. `.github/workflows/publish-resource.yml` runs this.
"""

import argparse
import datetime
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build_resource_package as bp  # noqa: E402  (puts agent/ on the path)
import resource_package as rp  # noqa: E402

IDENTITY = ["-c", "user.name=maalc publish workflow", "-c", "user.email=noreply@github.com"]
EXTRA = ("LICENSE", "NOTICE.md")  # copied from this repository's root: the attribution travels with the package


def parse_tag(tag: str) -> tuple[int, ...] | None:
    """The version a tag names, None for a tag that is not one (`v1.2`, `latest`)."""
    try:
        key = rp.version_key(tag)
    except ValueError:
        return None
    return key if 3 <= len(key) <= 4 and all(part.isdecimal() for part in tag.split(".")) else None


def latest_tag(tags: list[str]) -> str | None:
    versions = [tag for tag in tags if parse_tag(tag)]
    return max(versions, key=parse_tag, default=None)


def next_version(tags: list[str], day: str) -> str:
    """`day` when no tag has it yet, else `day.2`, `day.3`, ... Refuses to go back past a tag dated after `day`."""
    latest = latest_tag(tags)
    if latest and rp.version_key(latest)[:3] > rp.version_key(day):
        raise SystemExit(f"tag {latest} is dated after {day}: refusing to publish an older version")
    keys = [key for key in map(parse_tag, tags) if key]
    used = [key for key in keys if key[:3] == rp.version_key(day)]
    if not used:
        return day
    return f"{day}.{max(key[3] if len(key) == 4 else 1 for key in used) + 1}"


def should_publish(latest: dict | None, new: dict) -> bool:
    """False when `new` equals `latest`, the same description of the latest published package (None: nothing yet)."""
    return latest != new


def describe(manifest: dict, extras: dict[str, str]) -> dict:
    """What makes two packages the same: the manifest without its version, and the ids of LICENSE and NOTICE.md."""
    return {**{k: v for k, v in manifest.items() if k != "version"}, "extras": extras}


def git(*args, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        command = next(arg for arg in args if not arg.startswith("-") and "=" not in arg)
        raise SystemExit(f"git {command} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def _writable(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(path: Path) -> None:
    shutil.rmtree(path, onerror=_writable)  # git's object files are read-only on Windows


def publish(base: Path, work: Path, remote: str, day: str, sources: list[str], client: str | None = None,
            repo: Path = REPO) -> str | None:
    """Push the package of `base` to `remote` and return its version, None when there is nothing new to publish."""
    work = Path(work)
    if work.exists():
        rmtree(work)
    git("clone", "--quiet", "--filter=blob:none", remote, str(work))  # the history holds every package: no old blobs
    tags = git("tag", "--list", cwd=work).split()
    latest = latest_tag(tags)
    before = None
    if latest:
        before = describe(json.loads(git("show", f"{latest}:{rp.MANIFEST}", cwd=work)),
                          {name: git("rev-parse", f"{latest}:{name}", cwd=work) for name in EXTRA})
    after = describe(bp.build_manifest(base, day, sources, client),
                     {name: git("hash-object", str(Path(repo) / name)) for name in EXTRA})
    if not should_publish(before, after):
        return None
    version = next_version(tags, day)
    for entry in work.iterdir():
        if entry.name != ".git":
            rmtree(entry) if entry.is_dir() else entry.unlink()
    bp.build_package(base, work, version, sources, client)
    for name in EXTRA:
        shutil.copyfile(Path(repo) / name, work / name)
    git("checkout", "--quiet", "-B", "main", cwd=work)
    git("add", "--all", cwd=work)
    git(*IDENTITY, "commit", "--quiet", "-m", f"Resource package {version}", cwd=work)
    git(*IDENTITY, "tag", version, cwd=work)
    git("push", "--quiet", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{version}", cwd=work)
    return version


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remote", required=True, help="the git url of maalc-resource")
    ap.add_argument("--work", type=Path, default=Path("resource-publish"), help="a folder to clone it into (replaced)")
    ap.add_argument("--base", type=Path, default=bp.BASE)
    ap.add_argument("--version-date", default=datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d"))
    ap.add_argument("--client", help="the game client version (default: data/client.json)")
    ap.add_argument("--source", action="append", dest="sources")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    version = publish(args.base, args.work, args.remote, args.version_date, args.sources or rp.SOURCES, args.client)
    print(f"published {version}" if version else "nothing to publish: the package equals the latest published one")
