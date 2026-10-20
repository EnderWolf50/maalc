"""Every local check, one summary line each: ruff, pytest, maa-tools check, maa-tools test.

  uv run python tools/check.py

A failing step prints the last 15 lines of its output. Exit code = number of failed steps.
"""
import re
import shutil
import subprocess
import sys

STEPS = [["uv", "run", "ruff", "check"], ["uv", "run", "pytest", "-q"],
         ["pnpm", "exec", "maa-tools", "check"], ["pnpm", "exec", "maa-tools", "test"]]

failed = 0
for step in STEPS:
    r = subprocess.run([shutil.which(step[0]) or step[0], *step[1:]], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = re.sub(r"[^\n]*\r(?!\n)", "", r.stdout + r.stderr)  # drop progress-bar frames
    print(f"== {' '.join(step)}: exit {r.returncode}")
    if r.returncode:
        print("\n".join([line for line in out.splitlines() if line.strip()][-15:]))
        failed += 1
sys.exit(failed)
