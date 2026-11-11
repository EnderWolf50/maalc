"""Every local check, one summary line each with its exit code and seconds: ruff, review_lint, pytest, maa-tools check,
maa-tools test.

  uv run python tools/check.py

pytest runs as SHARDS processes at once, SHARD=i of SHARDS each: tests/conftest.py splits the test files as it does for
CI's agent shards (#484). A failing step prints the last 15 lines of its output, of each failing shard for pytest.
Exit code = number of failed steps.
review_lint (CI's review-lint job, #628) compares the branch with origin/main; a checkout without that ref skips it and
prints why (run `git fetch origin main`).
A worktree without the gitignored OCR model gets it from `fetch_ocr.py` first, since every OCR test fails without it.
Each run appends one JSON line to `<main checkout>/.local/check-runs.jsonl` (#633): see record() and docs/agents/local-dev.md
"Checks". tools/check_stats.py summarises the file. A log that cannot be written is a warning, never a failed run.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import local_dir
import shard_seconds

ROOT = Path(__file__).resolve().parent.parent
LOG_NAME = "check-runs.jsonl"


def pytest_shards(cores):
    """One pytest shard per 4 cores, at most 4: CI gives each shard a 4-vCPU runner, where two MaaFramework children at
    once outlast run_child's timeout (.github/workflows/ci.yml, the agent job)."""
    return max(1, min(4, cores // 4))


SHARDS = pytest_shards(os.cpu_count() or 4)
BASE = "origin/main"
# (command, processes at once). pytest leaves its cache alone: the shards would overwrite each other's.
RUFF = (["uv", "run", "ruff", "check"], 1)
REVIEW_LINT = (["uv", "run", "python", "tools/review_lint.py", BASE], 1)
PYTEST = ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"]
STEPS = [RUFF, (PYTEST, SHARDS), (["pnpm", "exec", "maa-tools", "check"], 1), (["pnpm", "exec", "maa-tools", "test"], 1)]
# pytest also gets this: {shard} becomes the shard's number, so each shard writes its own junit file, which gives the log
# the seconds of every test file and the failed tests (as CI's shard-balance reads its junit artifacts).
JUNIT = "--junitxml={junit}/{{shard}}.xml"
TAIL = 15
ANSI = re.compile(r"\x1b\[[0-9;]*m")
MAA_FAIL = re.compile(r"^\s+(\S+) (\S+) (should hit but missed|should missed but hit|box mismatch|missing detail)")


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


class Shown(str):
    """The text of a failing step to print; .texts is the whole output of every shard, for the log."""
    texts = ()


def run_step(cmd, shards=1, popen=subprocess.Popen, stop=stop):
    """(exit code, output to show) of one step. With shards > 1 it starts that many processes at once, SHARD=i of
    SHARDS=shards in each one's environment; the code is the first failing shard's, the output each failing shard's
    tail under its name. {shard} in an argument becomes the shard's number. Output goes to files, not pipes, so a shard
    that writes much never blocks on a full pipe.
    A start that fails, or Ctrl-C, ends the shards already running before the error goes on."""
    template = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
    with tempfile.TemporaryDirectory() as folder:
        outs, processes = [], []
        try:
            for i in range(shards):
                outs.append(open(Path(folder) / f"{i}.log", "w+", encoding="utf-8", errors="replace"))
                env = {**os.environ, "SHARDS": str(shards), "SHARD": str(i)} if shards > 1 else None
                args = [arg.replace("{shard}", str(i)) for arg in template]
                processes.append(popen(args, stdout=outs[-1], stderr=subprocess.STDOUT, env=env))
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
    shown = Shown("\n".join((f"-- shard {i} of {shards}\n" if shards > 1 else "") + tail(text)
                            for i, (code, text) in enumerate(zip(codes, texts)) if code))
    shown.texts = tuple(texts)
    return next((code for code in codes if code), 0), shown


def has_base(ref):
    """Whether git knows `ref` here (an offline or never-fetched checkout has no origin/main)."""
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"], capture_output=True).returncode == 0


def junit_cases(folder):
    """(seconds per test file, node ids of the failed tests) from the junit files in `folder`; empty when pytest wrote
    none."""
    reports, failed = [], []
    for report in sorted(Path(folder).glob("*.xml")):
        try:
            cases = list(ET.parse(report).iter("testcase"))
        except (ET.ParseError, OSError):
            continue
        reports.append(report)
        for case in cases:
            if case.find("failure") is None and case.find("error") is None:
                continue
            parts = case.get("classname", "").split(".")
            at = next((n for n, part in enumerate(parts) if part.startswith("test_")), None)
            if at is None:
                failed.append(".".join(p for p in (*parts, case.get("name", "")) if p))
            else:
                failed.append("::".join(["/".join(parts[:at + 1]) + ".py", *parts[at + 1:], case.get("name", "")]))
    seconds = {name: round(took, 1) for name, took in shard_seconds.measured(reports).items()}
    return seconds, sorted(set(failed))


def maa_failures(texts):
    """The `maa-tools test` cases that went red, as `<image> <node>: <reason>`, from its failure lines."""
    return [f"{m[1]} {m[2]}: {m[3]}" for text in texts for line in ANSI.sub("", text).splitlines() if (m := MAA_FAIL.match(line))]


def git(*args, env=None):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
                          env={**os.environ, **env} if env else None).stdout


def work_tree_files(base):
    """{path: blob id} of every file the working tree (committed, staged, unstaged and untracked, not ignored) has
    different from `base`. Built in a throwaway index, so the checkout's own index stays as it is."""
    with tempfile.TemporaryDirectory() as folder:
        env = {"GIT_INDEX_FILE": str(Path(folder) / "index")}
        git("read-tree", "HEAD", env=env)
        git("add", "-A", env=env)
        raw = git("diff-index", "--cached", "--no-renames", "--raw", "-z", base, env=env).split("\0")
    return {path: meta.split()[3] for meta, path in zip(raw[0::2], raw[1::2]) if meta}


def checkout_state(has_base_ref):
    """Where the run happened: worktree, branch, HEAD, whether anything is uncommitted, and the files that differ from
    the point the branch left origin/main (the same change has the same blob ids in the next run, so the summary can
    tell what changed between two runs without the commits)."""
    head = git("rev-parse", "HEAD").strip()
    base = None
    if has_base_ref:
        try:
            base = git("merge-base", "HEAD", BASE).strip()
        except subprocess.CalledProcessError:  # a shallow clone, or histories that share nothing: no common point
            pass
    return {"worktree": git("rev-parse", "--show-toplevel").strip(), "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
            "base": base, "head": head, "dirty": bool(git("status", "--porcelain").strip()),
            "files": work_tree_files(base or head)}


def record(started, steps, junit_dir, maa_texts, has_base_ref, wall):
    """One run as a JSON-able dict (format: docs/agents/local-dev.md "Checks")."""
    seconds, failed_tests = junit_cases(junit_dir)
    return {"v": 1, "started": started.isoformat(timespec="seconds"), "seconds": round(wall, 1),
            **checkout_state(has_base_ref), "steps": steps, "failed_tests": failed_tests,
            "failed_maa": maa_failures(maa_texts), "test_seconds": seconds}


def append_record(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as out:
        out.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def default_log():
    return local_dir.main_checkout() / ".local" / LOG_NAME


def step_name(cmd):
    """`ruff`, `review_lint`, `pytest`, `maa-tools check` or `maa-tools test`."""
    if "maa-tools" in cmd:
        return "maa-tools " + cmd[-1]
    return "review_lint" if "tools/review_lint.py" in cmd else "pytest" if "pytest" in cmd else "ruff"


def main(run=run_step, has_base=has_base, log=default_log):
    """`log` gives the path of the run log, or is None to write none."""
    ocr_dir = ROOT / "assets/resource/base/model/ocr"
    if not all((ocr_dir / name).exists() for name in ("det.onnx", "rec.onnx", "keys.txt")):
        print("== OCR model missing: uv run python tools/fetch_ocr.py", flush=True)
        if subprocess.run([sys.executable, str(Path(__file__).with_name("fetch_ocr.py"))]).returncode:
            sys.exit("fetch_ocr.py failed; the OCR tests cannot run without the model")
    steps = STEPS[:1] + [REVIEW_LINT] + STEPS[1:]
    has_base_ref = has_base(BASE)
    if not has_base_ref:
        print(f"== tools/review_lint.py: skipped, no {BASE} to compare with (git fetch origin main)", flush=True)
        steps.remove(REVIEW_LINT)
    started, run_began, failed, logged, maa_texts = datetime.datetime.now().astimezone(), time.monotonic(), 0, [], ()
    with tempfile.TemporaryDirectory() as junit:
        for cmd, shards in steps:
            began = time.monotonic()
            code, shown = run(cmd + [JUNIT.format(junit=junit)] if cmd is PYTEST else cmd, shards)
            took = time.monotonic() - began
            label = " ".join(cmd) + (f" ({shards} shards)" if shards > 1 else "")
            print(f"== {label}: exit {code}, {took:.0f} s", flush=True)
            logged.append({"name": step_name(cmd), "exit": code, "seconds": round(took, 1)})
            if step_name(cmd) == "maa-tools test":
                maa_texts = getattr(shown, "texts", ())
            if code:
                print(shown, flush=True)
                failed += 1
        if log:
            try:
                append_record(log(), record(started, logged, junit, maa_texts, has_base_ref, time.monotonic() - run_began))
            except Exception as error:  # a log that cannot be written never fails the check
                print(f"== check log not written: {type(error).__name__}: {error}", flush=True)
    return failed


if __name__ == "__main__":
    sys.exit(main())
