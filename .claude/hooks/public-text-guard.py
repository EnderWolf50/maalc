"""PreToolUse(Bash): deny GitHub text and commit messages that name this machine or its owner.

This repo is public. The generic shapes below catch any absolute path or file:// link, and every
personal term (game-account e-mail, local folder names) comes from the repo-local git config:
`git config --local --add maalc.privateTerm <term>`. That lives in .git/config, is shared by every
worktree and is never committed. `git config user.email` counts as a term too, and the Windows login
name counts when it appears as a path segment.

A body file is named by any `--<word>-file` flag, and the guard reads the file, never the path that names it: an
absolute path is fine, a local path inside the text is not. A `questions-<n>` label (a note kept in .local) is denied too.
A `gh pr create|edit --body-file` body must also carry `N passed, M failed` and an issue on each "not run" line.

Checked: `gh issue|pr create|comment|edit|review|close|merge|reopen`, `gh release create|edit`, `gh api`,
`git commit|merge|tag`, including the contents of a `--body-file`/`-F` file. Paths that only name a file
to upload (`--attach`, `-R`, `git -C`) are fine.

Fails closed: text the hook cannot read (stdin, `$(...)`, a backtick, a heredoc, `--input`, a body file that
does not exist yet) is denied, because it could carry anything.

Each publishing call is cut at its own boundary, read the way bash reads it (quotes, backslashes, `$(...)`,
`${...}`, comments). A call inside quotes (`bash -c`, `eval`) or after a heredoc is checked to the end of the
line. This is a seatbelt against an agent's accidental leak, not a sandbox: a `$var`, a body file rewritten
earlier in the same command, or text that `xargs` supplies to a text flag still pass.
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
FILE_FLAG = re.compile(rf"(?<![\w-])(?:--[a-z]+-file|--file|-F)(?:\s+|=|(?=\S))({ARG})")  # --body-file, --notes-file, --comment-file...; gh: -F is --body-file; git: -F is --file
FIELD_FILE = re.compile(rf"(?:--field|-F)\s*[\w.\[\]]+=@({ARG})")  # gh api -F key=@file
FIELD = re.compile(r"^[\w.\[\]]+=")  # `-F key=value` is an api field, not a file
INPUT = re.compile(r"--input(?:\s|=)")
UNREADABLE = re.compile(r"\$\(|`|<<-?\s*[\"']?\w")  # command substitution or heredoc
LOCAL = re.compile(r"\b[A-Za-z]:[\\/]+\w|(?<![\w.])/(?:home|Users|mnt/[a-z])/\w+|~[\\/]\.?\w|file://", re.I)
LOCAL_NOTE = re.compile(r"\bquestions-\d+\b", re.I)  # the label of a note that lives only in .local/scratch
PR_CALL = re.compile(r"\bgh\s+pr\s+(?:create|edit)\b")
BODY_FILE = re.compile(rf"(?<![\w-])(?:--body-file|-F)(?:\s+|=|(?=\S))({ARG})")
TEST_LINE = re.compile(r"\b\d+ passed, \d+ failed\b", re.I)
NOT_RUN = re.compile(r"\bnot run\b", re.I)
NOT_RUN_OK = re.compile(r"#\d+|not run:?\s*(?:none|n/a)\b", re.I)
HEREDOC = re.compile(r"<<-?\s*[\"']?\w")
EMPTY_FLAG = re.compile(r"(?<![\w-])(?:--[a-z]+-file|--file|-F)\s*$")  # xargs supplies the file
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


def quoted(cmd: str) -> set:
    """Positions inside a quoted argument, read with scan()'s rules."""
    inside = set()
    scan(cmd, 0, False, inside)
    return inside


def bare(m, inside: set) -> bool:
    """The match starts a word of its own, not text in the middle of a quoted argument."""
    return not (m.start() in inside and m.start() - 1 in inside)


def public_text(cmd: str, base: Path) -> tuple[str, bool]:
    """(the part of the call that reaches GitHub or the commit log, whether some of it could not be read)."""
    unreadable = bool(UNREADABLE.search(cmd)) or any(bare(m, quoted(cmd)) for p in (INPUT, EMPTY_FLAG) for m in p.finditer(cmd))
    files = []
    for pat in (FILE_FLAG, FIELD_FILE):
        inside = quoted(cmd)
        for m in pat.finditer(cmd):
            if not bare(m, inside):
                continue
            value = unquote(m[1])
            if pat is FILE_FLAG and FIELD.match(value):
                continue
            path = base / native(value)
            if value in ("-", "@-") or not path.is_file():
                unreadable = True
            else:
                files.append(path.read_text(encoding="utf-8", errors="replace"))
            cmd = cmd.replace(m[0], " ")
    inside = quoted(cmd)
    cmd = re.sub(rf"--attach(?:\s+|=)({ARG})", lambda m: " " + unquote(m[1]).partition("#")[2] if bare(m, inside) else m[0], cmd)  # keep the alt text
    inside = quoted(cmd)
    cmd = re.sub(rf"(?<![\w-])(?:--repo|-R|-C)\s+{ARG}", lambda m: " " if bare(m, inside) else m[0], cmd)  # on the command line only, never in a body file
    return re.sub(r"https?://\S+", " ", "\n".join([cmd, *files])), unreadable  # a link names a page, never a place here


