"""Rebuild the user's `install/` in the main checkout after a PR landed.

  uv run python tools/after_land.py

Run it from the main checkout. It refuses while a task holds the emulator queue (a live run is using
`install/`), fast-forwards the checkout to `origin/main` (refusing off main, with local changes, or when
it cannot fast-forward), then builds the settings GUI, assembles `install/` and checks that `install/config/settings.json` still loads. Stops at the first failing step.
"""
import shutil
import subprocess
import sys

from local_dir import main_checkout

REPO = main_checkout()
# A fetch that lost a ref lock to another git's fetch did so after that one updated the ref, so the next fetch starts
# from the new value and passes unless the remote moved again: 90 races on a scratch repo needed 2 fetches at most.
FETCH_TRIES = 3


def step(label: str, *cmd: str) -> None:
    print(f"== {label}", flush=True)
    if subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], cwd=REPO).returncode:
        sys.exit(f"after_land: '{label}' failed")


def run_git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def sync_main(git=run_git) -> None:
    """Fetch and fast-forward the checkout's `main` to `origin/main`, so the install holds every merged PR.

    It merges `origin/main` instead of pulling: a pull merges what its own fetch wrote to FETCH_HEAD, and a
    `git fetch` run in this checkout at the same time rewrites that file ("Cannot fast-forward to multiple
    branches"). A failed fetch is made again; a failed merge still counts when `main` is at `origin/main`, as
    when another after_land's merge moved HEAD first ("cannot lock ref 'HEAD'").
    """
    branch = git("rev-parse", "--abbrev-ref", "HEAD")[1].strip()
    if branch != "main":
        sys.exit(f"after_land: the checkout is on '{branch}', not on main")
    if git("status", "--porcelain", "--untracked-files=no")[1].strip():
        sys.exit("after_land: the checkout is not clean; commit or stash its changes first")
    for _ in range(FETCH_TRIES):
        rc, out = git("fetch", "origin")
        if not rc:
            break
    else:
        sys.exit(f"after_land: git fetch origin failed\n{out.strip()}")
    rc, out = git("merge", "--ff-only", "origin/main")
    if rc and git("rev-parse", "HEAD")[1] != git("rev-parse", "origin/main")[1]:
        sys.exit(f"after_land: main cannot fast-forward to origin/main\n{out.strip()}")


def main() -> None:
    held = list((REPO / ".local/queue/emulator").glob("*.ticket"))
    if held:
        sys.exit(f"after_land: the emulator queue holds {len(held)} ticket(s); install/ is in use. Run tools/live/queue.py status.")
    sync_main()
    step("build the settings GUI", "pnpm", "--dir", "gui", "tauri", "build", "--no-bundle")
    step("assemble install/", sys.executable, "tools/install.py")
    step("install/config/settings.json loads", sys.executable, "-c",
         "import sys; sys.path.insert(0, 'agent'); from settings import load_settings; load_settings('install')")


if __name__ == "__main__":
    main()
