"""PreToolUse(Bash): deny GitHub text and commit messages that name this machine or its owner.

This repo is public. The generic shapes below catch any absolute path or file:// link, and every
personal term (game-account e-mail, local folder names) comes from the repo-local git config:
`git config --local --add maalc.privateTerm <term>`. That lives in .git/config, is shared by every
worktree and is never committed. `git config user.email` counts as a term too, and the Windows login
name counts when it appears as a path segment.

Checked: `gh issue|pr create|comment|edit|review|close|merge|reopen`, `gh release create|edit`, `gh api`,
`git commit|merge|tag`, including the contents of a `--body-file`/`-F` file. Paths that only name a file
to upload (`--attach`, `-R`, `git -C`) are fine.

Fails closed: text the hook cannot read (stdin, `$(...)`, a backtick, a heredoc, `--input`, a body file that
does not exist yet) is denied, because it could carry anything.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ARG = r"""(?:"[^"]*"|'[^']*'|\S+)"""
GIT_OPT = rf"""(?:-[Cc]\s+{ARG}|--(?:git-dir|work-tree|namespace)\s+{ARG}|--[\w-]+(?:=\S+)?|-[pP])"""
START = re.compile(r"\bgh\s+(?:issue|pr)\s+(?:create|comment|edit|review|close|merge|reopen)\b"
                   r"|\bgh\s+release\s+(?:create|edit)\b|\bgh\s+api\b"
                   rf"|\bgit\b(?:\s+{GIT_OPT})*\s+(?:commit|merge|tag)\b")
FILE_FLAG = re.compile(rf"(?<![\w-])(?:--body-file|--notes-file|--file|-F)(?:\s+|=|(?=\S))({ARG})")  # gh: -F is --body-file; git: -F is --file
FIELD_FILE = re.compile(rf"(?:--field|-F)\s*[\w.\[\]]+=@({ARG})")  # gh api -F key=@file
FIELD = re.compile(r"^[\w.\[\]]+=")  # `-F key=value` is an api field, not a file
INPUT = re.compile(r"--input(?:\s|=)")
UNREADABLE = re.compile(r"\$\(|`|<<-?\s*[\"']?\w")  # command substitution or heredoc
LOCAL = re.compile(r"\b[A-Za-z]:[\\/]+\w|(?<![\w.])/(?:home|Users|mnt/[a-z])/\w+|~[\\/]\.?\w|file://", re.I)
UNREADABLE_REASON = "write the body to a file with the Write tool and pass its absolute Windows path to --body-file"


def unquote(s: str) -> str:
    return s.strip("\"'")


def cygpath() -> str | None:
    """Git for Windows' cygpath, found on PATH or next to git itself (a hook may not have usr/bin on PATH)."""
    found = shutil.which("cygpath")
    if found or os.name != "nt":
        return found
    git = shutil.which("git")
    for root in (Path(git).parents[1:3] if git else []):
        if (exe := root / "usr/bin/cygpath.exe").is_file():
            return str(exe)
    return None


def native(path: str) -> str:
    """A `/`-rooted path as Git Bash means it (`/tmp/x`, `/d/dir`) becomes the Windows path Python can open."""
    if os.name == "nt" and path.startswith("/") and (tool := cygpath()):
        out = subprocess.run([tool, "-w", path], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        return out or path
    return path


def base_dir(prefix: str, start_text: str, cwd: str) -> Path:
    """Where relative paths resolve: cwd, after the `cd X &&` before the call and its `git -C X`."""
    base = Path(cwd)
    for m in re.finditer(rf"\bcd\s+({ARG})\s*(?:&&|;|\n)", prefix):
        base = base / native(unquote(m[1]))
    for m in re.finditer(rf"(?<![\w-])-C\s+({ARG})", start_text):
        base = base / native(unquote(m[1]))
    return base


def public_text(cmd: str, base: Path) -> tuple[str, bool]:
    """(the part of the call that reaches GitHub or the commit log, whether some of it could not be read)."""
    unreadable = bool(INPUT.search(cmd)) or bool(UNREADABLE.search(cmd))
    files = []
    for pat in (FILE_FLAG, FIELD_FILE):
        for m in pat.finditer(cmd):
            value = unquote(m[1])
            if pat is FILE_FLAG and FIELD.match(value):
                continue
            path = base / native(value)
            if value in ("-", "@-") or not path.is_file():
                unreadable = True
            else:
                files.append(path.read_text(encoding="utf-8", errors="replace"))
            cmd = cmd.replace(m[0], " ")
    cmd = re.sub(rf"--attach(?:\s+|=)({ARG})", lambda m: " " + unquote(m[1]).partition("#")[2], cmd)  # keep the alt text
    cmd = re.sub(rf"(?<![\w-])(?:--repo|-R|-C)\s+{ARG}", " ", cmd)  # on the command line only, never in a body file
    return re.sub(r"https?://\S+", " ", "\n".join([cmd, *files])), unreadable  # a link names a page, never a place here


def terms(cwd: str) -> list[str]:
    def git(*args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
    found = git("config", "--get-all", "maalc.privateTerm") + git("config", "user.email")
    return [t.strip() for t in found if len(t.strip()) >= 4]


def check(cmd: str, cwd: str) -> str | None:
    """The reason to deny the command, or None."""
    start = START.search(cmd)
    if not start:
        return None
    text, unreadable = public_text(cmd[start.start():], base_dir(cmd[:start.start()], start.group(0), cwd))
    if unreadable:
        return "The guard cannot read this text: " + UNREADABLE_REASON + "."
    found = {m.group(0) for m in LOCAL.finditer(text)}
    found |= {t for t in terms(cwd) if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.I)}
    login = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(login) >= 4 and re.search(rf"[\\/]{re.escape(login)}(?=[\\/\s\"'`]|$)", text, re.I):
        found.add(login)
    if found:
        return ("Public text names this machine or its owner: " + ", ".join(sorted(found)[:3])
                + ". Describe the evidence by its content and upload the file with --attach.")
    return None


if __name__ == "__main__":
    data = json.load(sys.stdin)
    reason = check(data.get("tool_input", {}).get("command", ""), data.get("cwd") or os.getcwd())
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
