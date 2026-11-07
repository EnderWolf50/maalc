"""Every local check, one summary line each with its exit code and seconds: ruff, pytest, maa-tools check, maa-tools test.

  uv run python tools/check.py

pytest runs as SHARDS processes at once, SHARD=i of SHARDS each: tests/conftest.py splits the test files as it does for
CI's agent shards (#484). A failing step prints the last 15 lines of its output, of each failing shard for pytest.
Exit code = number of failed steps.
A worktree without the gitignored OCR model gets it from `fetch_ocr.py` first, since every OCR test fails without it.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STEPS = [["uv", "run", "ruff", "check"], ["uv", "run", "pytest", "-q"],
         ["pnpm", "exec", "maa-tools", "check"], ["pnpm", "exec", "maa-tools", "test"]]
# CI's agent shards (.github/workflows/ci.yml); most of a child test's time is waiting, so they share the cores well.
SHARDS = min(4, os.cpu_count() or 1)
TAIL = 15


def tail(out):
    out = re.sub(r"[^\n]*\r(?!\n)", "", out)  # drop progress-bar frames
    return "\n".join([line for line in out.splitlines() if line.strip()][-TAIL:])


def run_step(step, shards=1, popen=subprocess.Popen):
    """(exit code, output to show) of one step. With shards > 1 it starts that many processes at once, SHARD=i of
    SHARDS=shards in each one's environment; the code is the first failing shard's, the output each failing shard's
    tail under its name. Output goes to files, not pipes, so a shard that writes much never blocks on a full pipe."""
    cmd = [shutil.which(step[0]) or step[0], *step[1:]]
    with tempfile.TemporaryDirectory() as folder:
        started = []
        for i in range(shards):
            out = open(Path(folder) / f"{i}.log", "w+", encoding="utf-8", errors="replace")
            env = {**os.environ, "SHARDS": str(shards), "SHARD": str(i)} if shards > 1 else None
            started.append((i, out, popen(cmd, stdout=out, stderr=subprocess.STDOUT, env=env)))
        code, shown = 0, []
        for i, out, process in started:
            returned = process.wait()
            out.seek(0)
            text = out.read()
            out.close()
            if returned:
                code = code or returned
                shown.append((f"-- shard {i} of {shards}\n" if shards > 1 else "") + tail(text))
    return code, "\n".join(shown)


def main():
    ocr_dir = Path(__file__).resolve().parent.parent / "assets/resource/base/model/ocr"
    if not all((ocr_dir / name).exists() for name in ("det.onnx", "rec.onnx", "keys.txt")):
        print("== OCR model missing: uv run python tools/fetch_ocr.py", flush=True)
        if subprocess.run([sys.executable, str(Path(__file__).with_name("fetch_ocr.py"))]).returncode:
            sys.exit("fetch_ocr.py failed; the OCR tests cannot run without the model")
    failed = 0
    for step in STEPS:
        shards = SHARDS if step[2] == "pytest" else 1
        began = time.monotonic()
        code, shown = run_step(step, shards)
        label = " ".join(step) + (f" ({shards} shards)" if shards > 1 else "")
        print(f"== {label}: exit {code}, {time.monotonic() - began:.0f} s", flush=True)
        if code:
            print(shown, flush=True)
            failed += 1
    return failed


if __name__ == "__main__":
    sys.exit(main())
