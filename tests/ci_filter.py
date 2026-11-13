"""Which non-code files the tests read, and the CI filter that must name them (#684).

`.github/workflows/ci.yml` skips the `agent` job (all the Python tests) for a pull request that changes only docs, gui/,
root `*.md` files and LICENSE. A test that reads one of those files would then not run when it changes. The `read` filter
of the `changes` job names the files tests read; its pattern list is the one source. conftest.py records every file the
test process opens or lists (`record`) and, through tests/ci_child/sitecustomize.py, every Python child of it. At the end of
a run `unlisted` names the ones outside the list, so a test that starts reading a new docs or gui file fails its shard until
the list catches up. Not seen: a file only `stat` or `exists()` touches, and a child that is not Python or runs `python -I`.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def glob_regex(pattern: str) -> re.Pattern:
    """A paths-filter (picomatch) pattern as a regex: `**` crosses folders, `*` and `?` stay in one. Braces, brackets and
    parentheses are picomatch syntax this does not read, so a pattern with one is refused rather than matched wrongly."""
    if re.search(r"[{}\[\]()]", pattern):
        raise ValueError(f"glob_regex does not read {pattern!r}")
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(patterns, path: str) -> bool:
    return any(glob_regex(p).match(path) for p in patterns)


def changes_steps() -> dict:
    steps = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["changes"]["steps"]
    return {s["id"]: s for s in steps if "id" in s}


def filter_patterns(step: str, name: str) -> list[str]:
    return yaml.safe_load(changes_steps()[step]["with"]["filters"])[name]


def not_code() -> list[str]:
    """The patterns of the `code` filter that take a file out: its non-code files. The filter must stay `**` minus patterns
    under `predicate-quantifier: every`, the only shape this reads."""
    patterns = filter_patterns("filter", "code")
    assert patterns[0] == "**" and all(p.startswith("!") for p in patterns[1:]), patterns
    assert changes_steps()["filter"]["with"]["predicate-quantifier"] == "every"
    return [p[1:] for p in patterns[1:]]


def read_patterns() -> list[str]:
    return filter_patterns("readfilter", "read")


def unlisted(opened) -> list[str]:
    """Of the repository paths (forward slashes, relative to the root) opened, the non-code ones the `read` filter lacks."""
    outside, listed = not_code(), read_patterns()
    return sorted(p for p in set(opened) if matches(outside, p) and not matches(listed, p))


OPENED: set[str] = set()
_ROOT = os.path.normcase(str(ROOT)) + os.sep
CHILD_DIR = Path(__file__).resolve().parent / "ci_child"  # its sitecustomize.py records a Python child's opens
SKIPPED = (".venv/", ".git/", ".local/", "node_modules/", "src-tauri/target/", "gui/dist/")  # not tracked, never a PR's change
LOG_ENV = "CI_FILTER_LOG"


def record(path, listing: bool = False) -> None:
    """Note `path` when it lies in the repository (the cheap checks first: this runs on every open). A listed folder is
    noted with a closing slash, and only inside docs/ and gui/: the root and the code folders are listed all the time."""
    try:
        p = os.path.abspath(os.fsdecode(path))
    except (TypeError, ValueError):
        return
    if not os.path.normcase(p).startswith(_ROOT):
        return
    rel = p[len(_ROOT):].replace(os.sep, "/")  # the case the opener wrote: the filter's patterns are case-sensitive
    if any(s in rel + "/" for s in SKIPPED) or listing and not rel.startswith(("docs", "gui")):
        return
    OPENED.add(rel + "/" if listing else rel)


def install() -> None:
    """Note every open in this process, and hand a log to the Python children it starts (see all_opened)."""
    def hook(event, args):
        if event == "open":
            record(args[0])
        elif event in ("os.listdir", "os.scandir"):
            record(args[0] if args[0] is not None else ".", listing=True)

    sys.addaudithook(hook)
    fd, log = tempfile.mkstemp(prefix="ci-filter-", suffix=".log")
    os.close(fd)
    os.environ[LOG_ENV] = log
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(CHILD_DIR), os.environ.get("PYTHONPATH")]))


def all_opened() -> set[str]:
    """What this process and its Python children opened."""
    log = os.environ.get(LOG_ENV)
    from_children = Path(log).read_text(encoding="utf-8").splitlines() if log and Path(log).exists() else []
    return OPENED | set(from_children)


def forget_log() -> None:
    if log := os.environ.pop(LOG_ENV, None):
        Path(log).unlink(missing_ok=True)
