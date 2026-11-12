"""Which tests a branch adds or changes still pass on its base commit (CODING_STANDARDS.md "Recognition": a check proves the change).

  uv run python tools/red_check.py <base>      # e.g. origin/main

Runs the branch's tests/ files against the base's code in a temporary worktree and lists every added or changed test
that passes there. Such a test proves nothing about the change, unless it guards behaviour the base already has: say
so in the PR. The branch's test data goes along (every file it adds or edits under tests/, screenshots too, and
maatools.config.mts), so a test fails on the base for the base's code, not for a missing picture (#541). The rest are
listed in two groups: red (the test failed there) and could not read data (a file it opens outside assets/ is missing
there, or it skipped, so the run proves nothing). Exit code 1 when one passes on the base or could not read its data.
"""
import ast
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import dir_link

ROOT = Path(__file__).resolve().parent.parent
OCR = Path("assets/resource/base/model/ocr")  # gitignored; the base worktree borrows this checkout's
TEST_DATA = ("tests", "maatools.config.mts")  # what the branch's tests read, copied over the base
# A test that raised this read no data on the base; a file missing under assets/ is the base's code, so it stays red.
# Matched at the start (`DID NOT RAISE <class 'FileNotFoundError'>` is a failed assertion), so a fixture's error, which
# junit quotes after a prefix (`failed on setup with "FileNotFoundError: ..."`), spells the prefix out.
NO_DATA_ERROR = re.compile(r"(?:failed on setup with \")?FileNotFoundError\b(?!.*\bassets[\\/])")


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=check).stdout


def changed_lines(base: str) -> dict[str, set[int]]:
    """New-side line numbers each tests/ file of the branch adds or edits, from the merge base to HEAD."""
    lines: dict[str, set[int]] = {}
    path = ""
    # R: a moved and edited file's hunks name only its edited lines (a pure move has no hunk, so no test of it is listed)
    for line in git("diff", "-U0", "--no-color", "--diff-filter=AMR", f"{base}...HEAD", "--", "tests").splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif path and (m := re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))?", line)):
            start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
            lines.setdefault(path, set()).update(range(start, start + count))
    return lines


def changed_files(base: str) -> list[str]:
    """Every file under TEST_DATA the branch adds or edits, binary ones too (a diff's line numbers skip those)."""
    return git("diff", "--name-only", "--no-color", "--no-renames", "--diff-filter=AM", f"{base}...HEAD", "--", *TEST_DATA).splitlines()


def changed_tests(source: str, lines: set[int], path: str) -> list[str]:
    """pytest ids of the test functions in `source` (a module) whose span holds a changed line."""
    ids = []

    def visit(body, prefix):
        for node in body:
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                visit(node.body, prefix + node.name + "::")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                span = range(min([node.lineno, *(d.lineno for d in node.decorator_list)]), node.end_lineno + 1)
                if lines.intersection(span):
                    ids.append(f"{path}::{prefix}{node.name}")

    visit(ast.parse(source).body, "")
    return ids


OUTCOMES = PASS, RED, NO_DATA = "passes on", "red on", "could not read data on"  # each one's report line, worst last


def outcomes(junit: Path) -> dict[tuple[str, str], str]:
    """(test module, function) -> PASS, RED or NO_DATA from a junit file. A parametrized test passes when all its cases do;
    one case that could not read its data or was skipped (it did not run) makes it NO_DATA, otherwise one failed case RED."""
    results: dict[tuple[str, str], str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        module = next((part for part in case.get("classname", "").split(".") if part.startswith("test_")), "")
        key = (module, case.get("name", "").split("[")[0])
        bad = [child for child in case if child.tag in ("failure", "error", "skipped")]
        no_data = any(c.tag == "skipped" or NO_DATA_ERROR.match(c.get("message", "")) for c in bad)
        outcome = PASS if not bad else NO_DATA if no_data else RED
        results[key] = max(results.get(key, PASS), outcome, key=OUTCOMES.index)
    return results


def main(base: str) -> int:
    lines = changed_lines(base)
    wanted = [i for path, ls in sorted(lines.items()) if Path(path).name.startswith("test_") and path.endswith(".py")
              for i in changed_tests((ROOT / path).read_text(encoding="utf-8"), ls, path)]
    if not wanted:
        print("red_check: no test added or changed")
        return 0
    with tempfile.TemporaryDirectory(prefix="red-check-") as tmp:
        work = Path(tmp) / "base"
        git("worktree", "add", "--detach", str(work), base)
        try:
            for path in changed_files(base):  # the branch's tests, fixtures and screens, over the base's code
                (work / path).parent.mkdir(parents=True, exist_ok=True)
                (work / path).write_bytes(subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, check=True).stdout)
            if (ROOT / OCR).exists() and not (work / OCR).exists():
                (work / OCR).parent.mkdir(parents=True, exist_ok=True)  # the gitignored model, reachable from the base worktree
                dir_link.link(work / OCR, ROOT / OCR)
            results: dict[tuple[str, str], str] = {}
            for n, path in enumerate(sorted({w.split("::")[0] for w in wanted})):  # one run per file: a module that does not import
                junit = Path(tmp) / f"result{n}.xml"                                # on the base must not stop the others
                subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
                                *(w for w in wanted if w.split("::")[0] == path)], cwd=work, capture_output=True, text=True, encoding="utf-8")
                results |= outcomes(junit) if junit.exists() else {}
        finally:
            dir_link.unlink(work / OCR)  # the link only, never the model behind it
            git("worktree", "remove", "--force", str(work), check=False)
    keys = {(Path(w.split("::")[0]).stem, w.split("::")[-1]) for w in wanted}
    group = {outcome: sorted(k for k in keys if results.get(k, RED) == outcome) for outcome in OUTCOMES}
    for outcome in OUTCOMES:
        for module, name in group[outcome]:
            print(f"{outcome} {base}: {module}::{name}")
    print(f"red_check: {len(keys)} test(s) added or changed, {len(group[PASS])} pass on {base}, {len(group[RED])} red, "
          f"{len(group[NO_DATA])} could not read data")
    return 1 if group[PASS] or group[NO_DATA] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
