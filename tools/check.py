"""Every local check, one summary line each: ruff, pytest, maa-tools check, maa-tools test.

  uv run python tools/check.py

A failing step prints the last 15 lines of its output. Exit code = number of failed steps.
A worktree without the gitignored OCR model gets it from `fetch_ocr.py` first, since every OCR test fails without it.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ocr_dir = Path(__file__).resolve().parent.parent / "assets/resource/base/model/ocr"
if not all((ocr_dir / name).exists() for name in ("det.onnx", "rec.onnx", "keys.txt")):
    print("== OCR model missing: uv run python tools/fetch_ocr.py", flush=True)
    if subprocess.run([sys.executable, str(Path(__file__).with_name("fetch_ocr.py"))]).returncode:
        sys.exit("fetch_ocr.py failed; the OCR tests cannot run without the model")

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
