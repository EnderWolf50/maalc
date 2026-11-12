"""Merge pull requests one at a time and test integration merges.

  uv run python tools/ship.py ready <pr>...
  uv run python tools/ship.py land <pr>... --go [--onto-red <pr>]
  uv run python tools/ship.py into <integration-branch> <branch>

`ready` prints one line per PR: head SHA, `ci-ok` state, mergeable, draft, base and the open PRs stacked on its branch.

`land` merges each PR (merge commit) once `ci-ok` passed on its current head and it is mergeable (an UNKNOWN
mergeable, which GitHub reports for a few seconds after a merge into the base or a retarget, is read again every 5 s
for up to a minute). A PR into main also waits for the CI run of main's head and is not merged when that run is not
green. It retargets every PR stacked on the branch to the base before deleting the branch, waits for the CI run of
the merge commit on the base branch and exits non-zero when that run is red. Several PRs land in the given order;
the first that is not ready, finds main red, fails to merge or turns main red stops the batch, and the PRs after it
are not started. Once the batch ends with main green, `tools/after_land.py` runs once in the main checkout, unless
the emulator queue has a holder (`install/` is in use): then the command to run later is printed.
A main red from an outside failure (a GitHub 504) gets a rerun of its CI. `--onto-red <pr>` skips the check of
main's head for that one PR: use it only for the PR that fixes a red main.
Calls with `--go` take turns in the land lane (`<main checkout>/.local/queue/land/`, a `tools/live/queue.py` queue):
each holds its ticket for the whole batch, `after_land.py` included. A call that has to wait prints once
`ship: waiting for pid <pid> (ship.py land #<pr>...) to end before landing #<pr>...` and starts when that call ends,
whether it landed or stopped. The ticket of a call whose process is gone is dropped, so the next call takes over.
A call whose own ticket is removed while it waits exits 1, says so and lands nothing. A dry run (no `--go`) never
waits for a turn.

`into` merges `<branch>` into the integration branch (`--no-ff`) in a worktree of it and pushes it; a conflict
leaves the branch as it was. The checks run in CI on the integration branch's draft PR, not on this machine (#636):
the first merge into an integration branch with no open PR opens it, and every `into` names the PR whose `ci-ok` to
wait for. A red `ci-ok` is fixed on the branch and merged in with another `into`.
"""
import argparse
import enum
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path

from live.queue import holders, turn
from local_dir import local_dir, main_checkout

CI_CHECK = "ci-ok"
PR_FIELDS = "number,state,isDraft,mergeable,baseRefName,headRefName,headRefOid,isCrossRepository,statusCheckRollup"
MAIN_CI_TIMEOUT = 45 * 60
POLL = 30.0
MERGEABLE_POLL = 5.0
MERGEABLE_READS = 12


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


def emulator_busy(repo: Path) -> bool:
    return bool(holders(repo / ".local" / "queue" / "emulator"))


class Outcome(enum.Enum):
    REFUSED = enum.auto()
    PREVIEWED = enum.auto()
    INTO_STACK = enum.auto()
    GREEN = enum.auto()
    RED = enum.auto()


STOPS = {Outcome.REFUSED, Outcome.RED}


def land_one(runner, pr: int, go: bool, sleep=time.sleep, onto_red: bool = False) -> Outcome:
    info = pr_info(runner, pr)
    for _ in range(MERGEABLE_READS - 1):  # GitHub recomputes `mergeable` for a few seconds after the base moves
        if info["mergeable"] != "UNKNOWN" or blockers({**info, "mergeable": "MERGEABLE"}):  # a merged PR stays UNKNOWN
            break
        sleep(MERGEABLE_POLL)
        info = pr_info(runner, pr)
    if problems := blockers(info):
        print(f"ship: #{pr} is not ready: " + "; ".join(problems), file=sys.stderr)
        return Outcome.REFUSED
    branch, base, head = info["headRefName"], info["baseRefName"], info["headRefOid"]
    stacked = stacked_on(runner, branch)
    if not go:
        print(f"ship: #{pr} head {head[:10]} is ready. Would merge into {base}, retarget "
              f"{[s['number'] for s in stacked] or 'no PR'} and wait for main CI. Add --go.")
        return Outcome.PREVIEWED
    if base == "main" and not onto_red:
        main_sha = gh_json(runner, "api", f"repos/{{owner}}/{{repo}}/git/ref/heads/{base}")["object"]["sha"]
        if (state := wait_for_main_ci(runner, base, main_sha, sleep)) != "success":
            print(f"ship: #{pr} not merged: CI of {base}'s head {main_sha[:10]} is {state}. Rerun its CI when an outside "
                  f"failure (a GitHub 504) turned it red; land the PR that fixes {base} with --onto-red <pr>.",
                  file=sys.stderr)
            return Outcome.RED
    rc, out = runner(["gh", "pr", "merge", str(pr), "--merge", "--match-head-commit", head])
    if rc:  # GitHub can still refuse (the head moved): nothing merged, so it stops the batch like a blocker
        print(f"ship: gh pr merge {pr} failed\n{out.strip()}", file=sys.stderr)
        return Outcome.REFUSED
    for s in stacked:  # before the branch goes, or GitHub closes them
        need(runner, ["gh", "pr", "edit", str(s["number"]), "--base", base])
    if not info["isCrossRepository"]:
        need(runner, ["gh", "api", "-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/refs/heads/{branch}"])
    sha = gh_json(runner, "pr", "view", str(pr), "--json", "mergeCommit")["mergeCommit"]["oid"]
    if base != "main":  # ci.yml runs on pushes to main only: a stacked base gets no run to wait for
        print(f"ship: #{pr} merged as {sha[:10]} into {base}, which has no push CI; the stack's last PR lands on main")
        return Outcome.INTO_STACK
    print(f"ship: #{pr} merged as {sha[:10]}; waiting for CI on {base}", flush=True)
    if (result := wait_for_main_ci(runner, base, sha, sleep)) != "success":
        print(f"ship: CI of {sha[:10]} on {base} is {result}. Do not land another PR.", file=sys.stderr)
        return Outcome.RED
    return Outcome.GREEN


