"""Rebuild the user's `install/` in the main checkout after a PR landed.

  uv run python tools/after_land.py

Run it from the main checkout once `ship`'s land has pulled `main`. It refuses while a task holds the
emulator queue (a live run is using `install/`), then builds the settings GUI, assembles `install/`
and checks that `install/config/settings.json` still loads. Stops at the first failing step.
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


def main() -> None:
    held = list((REPO / ".local/queue/emulator").glob("*.ticket"))
    if held:
        sys.exit(f"after_land: the emulator queue holds {len(held)} ticket(s); install/ is in use. Run tools/live/queue.py status.")
    step("build the settings GUI", "pnpm", "--dir", "gui", "tauri", "build", "--no-bundle")
    step("assemble install/", sys.executable, "tools/install.py")
    step("install/config/settings.json loads", sys.executable, "-c",
         "import sys; sys.path.insert(0, 'agent'); from settings import load_settings; load_settings('install')")


if __name__ == "__main__":
    main()
