"""The update of the resource package at TaskStart (#771, ADR 0012, spec #759): the installed `data/`, `image/` and `pipeline/`
take the files maalc-resource published since, so a new event table, template or pipeline reaches the task that found it.

`update(base, log, tasker)` is the one entry; it never raises, and a failure leaves the files as they were, with one log line
saying why; it says whether it reloaded the bundle, for TaskStart to rebuild the task's entry node (#779). The steps,
one function each: read the local manifest (`update`), fetch the newest one (`fetch_manifest`), plan what changes for
each part of the package (`plan_part`), download it into a staging folder and verify it (`stage`), swap it
in all or nothing and write the new manifest last (`swap`), then reload the bundle and clear what the old files left in memory (`refresh`).

`APPLIED` names the parts this build applies, each group by the version that covers it. An update of `image/` or `pipeline/`
also reloads the bundle in the running task, and puts the previous files back when that fails (#772). Stdlib only: the release's bundled Python runs it.
"""

import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import resource_package as rp

CHECK_SECONDS = 10  # the whole check of the remote manifest, not each socket call
DOWNLOAD_SECONDS = 60  # all the files of one update
MANIFEST_LIMIT = 8 << 20  # bytes: a manifest larger than this is not one
STAGING = ".update"  # beside resource/base: the same volume, so a swap is a rename
SHA256 = re.compile(r"[0-9a-f]{64}")
PREFIX = "resource update: "

# (the parts one version covers, the manifest field that versions them, the version this program knows). The parts whose
# remote version differs are skipped and keep their files.
APPLIED = ((("data",), "format", rp.FORMAT), (("image", "pipeline"), "template", rp.TEMPLATE))

# module.function of every functools cache that holds something read from data/; the test that scans agent/ fails on a
# cache neither listed here nor named there as not on data/.
DATA_CACHES = ("settings._recipes", "settings.gift_tables", "settings.shop_gifts", "settings.vestige_ids",
               "gifts._game_tables", "gifts.default_list", "event_actions.event_table", "run_start_actions.pack_ids",
               "pack_cover.covers", "battle.stagger_word")
# module.function that rebuild, in place, what a module built from data/ when it was imported (other modules hold the same
# objects through `from actions import GIFTS`), in this order
DERIVED = ("actions.reload_gifts", "shop_actions.reload_gifts")


class UpdateError(Exception):
    """A reason the files were kept: it goes in the log as it is."""


@dataclass
class Plan:
    """What an update changes in one part of the package."""

    part: str
    version: str = ""  # the remote version whose files these are
    changed: dict = field(default_factory=dict)  # POSIX path -> the remote manifest's {size, sha256}
    removed: list = field(default_factory=list)

    def __bool__(self):
        return bool(self.changed or self.removed)


# -- fetch ------------------------------------------------------------------------------------------------------------


def _get_url(url, seconds, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "maalc-resource-update"})
    with urllib.request.urlopen(request, timeout=seconds) as response:
        try:
            return response.read(limit + 1)
        except (TimeoutError, socket.timeout):
            raise
        except (OSError, http.client.HTTPException) as e:
            raise UpdateError(f"download interrupted: {e}") from None


def fetch(source, rel, seconds, limit):
    """The bytes of `<source>/<rel>`, at most limit + 1 of them. `source` is an http(s) URL or a folder (a local copy of
    maalc-resource). Within `seconds` in all, not per socket call: the read runs in a thread the caller stops waiting for."""
    if seconds <= 0:
        raise UpdateError(f"{rel}: timed out")
    if not source.startswith(("http://", "https://")):
        if "://" in source:
            raise UpdateError(f"{source}: not an http(s) URL or a folder")
        try:
            with (Path(source) / rel).open("rb") as f:
                return f.read(limit + 1)
        except OSError as e:
            raise UpdateError(f"{rel}: cannot read from {source}: {e.strerror or e}") from None
    box = {}

    def work():
        try:
            box["data"] = _get_url(f"{source.rstrip('/')}/{rel}", seconds, limit)
        except BaseException as e:  # handed to the caller below
            box["error"] = e

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise UpdateError(f"{rel}: timed out")
    error = box.get("error")
    if error is None:
        return box["data"]
    if isinstance(error, UpdateError):
        raise UpdateError(f"{rel}: {error}")
    if isinstance(error, urllib.error.HTTPError):
        raise UpdateError(f"{rel}: HTTP {error.code} from {source}")
    if isinstance(error, (TimeoutError, socket.timeout)) or isinstance(getattr(error, "reason", None), (TimeoutError, socket.timeout)):
        raise UpdateError(f"{rel}: timed out")
    if isinstance(error, (urllib.error.URLError, OSError, http.client.HTTPException)):
        reason = getattr(error, "reason", error)
        raise UpdateError(f"{rel}: cannot connect to {source}: {reason}")
    raise error


