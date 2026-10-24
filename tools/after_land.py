"""Rebuild the user's `install/` in the main checkout after a PR landed.

  uv run python tools/after_land.py

Run it from the main checkout. It refuses while a task holds the emulator queue (a live run is using
`install/`), fast-forwards the checkout to `origin/main` (refusing off main, with local changes, or when
it cannot fast-forward), then builds the settings GUI, fetches the OCR model and its plate copy (what is
there is skipped), assembles `install/` and checks that `install/config/settings.json` still loads. Stops at the first failing step.
"""
import shutil
import subprocess
import sys

from local_dir import main_checkout

REPO = main_checkout()


def step(label: str, *cmd: str) -> None:
    print(f"== {label}", flush=True)
    if subprocess.run([shutil.which(cmd[0]) or cmd[0], *cmd[1:]], cwd=REPO).returncode:
        sys.exit(f"after_land: '{label}' failed")


def run_git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def sync_main(git=run_git) -> None:
    """Fetch and fast-forward the checkout's `main`, so the install holds every merged PR."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD")[1].strip()
    if branch != "main":
        sys.exit(f"after_land: the checkout is on '{branch}', not on main")
    if git("status", "--porcelain", "--untracked-files=no")[1].strip():
        sys.exit("after_land: the checkout is not clean; commit or stash its changes first")
    for args, what in ((("fetch", "origin"), "git fetch origin failed"),
                       (("pull", "--ff-only", "origin", "main"), "main cannot fast-forward to origin/main")):
        rc, out = git(*args)
        if rc:
            sys.exit(f"after_land: {what}\n{out.strip()}")


def main() -> None:
    held = list((REPO / ".local/queue/emulator").glob("*.ticket"))
    if held:
        sys.exit(f"after_land: the emulator queue holds {len(held)} ticket(s); install/ is in use. Run tools/live/queue.py status.")
    sync_main()
    step("build the settings GUI", "pnpm", "--dir", "gui", "tauri", "build", "--no-bundle")
    step("the OCR model and its plate copy (#329)", sys.executable, "tools/fetch_ocr.py")  # skips what is there
    step("assemble install/", sys.executable, "tools/install.py")
    step("install/config/settings.json loads", sys.executable, "-c",
         "import sys; sys.path.insert(0, 'agent'); from settings import load_settings; load_settings('install')")


if __name__ == "__main__":
    main()
