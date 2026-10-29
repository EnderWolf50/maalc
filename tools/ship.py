"""Merge pull requests one at a time and test integration merges.

  uv run python tools/ship.py ready <pr>...
  uv run python tools/ship.py land <pr> --go
  uv run python tools/ship.py into <integration-branch> <branch>

`ready` prints one line per PR: head SHA, `ci-ok` state, mergeable, draft, base and the open PRs stacked on its branch.

`land` merges one PR (merge commit) once `ci-ok` passed on its current head and it is mergeable. It
retargets every PR stacked on the branch to the base before deleting the branch, waits for the CI run of the
merge commit on the base branch and exits non-zero when that run is red. A green run is followed by
`tools/after_land.py` in the main checkout, unless the emulator queue has a holder (`install/` is in use):
then the command to run later is printed. A second PR is the caller's next step, after this call returned green.

`into` merges `<branch>` into the integration branch (`--no-ff`) in a worktree of it, runs `tools/check.py`
through the bench queue and pushes only on green. A conflict or a red check leaves the branch as it was.
The first merge into an integration branch with no open PR opens a draft one, so Linux CI runs from then on.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from local_dir import local_dir, main_checkout

CI_CHECK = "ci-ok"
PR_FIELDS = "number,state,isDraft,mergeable,baseRefName,headRefName,headRefOid,isCrossRepository,statusCheckRollup"
MAIN_CI_TIMEOUT = 45 * 60
POLL = 30.0


def run(argv: list[str], cwd: str | Path | None = None) -> tuple[int, str]:
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def need(runner, argv: list[str], cwd=None) -> str:
    rc, out = runner(argv, cwd)
    if rc:
        sys.exit(f"ship: {' '.join(argv[:4])} failed\n{out.strip()}")
    return out


def gh_json(runner, *args: str):
    return json.loads(need(runner, ["gh", *args]) or "null")


def ci_state(info: dict) -> str:
    """`ci-ok` on the PR's current head: SUCCESS, FAILURE, ... or `pending` / `missing`."""
    for c in info.get("statusCheckRollup") or []:
        if c.get("name") == CI_CHECK:
            return c.get("conclusion") or "pending" if c.get("status") == "COMPLETED" else "pending"
    return "missing"


def stacked_on(runner, branch: str) -> list[dict]:
    """The open PRs whose base is `branch`."""
    return gh_json(runner, "pr", "list", "--base", branch, "--state", "open", "--json", "number,headRefName")


def pr_info(runner, pr: int) -> dict:
    return gh_json(runner, "pr", "view", str(pr), "--json", PR_FIELDS)


def ready_line(info: dict, stacked: list[dict]) -> str:
    on_top = ",".join(f"#{s['number']}" for s in stacked) or "-"
    return (f"#{info['number']} head {info['headRefOid'][:10]} ci-ok {ci_state(info)} mergeable {info['mergeable']} "
            f"draft {str(info['isDraft']).lower()} base {info['baseRefName']} state {info['state']} stacked {on_top}")


def blockers(info: dict) -> list[str]:
    out = []
    if info["state"] != "OPEN":
        out.append(f"the PR is {info['state']}")
    if info["isDraft"]:
        out.append("the PR is a draft")
    if (ci := ci_state(info)) != "SUCCESS":
        out.append(f"{CI_CHECK} is {ci} on the current head")
    if info["mergeable"] != "MERGEABLE":
        out.append(f"the PR is {info['mergeable'].lower()}, not mergeable")
    return out


def cmd_ready(runner, prs: list[int]) -> int:
    for pr in prs:
        info = pr_info(runner, pr)
        print(ready_line(info, stacked_on(runner, info["headRefName"])))
    return 0


def wait_for_main_ci(runner, base: str, sha: str, sleep=time.sleep, now=time.monotonic,
                     timeout: float = MAIN_CI_TIMEOUT) -> str:
    """The conclusion of the `ci` run of commit `sha` on `base`: waits for the run to appear and to finish."""
    deadline = now() + timeout
    while now() < deadline:
        runs = gh_json(runner, "run", "list", "--workflow", "ci", "--branch", base, "--commit", sha,
                       "--json", "status,conclusion,url")
        if runs and all(r["status"] == "completed" for r in runs):
            bad = [r for r in runs if r["conclusion"] != "success"]
            return bad[0]["conclusion"] if bad else "success"
        sleep(POLL)
    return "timeout"


def emulator_busy(runner, repo: Path) -> bool:
    out = need(runner, [sys.executable, "tools/live/queue.py", "status", "--resource", "emulator"], repo)
    return "free" not in out.split()