def valid_path(path):
    """A POSIX path inside one of the package's parts: no empty, `.` or `..` segment, no backslash or drive."""
    segments = path.split("/") if isinstance(path, str) else []
    return (len(segments) >= 2 and segments[0] in rp.PARTS and all(s not in ("", ".", "..") for s in segments)
            and not any(c in path for c in "\\:") and path.isprintable())


def check_files(manifest):
    """The manifest's `files` when every path and entry is one the program can use, else an UpdateError."""
    folded = set()
    for path, entry in manifest["files"].items():
        if not valid_path(path) or any(s.endswith((".", " ")) for s in path.split("/")):
            raise UpdateError(f"manifest.json: {path} is not a path of the package")
        if path.casefold() in folded:  # one file on Windows
            raise UpdateError(f"manifest.json: {path} differs from another path only by case")
        folded.add(path.casefold())
        if (not isinstance(entry, dict) or not isinstance(entry.get("size"), int) or isinstance(entry["size"], bool)
                or entry["size"] < 0 or not isinstance(entry.get("sha256"), str) or not SHA256.fullmatch(entry["sha256"])):
            raise UpdateError(f"manifest.json: the entry of {path} has no size and sha256")
    return manifest["files"]


def fetch_manifest(source, seconds):
    data = fetch(source, "main/manifest.json", seconds, MANIFEST_LIMIT)
    try:
        manifest = rp.check_manifest(json.loads(data.decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as e:  # ManifestError is a ValueError
        raise UpdateError(f"main/manifest.json is not a manifest: {e}") from None
    check_files(manifest)
    return manifest


# -- plan -------------------------------------------------------------------------------------------------------------


def plan_part(part, base, local, remote):
    """What taking the remote's `part` changes: its files that differ from the local manifest's or are missing on disk,
    and the local manifest's that the remote no longer lists."""
    prefix = part + "/"
    remote_files = {p: e for p, e in remote["files"].items() if p.startswith(prefix)}
    local_files = {p: e for p, e in local["files"].items() if p.startswith(prefix)}
    plan = Plan(part, remote["version"])
    for path, entry in remote_files.items():
        if local_files.get(path, {}).get("sha256") != entry["sha256"] or not (base / path).is_file():
            plan.changed[path] = entry
    plan.removed = sorted(p for p in local_files if p not in remote_files)
    return plan


def plan_update(base, local, remote, log):
    """One Plan for each part of the package this build applies and the remote's version of it allows."""
    plans = []
    for parts, name, known in APPLIED:
        if remote[name] != known:
            skipped = " and ".join(part + "/" for part in parts)
            log(f"{PREFIX}{skipped}: {name} {remote[name]} is not the one this program knows ({known}): skipped, kept its files")
            continue
        plans.extend(plan_part(part, base, local, remote) for part in parts)
    return plans


def merged_manifest(local, remote, plans):
    """The manifest after the swap: the remote's for the parts applied, the local's for the rest."""
    applied = {p.part + "/" for p in plans}
    files = {p: e for p, e in local["files"].items() if not p.startswith(tuple(applied))}
    files.update({p: e for p, e in remote["files"].items() if p.startswith(tuple(applied))})
    # an install that updates (it has a source) takes the remote's list, so a mirror added later reaches an old zip (ADR 0012);
    # a remote that lists none leaves the install's own
    sources = ([x for x in remote["sources"] if isinstance(x, str)] or local["sources"]) if local["sources"] else []
    manifest = {**remote, "sources": sources, "files": dict(sorted(files.items()))}
    for parts, name, _ in APPLIED:
        if parts[0] + "/" not in applied:
            manifest[name] = local[name]
    return manifest


# -- stage and swap ---------------------------------------------------------------------------------------------------


def stage(source, plans, staging, seconds):
    """Download every changed file into `staging`, each checked against the manifest's size and sha256."""
    deadline = time.monotonic() + seconds
    for plan in plans:
        for path, entry in plan.changed.items():
            data = fetch(source, f"{plan.version}/{path}", deadline - time.monotonic(), entry["size"])
            if len(data) < entry["size"]:
                raise UpdateError(f"download of {path} interrupted: {len(data)} of {entry['size']} bytes")
            if len(data) > entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise UpdateError(f"{path}: sha256 does not match the manifest's")
            target = staging / "new" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def swap(base, plans, manifest, staging):
    """Put the staged files in place, delete the removed ones, write the manifest last. A failure puts every file back.

    A changed file is replaced in one step, never moved out first, so it is never missing, and the removals come after all
    replacements. A crash that runs nothing after it (power, kill) leaves the old manifest, so the next run plans the same
    change and finishes it: a file replaced differs from the old manifest's sha256, one removed is gone from the remote's."""
    undo = []  # (target, a copy of its old file or None), newest last
    try:
        for plan in plans:
            for path in plan.changed:
                replace_file(base / path, staging / "new" / path, staging / "old" / path, undo)
        for plan in plans:
            for path in plan.removed:
                remove_file(base / path, staging / "old" / path, undo)
        # the manifest is replaced in one step, never moved out: a crash between the two would leave none
        temp, copy = staging / rp.MANIFEST, staging / "old" / rp.MANIFEST
        temp.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / rp.MANIFEST, copy)
        undo.append((base / rp.MANIFEST, copy))
        os.replace(temp, base / rp.MANIFEST)
    except Exception:
        rollback(undo)
        raise
    for plan in plans:
        for path in plan.removed:
            prune_empty(base, (base / path).parent, plan.part)
    return undo


def rollback(undo):
    """Put back every file `swap` changed, newest first: the manifest, which `swap` writes last, goes back first. The paths that would not go back."""
    failed = []
    for target, old in reversed(undo):
        try:  # one file that cannot go back must not keep the others from it
            if old is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)  # a folder the swap pruned
                os.replace(old, target)
        except OSError:
            failed.append(f"{target.parent.name}/{target.name}")
    return failed


