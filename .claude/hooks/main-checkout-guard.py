"""PreToolUse(Bash, PowerShell): deny a git command that switches the main checkout to another branch.

The main checkout stays on `main`: `tools/after_land.py` refuses off main and a live run reads
`install/` from it. Denied there: `git switch ...`, `git checkout -b|-B|--orphan|--detach ...`, and
`git checkout <ref>` when `<ref>` names a branch, tag or commit. `git checkout -- <path>`, `git checkout <ref> -- <path>`
and `git checkout <path>` restore files and stay allowed. A linked worktree is free to switch.

The checkout a command acts on is found as git does: the folder the call runs in, after the `cd X` / `Set-Location X`
before it and its `git -C X`. It is the main checkout when git's dir and common dir are the same. A call inside quotes
(`bash -c "git switch x"`) is not read; this is a seatbelt for an agent's accident, not a sandbox.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOKEN = re.compile(r""""[^"]*"|'[^']*'|\S+""")
SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
CD = {"cd", "set-location", "sl", "pushd", "chdir"}
GIT_VALUE_OPTS = {"-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
SWITCHING_FLAGS = {"-b", "-B", "--orphan", "--detach", "-d"}
DENY = ("The main checkout stays on main. Work in a linked worktree (git worktree add) instead of "
        "switching or creating a branch here.")


def unquote(s: str) -> str:
    return s.strip("\"'")


def native(path: str) -> str:
    """A Git Bash path (`/d/dir`) as a Windows one."""
    m = re.match(r"^/([a-zA-Z])(?:/(.*))?$", path)
    return f"{m[1].upper()}:/{m[2] or ''}" if os.name == "nt" and m else path


def git_calls(cmd: str, cwd: str):
    """(directory, git arguments after its global options) for every `git` call that starts a command."""
    here = Path(cwd)
    for part in SEPARATORS.split(cmd):
        words = [unquote(t) for t in TOKEN.findall(part)]
        while words and words[0] in ("&", "."):
            words = words[1:]
        if not words:
            continue
        head = words[0].lower()
        if head in CD and len(words) > 1:
            here = here / native(words[1])
        elif re.fullmatch(r"(?:.*[\\/])?git(?:\.exe)?", head):
            where, args, i = here, words[1:], 0
            while i < len(args) and args[i].startswith("-"):
                if args[i] == "-C" and i + 1 < len(args):
                    where = where / native(args[i + 1])
                i += 2 if args[i] in GIT_VALUE_OPTS | {"-C"} else 1
            yield where, args[i:]


def is_main_checkout(where: Path) -> bool:
    r = subprocess.run(["git", "-C", str(where), "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
                       capture_output=True, text=True, encoding="utf-8")
    dirs = r.stdout.split("\n")[:2]
    return r.returncode == 0 and len(dirs) == 2 and Path(dirs[0]) == Path(dirs[1])


def is_ref(where: Path, name: str) -> bool:
    """`name` is a branch (local, or a remote one git would create locally), a tag or a commit."""
    for probe in (f"{name}^{{commit}}", f"refs/remotes/origin/{name}^{{commit}}"):
        if subprocess.run(["git", "-C", str(where), "rev-parse", "--verify", "--quiet", probe],
                          capture_output=True).returncode == 0:
            return True
    return False


def switches(where: Path, args: list[str], ref=is_ref) -> bool:
    if not args:
        return False
    if args[0] == "switch":
        return not {"-h", "--help"} & set(args[1:])
    if args[0] != "checkout":
        return False
    rest = args[1:]
    if SWITCHING_FLAGS & set(rest) or any(a.startswith(("-b", "-B")) for a in rest):
        return True
    before, after = rest, []
    if "--" in rest:
        before, after = rest[:rest.index("--")], rest[rest.index("--") + 1:]
    if after:
        return False  # `git checkout -- path`, `git checkout <ref> -- path`: files only
    positional = [a for a in before if a == "-" or not a.startswith("-")]
    return len(positional) == 1 and (positional[0] == "-" or ref(where, positional[0]))  # `git checkout <ref> <path>` restores files


def check(cmd: str, cwd: str, main=is_main_checkout, ref=is_ref) -> str | None:
    for where, args in git_calls(cmd, cwd):
        if switches(where, args, ref) and main(where):
            return DENY
    return None


if __name__ == "__main__":
    data = json.load(sys.stdin)
    reason = check(data.get("tool_input", {}).get("command", ""), data.get("cwd") or os.getcwd())
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