def waiting_line(ahead: list[tuple[str, str]], prs: list[int]) -> str:
    calls = ", ".join(f"pid {pid} ({cmd})" for pid, cmd in ahead)
    return f"ship: waiting for {calls} to end before landing {' '.join(f'#{p}' for p in prs)}"


def cmd_land(runner, prs: list[int], go: bool, sleep=time.sleep, repo: Path | None = None,
             onto_red: int | None = None) -> int:
    repo = repo or main_checkout()
    lane = turn(repo / ".local" / "queue" / "land", "land", ["ship.py", "land", *(f"#{p}" for p in prs)], sleep=sleep,
                on_wait=lambda ahead: print(waiting_line(ahead, prs), flush=True)) if go else nullcontext()
    with lane:
        outcomes = []
        for i, pr in enumerate(prs):
            outcomes.append(land_one(runner, pr, go, sleep, onto_red=pr == onto_red))
            if outcomes[-1] in STOPS:
                if len(prs) > 1:
                    rest = ", ".join(f"#{p}" for p in prs[i + 1:]) or "none"
                    print(f"ship: stopped at #{pr}; not started: {rest}", file=sys.stderr)
                break
        stop_rc = int(outcomes[-1] in STOPS)
        if Outcome.GREEN not in outcomes or outcomes[-1] is Outcome.RED:
            return stop_rc
        later = "uv run python tools/after_land.py"
        if emulator_busy(repo):
            print(f"ship: green. The emulator queue has a holder (install/ is in use); run later in the main checkout: {later}")
            return stop_rc
        rc, out = runner(["uv", "run", "python", "tools/after_land.py"], repo)  # the main checkout's venv, not the caller's
        print(out.strip())
        if rc:
            print("ship: green, but after_land failed", file=sys.stderr)
        return rc or stop_rc


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
    body.write_text(f"整合分支 `{integration}`。這個 PR 的 CI 檢查每一次併入（`tools/ship.py into`），從第一次起。"
                    "分支可以合併前保持 draft。\n", encoding="utf-8")
    try:
        return need(runner, ["gh", "pr", "create", "--draft", "--base", base, "--head", integration,
                             "--title", f"chore: 整合分支 {integration}", "--body-file", str(body)]).strip()
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
        conflicts = runner(["git", "diff", "--name-only", "--diff-filter=U"], tree)[1].split()
        runner(["git", "merge", "--abort"], tree)  # none to abort when the merge failed before it started
        print(f"ship: merging {branch} into {integration} failed: "
              f"{'conflicts in ' + ', '.join(conflicts) if conflicts else out.strip()}", file=sys.stderr)
        return 1
    pushed = False
    try:
        need(runner, ["git", "push", "origin", integration], tree)
        pushed = True
    finally:
        if not pushed:  # a merge that was not pushed must not ride along with the next `into`
            runner(["git", "reset", "--hard", before], tree)
    print(f"ship: {branch} merged into {integration} and pushed")
    if prs := open_pr_of(runner, integration):
        print(f"ship: CI checks it on #{prs[0]['number']}: gh pr checks {prs[0]['number']} --watch")
    else:
        print(f"ship: opened {draft_pr(runner, integration)}; its CI checks the merge")
    return 0


def main(argv=None, runner=run) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ready").add_argument("prs", type=int, nargs="+")
    land = sub.add_parser("land")
    land.add_argument("prs", type=int, nargs="+")
    land.add_argument("--go", action="store_true", help="merge; without it only say what would happen")
    land.add_argument("--onto-red", type=int, metavar="PR",
                      help="merge this PR even when the CI of main's head is not green: only the PR that fixes a red "
                           "main. A main red from an outside failure (a GitHub 504) gets a rerun of its CI instead")
    into = sub.add_parser("into")
    into.add_argument("integration")
    into.add_argument("branch")
    a = ap.parse_args(argv)
    if a.cmd == "ready":
        return cmd_ready(runner, a.prs)
    if a.cmd == "land":
        if a.onto_red is not None and a.onto_red not in a.prs:
            ap.error(f"--onto-red {a.onto_red} is not one of the PRs to land")
        return cmd_land(runner, a.prs, a.go, onto_red=a.onto_red)
    return cmd_into(runner, a.integration, a.branch)


if __name__ == "__main__":
    sys.exit(main())