def remove_file(target, old, undo):
    if target.exists():
        old.parent.mkdir(parents=True, exist_ok=True)
        os.replace(target, old)
        undo.append((target, old))


def replace_file(target, staged, old, undo):
    if target.exists():
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, old)
        undo.append((target, old))
    else:
        undo.append((target, None))
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, target)


def prune_empty(base, folder, part):
    """Remove the folders a deleted file left empty, up to (not including) the part's own."""
    while folder != base / part and base / part in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


# -- after the swap ---------------------------------------------------------------------------------------------------


def clear_data_caches():
    """Forget what the agent read from data/: every cache in DATA_CACHES, then what the modules built at import."""
    for name in DATA_CACHES:
        module, _, function = name.partition(".")
        if module in sys.modules:
            getattr(sys.modules[module], function).cache_clear()
    for name in DERIVED:
        module, _, function = name.partition(".")
        if module in sys.modules:
            getattr(sys.modules[module], function)()


class ClearRefused(UpdateError):
    """resource.clear() said no: the resource still holds what it held."""


def needs_reload(plans):
    """The bundle holds image/ and pipeline/; data/ is read from disk by the agent."""
    return any(p for p in plans if p.part != "data")  # a plan with no change is falsy


def reload_bundle(tasker, base):
    """Drop what the resource holds and load `base` again, waiting for the load. MaaFramework has no guard against doing
    this inside a running task: the task goes on with the new pipeline and templates (the test in test_task_chain.py)."""
    resource = tasker.resource
    if not resource.clear():
        raise ClearRefused("resource.clear() failed (a load is still running)")
    if not resource.post_bundle(base).wait().succeeded:
        raise UpdateError("resource.post_bundle() did not load the bundle")


