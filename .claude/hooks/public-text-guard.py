"""PreToolUse(Bash): deny GitHub text and commit messages that name this machine or its owner.

This repo is public. The generic shapes below catch any absolute path or file:// link, and every
personal term (game-account e-mail, local folder names) comes from the repo-local git config:
`git config --local --add maalc.privateTerm <term>`. That lives in .git/config, is shared by every
worktree and is never committed. The Windows login name and `git config user.email` count as terms too.

Checked: `gh issue|pr create|comment|edit|review`, `gh api`, `git commit`, including the contents of a
`--body-file`/`-F` file. Paths that only name a file to upload (`--attach`, `-R`, `git -C`) are fine.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

START = re.compile(r"\bgh\s+(?:issue|pr)\s+(?:create|comment|edit|review)\b|\bgh\s+api\b"
                   r"|\bgit\b(?:\s+-[Cc]\s+(?:\"[^\"]*\"|'[^']*'|\S+))*\s+commit\b")
ARG = r"""(?:"[^"]*"|'[^']*'|\S+)"""
FILE_FLAG = re.compile(rf"(?:--body-file|--file|-F)(?:\s+|=)({ARG})")  # gh issue/pr: -F is --body-file; git commit: -F is --file
FIELD_FILE = re.compile(rf"(?:--field|-F)\s+[\w.\[\]]+=@({ARG})")  # gh api -F key=@file
LOCAL = re.compile(r"\b[A-Za-z]:[\\/]+\w|(?<![\w.])/(?:home|Users|mnt/[a-z])/\w+|~[\\/]\.?\w|file://", re.I)


def unquote(s: str) -> str:
    return s.strip("\"'")


def public_text(cmd: str, cwd: str) -> str:
    """The part of the command (from the gh or git call on) that reaches GitHub or the commit log."""
    text = cmd
    for pat in (FILE_FLAG, FIELD_FILE):
        for m in pat.finditer(cmd):
            path = Path(cwd, unquote(m[1]))
            if path.is_file():
                text = text.replace(m[0], " ") + "\n" + path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(rf"--attach(?:\s+|=)({ARG})", lambda m: " " + unquote(m[1]).partition("#")[2], text)  # keep the alt text
    text = re.sub(rf"(?:--repo|-R|-C)\s+{ARG}", " ", text)
    return re.sub(r"https?://\S+", " ", text)  # a link names a page, never a place on this machine


def terms(cwd: str) -> list[str]:
    def git(*args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
    found = git("config", "--get-all", "maalc.privateTerm") + git("config", "user.email") + [os.environ.get("USERNAME", "")]
    return [t.strip() for t in found if len(t.strip()) >= 4]


def hits(cmd: str, cwd: str) -> list[str]:
    start = START.search(cmd)
    if not start:
        return []
    cmd = cmd[start.start():]  # a leading `cd <somewhere> &&` is not public text
    text = public_text(cmd, cwd)
    found = {m.group(0) for m in LOCAL.finditer(text)}
    found |= {t for t in terms(cwd) if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.I)}
    return sorted(found)


if __name__ == "__main__":
    data = json.load(sys.stdin)
    found = hits(data.get("tool_input", {}).get("command", ""), data.get("cwd") or os.getcwd())
    if found:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Public text names this machine or its owner: " + ", ".join(found[:3])
                + ". Describe the evidence by its content and upload the file with --attach."}}))