def pr_body_problem(call: str, base: Path) -> str | None:
    """docs/agents/pr.md for a `gh pr create|edit --body-file`: a test line `N passed, M failed`, and an issue
    (`#n`) on every line that says something was not run."""
    if not PR_CALL.search(call):
        return None
    inside = quoted(call)
    for m in BODY_FILE.finditer(call):
        path = base / native(unquote(m[1]))
        if not bare(m, inside) or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if not TEST_LINE.search(body):
            return "The PR body needs the test result as `<command> -> N passed, M failed` (docs/agents/pr.md)."
        for line in body.splitlines():
            if NOT_RUN.search(line) and not NOT_RUN_OK.search(line):
                return "A PR body line says `not run` without the issue that tracks it (`#<n>`): " + line.strip()[:80]
    return None


def terms(cwd: str) -> list[str]:
    def git(*args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
    found = git("config", "--get-all", "maalc.privateTerm") + git("config", "user.email")
    return [t.strip() for t in found if len(t.strip()) >= 4]


def scan(cmd: str, at: int, stop: bool, inside: set | None = None) -> tuple[int, bool]:
    """(where the call starting at `at` ends, whether a quote or `$(...)` is still open there), the way bash reads it:
    a backslash escapes the next character outside quotes, in "..." and in $'...', never in '...'."""
    quote, closers, i = "", [], at
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and quote != "\'":
            if quote and inside is not None:
                inside.update((i, i + 1))
            i += 2
            continue
        if quote:
            if inside is not None:
                inside.add(i)
            if c == "\'" and quote in "\'$" or c == quote:
                quote = ""
        elif c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()<>"):  # a comment runs to the end of the line
            nl = cmd.find("\n", i)
            i = nl if nl >= 0 else len(cmd)
            continue
        elif cmd.startswith("$\'", i):
            quote, i = "$", i + 1
        elif c in "'\"":
            quote = c
        elif cmd.startswith(("$(", "${"), i):
            closers, i = closers + [")" if cmd[i + 1] == "(" else "}"], i + 1
        elif closers and c == closers[-1]:
            closers.pop()
        elif stop and not closers and (c in ";|\n" or cmd.startswith("&&", i)):
            break
        i += 1
    return i, bool(quote or closers)


def segment(cmd: str, at: int) -> str:
    """The one call starting at `at`; the rest of the line when the call sits inside quotes (bash -c, eval)."""
    if scan(cmd[:at], 0, False)[1] or HEREDOC.search(cmd[:at]):  # a heredoc body is not read: fail closed
        return cmd[at:]
    return cmd[at:scan(cmd, at, True)[0]]


def check(cmd: str, cwd: str) -> str | None:
    """The reason to deny the command, or None. Every publishing call in the line is checked on its own."""
    for start in START.finditer(cmd):
        reason = check_call(segment(cmd, start.start()), cmd[:start.start()], start.group(0), cwd)
        if reason:
            return reason
    return None


def check_call(call: str, prefix: str, start_text: str, cwd: str) -> str | None:
    text, unreadable = public_text(call, base_dir(prefix, start_text, cwd))
    if unreadable:
        return "The guard cannot read this text: " + UNREADABLE_REASON + "."
    found = {m.group(0) for m in LOCAL.finditer(text)} | {m.group(0) for m in LOCAL_NOTE.finditer(text)}
    found |= {t for t in terms(cwd) if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.I)}
    login = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if len(login) >= 4 and re.search(rf"[\\/]{re.escape(login)}(?=[\\/\s\"'`]|$)", text, re.I):
        found.add(login)
    if found:
        return ("Public text names this machine or its owner: " + ", ".join(sorted(found)[:3])
                + ". Describe the evidence by its content and upload the file with --attach.")
    return pr_body_problem(call, base_dir(prefix, start_text, cwd))


if __name__ == "__main__":
    data = json.load(sys.stdin)
    reason = check(data.get("tool_input", {}).get("command", ""), data.get("cwd") or os.getcwd())
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