def cmd_land(runner, pr: int, go: bool, sleep=time.sleep, repo: Path | None = None) -> int:
    repo = repo or main_checkout()
    info = pr_info(runner, pr)
    if problems := blockers(info):
        print(f"ship: #{pr} is not ready: " + "; ".join(problems), file=sys.stderr)
        return 1
    branch, base, head = info["headRefName"], info["baseRefName"], info["headRefOid"]
    stacked = stacked_on(runner, branch)
    if not go:
        print(f"ship: #{pr} head {head[:10]} is ready. Would merge into {base}, retarget "
              f"{[s['number'] for s in stacked] or 'no PR'} and wait for main CI. Add --go.")
        return 0
    need(runner, ["gh", "pr", "merge", str(pr), "--merge", "--match-head-commit", head])
    for s in stacked:  # before the branch goes, or GitHub closes them
        need(runner, ["gh", "pr", "edit", str(s["number"]), "--base", base])
    if not info["isCrossRepository"]:
        need(runner, ["gh", "api", "-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/refs/heads/{branch}"])
    sha = gh_json(runner, "pr", "view", str(pr), "--json", "mergeCommit")["mergeCommit"]["oid"]
    print(f"ship: #{pr} merged as {sha[:10]}; waiting for CI on {base}", flush=True)
    if (result := wait_for_main_ci(runner, base, sha, sleep)) != "success":
        print(f"ship: CI of {sha[:10]} on {base} is {result}. Do not land another PR.", file=sys.stderr)
        return 1
    later = "uv run python tools/after_land.py"
    if emulator_busy(runner, repo):
        print(f"ship: green. The emulator queue has a holder (install/ is in use); run later in the main checkout: {later}")
        return 0
    rc, out = runner([sys.executable, "tools/after_land.py"], repo)
    print(out.strip())
    if rc:
        print("ship: green, but after_land failed", file=sys.stderr)
    return rc


def worktree_of(runner, repo: Path, branch: str) -> Path | None:
    """The worktree that has `branch` checked out."""
    path = None
    for line in need(runner, ["git", "worktree", "list", "--porcelain"], repo).splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def open_pr_of(runner, branch: str) -> list[dict]:
    return gh_json(runner, "pr", "list", "--head", branch, "--state", "open", "--json", "number")


def draft_pr(runner, integration: str, base: str = "main") -> str:
    fd, name = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    body = Path(name)
    body.write_text(f"Integration branch `{integration}`. Each merge into it runs the checks first, so CI runs "
                    "here from the first merge. Draft until the branch is ready to land.\n", encoding="utf-8")
    try:
        return need(runner, ["gh", "pr", "create", "--draft", "--base", base, "--head", integration,
                             "--title", f"Integration: {integration}", "--body-file", str(body)]).strip()
    finally:
        body.unlink(missing_ok=True)


def cmd_into(runner, integration: str, branch: str, repo: Path | None = None) -> int:
    repo = repo or main_checkout()
    need(runner, ["git", "fetch", "origin"], repo)
    tree = worktree_of(runner, repo, integration)
    if tree is None:
        tree = local_dir("scratch", f"into-{re.sub(r'[^\w.-]', '_', integration)}") / "wt"
        need(runner, ["git", "worktree", "add", str(tree), integration], repo)
    if need(runner, ["git", "status", "--porcelain", "--untracked-files=no"], tree).strip():
        sys.exit(f"ship: the worktree of {integration} has local changes ({tree})")
    need(runner, ["git", "merge", "--ff-only", f"origin/{integration}"], tree)
    before = need(runner, ["git", "rev-parse", "HEAD"], tree).strip()
    rc, out = runner(["git", "merge", "--no-ff", "-m", f"Merge {branch} into {integration}", f"origin/{branch}"], tree)
    if rc:
        conflicts = need(runner, ["git", "diff", "--name-only", "--diff-filter=U"], tree).split()
        need(runner, ["git", "merge", "--abort"], tree)
        print(f"ship: merging {branch} into {integration} conflicts in: {', '.join(conflicts) or out.strip()}", file=sys.stderr)
        return 1
    need(runner, ["uv", "run", "python", "tools/fetch_ocr.py"], tree)
    rc, out = runner(["uv", "run", "python", "tools/live/queue.py", "run", "--resource", "bench", "--name",
                      f"into-{branch}", "--", "uv", "run", "python", "tools/check.py"], tree)
    print(out.strip()[-3000:])
    if rc:
        need(runner, ["git", "reset", "--hard", before], tree)
        print(f"ship: the checks failed with {branch} merged; {integration} is as it was, nothing pushed", file=sys.stderr)
        return 1
    need(runner, ["git", "push", "origin", integration], tree)
    if not open_pr_of(runner, integration):
        print(f"ship: opened {draft_pr(runner, integration)}")
    print(f"ship: {branch} merged into {integration} and pushed")
    return 0


def main(argv=None, runner=run) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ready").add_argument("prs", type=int, nargs="+")
    land = sub.add_parser("land")
    land.add_argument("pr", type=int)
    land.add_argument("--go", action="store_true", help="merge; without it only say what would happen")
    into = sub.add_parser("into")
    into.add_argument("integration")
    into.add_argument("branch")
    a = ap.parse_args(argv)
    if a.cmd == "ready":
        return cmd_ready(runner, a.prs)
    if a.cmd == "land":
        return cmd_land(runner, a.pr, a.go)
    return cmd_into(runner, a.integration, a.branch)


if __name__ == "__main__":
    sys.exit(main())