def refresh(plans, tasker, base, undo, log):
    """After a swap, make the agent run on the new files: reload the bundle when image/ or pipeline/ changed, and clear the
    data caches when data/ did. A reload that fails puts the previous files back (every part: the version is one), loads
    them again and says so. True when the new files stand."""
    stands = True
    if needs_reload(plans):
        try:
            reload_bundle(tasker, base)
        except Exception as e:
            stands = False
            failed = rollback(undo)
            log(f"{PREFIX}the reload of the {plans[0].version} bundle failed ({type(e).__name__}: {e}): the previous files are back"
                + (f", except {', '.join(failed)}" if failed else ""))
            if isinstance(e, ClearRefused):  # the resource was not touched: the previous bundle is still loaded
                log(f"{PREFIX}the previous bundle is still loaded")
            else:
                try:
                    reload_bundle(tasker, base)
                except Exception as e:
                    log(f"{PREFIX}the previous bundle could not be reloaded either ({type(e).__name__}: {e})")
    if any(p for p in plans if p.part == "data"):
        try:
            clear_data_caches()
        except Exception as e:  # the files are whichever stand now: say so, not "kept"
            log(f"{PREFIX}what the agent had read of the old files could not all be cleared: {type(e).__name__}: {e}")
    return stands


# -- the update -------------------------------------------------------------------------------------------------------


def update(base, log, tasker):
    """Take the newer files of the package maalc-resource published, if any. Never raises. True when it reloaded the
    bundle, or tried to: the task's entry node may be the one posted on the old bundle (TaskStart, #779)."""
    try:
        return run_update(Path(base), log, tasker)
    except UpdateError as e:
        log(f"{PREFIX}kept the current files: {e}")
    except Exception as e:  # a task starts without an update
        log(f"{PREFIX}kept the current files: {type(e).__name__}: {e}")
    return False


def run_update(base, log, tasker):
    try:
        local = rp.read_manifest(base)
    except rp.ManifestError as e:
        log(f"{PREFIX}skipped: {e}")
        return False
    if local is None:
        log(f"{PREFIX}skipped: no {rp.MANIFEST}")
        return False
    if not local["sources"]:
        log(f"{PREFIX}skipped: the manifest lists no source (updates off)")
        return False
    staging = base.parent / STAGING
    shutil.rmtree(staging, ignore_errors=True)  # what a crash left
    deadline = time.monotonic() + CHECK_SECONDS
    remote, source, reasons = None, None, []
    for source in local["sources"]:
        try:
            remote = fetch_manifest(source, deadline - time.monotonic())
            break
        except UpdateError as e:
            reasons.append(str(e))
    if remote is None:
        raise UpdateError("; ".join(reasons))
    if rp.version_key(remote["version"]) < rp.version_key(local["version"]):
        log(f"{PREFIX}up to date: the remote {remote['version']} is older than {local['version']}")
        return False
    plans = plan_update(base, local, remote, log)
    if not plans:
        return False
    if not any(plans):
        if remote["version"] != local["version"] and len(plans) == sum(len(parts) for parts, _, _ in APPLIED):  # none skipped
            write_manifest_only(base, merged_manifest(local, remote, plans), staging)
        log(f"{PREFIX}up to date: {remote['version']} changes no file")
        return False
    try:
        stage(source, plans, staging / remote["version"], DOWNLOAD_SECONDS)
        undo = swap(base, plans, merged_manifest(local, remote, plans), staging / remote["version"])
        stands = refresh(plans, tasker, base, undo, log)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    reloads = needs_reload(plans)
    if stands:
        changed, removed = sum(len(p.changed) for p in plans), sum(len(p.removed) for p in plans)
        log(f"{PREFIX}{local['version']} -> {remote['version']}: {changed} changed, {removed} removed"
            + (", bundle reloaded" if reloads else ""))
    return reloads


def write_manifest_only(base, manifest, staging):
    staging.mkdir(parents=True, exist_ok=True)
    try:
        swap(base, [], manifest, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
