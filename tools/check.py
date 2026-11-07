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


def pytest_shards(cores):
    """One pytest shard per 4 cores, at most 4: CI gives each shard a 4-vCPU runner, where two MaaFramework children at
    once outlast run_child's timeout (.github/workflows/ci.yml, the agent job)."""
    return max(1, min(4, cores // 4))


SHARDS = pytest_shards(os.cpu_count() or 4)
# (command, processes at once). pytest leaves its cache alone: the shards would overwrite each other's.
STEPS = [(["uv", "run", "ruff", "check"], 1), (["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"], SHARDS),
         (["pnpm", "exec", "maa-tools", "check"], 1), (["pnpm", "exec", "maa-tools", "test"], 1)]
TAIL = 15


def tail(out):
    out = re.sub(r"[^\n]*\r(?!\n)", "", out)  # drop progress-bar frames
    return "\n".join([line for line in out.splitlines() if line.strip()][-TAIL:])


def stop(process):
    """End a process left running and what it started: killing `uv run` alone leaves its pytest going on Windows."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.kill()
    process.wait()


def run_step(cmd, shards=1, popen=subprocess.Popen, stop=stop):
    """(exit code, output to show) of one step. With shards > 1 it starts that many processes at once, SHARD=i of
    SHARDS=shards in each one's environment; the code is the first failing shard's, the output each failing shard's
    tail under its name. Output goes to files, not pipes, so a shard that writes much never blocks on a full pipe.
    A start that fails, or Ctrl-C, ends the shards already running before the error goes on."""
    cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
    with tempfile.TemporaryDirectory() as folder:
        outs, processes = [], []
        try:
            for i in range(shards):
                outs.append(open(Path(folder) / f"{i}.log", "w+", encoding="utf-8", errors="replace"))
                env = {**os.environ, "SHARDS": str(shards), "SHARD": str(i)} if shards > 1 else None
                processes.append(popen(cmd, stdout=outs[-1], stderr=subprocess.STDOUT, env=env))
            codes = [process.wait() for process in processes]
            texts = []
            for out in outs:
                out.seek(0)
                texts.append(out.read())
        finally:
            for process in processes:
                if process.poll() is None:
                    stop(process)
            for out in outs:
                out.close()
    shown = [(f"-- shard {i} of {shards}\n" if shards > 1 else "") + tail(text)
             for i, (code, text) in enumerate(zip(codes, texts)) if code]
    return next((code for code in codes if code), 0), "\n".join(shown)


def main(run=run_step):
    ocr_dir = Path(__file__).resolve().parent.parent / "assets/resource/base/model/ocr"
    if not all((ocr_dir / name).exists() for name in ("det.onnx", "rec.onnx", "keys.txt")):
        print("== OCR model missing: uv run python tools/fetch_ocr.py", flush=True)
        if subprocess.run([sys.executable, str(Path(__file__).with_name("fetch_ocr.py"))]).returncode:
            sys.exit("fetch_ocr.py failed; the OCR tests cannot run without the model")
    failed = 0
    for cmd, shards in STEPS:
        began = time.monotonic()
        code, shown = run(cmd, shards)
        label = " ".join(cmd) + (f" ({shards} shards)" if shards > 1 else "")
        print(f"== {label}: exit {code}, {time.monotonic() - began:.0f} s", flush=True)
        if code:
            print(shown, flush=True)
            failed += 1
    return failed


if __name__ == "__main__":
    sys.exit(main())
