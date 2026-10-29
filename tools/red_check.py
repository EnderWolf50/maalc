"""Which tests a branch adds or changes still pass on its base commit (CODING_STANDARDS.md "Recognition": a check proves the change).

  uv run python tools/red_check.py <base>      # e.g. origin/main

Runs the branch's tests/ files against the base's code in a temporary worktree and lists every added or changed test
that passes there. Such a test proves nothing about the change, unless it guards behaviour the base already has: say
so in the PR. Exit code 1 when one passes on the base.
"""
import ast
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OCR = Path("assets/resource/base/model/ocr")  # gitignored; the base worktree borrows this checkout's


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=check).stdout


def changed_lines(base: str) -> dict[str, set[int]]:
    """New-side line numbers each tests/ file of the branch adds or edits, from the merge base to HEAD."""
    lines: dict[str, set[int]] = {}
    path = ""
    for line in git("diff", "-U0", "--no-color", "--diff-filter=AM", f"{base}...HEAD", "--", "tests").splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif path and (m := re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))?", line)):
            start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
            lines.setdefault(path, set()).update(range(start, start + count))
    return lines


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


def passed_keys(junit: Path) -> set[tuple[str, str]]:
    """(test module, function) of every test whose cases all passed in a junit file; one failed case of a parametrized test fails it."""
    results: dict[tuple[str, str], bool] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        module = next((part for part in case.get("classname", "").split(".") if part.startswith("test_")), "")
        key = (module, case.get("name", "").split("[")[0])
        ok = not any(child.tag in ("failure", "error", "skipped") for child in case)
        results[key] = results.get(key, True) and ok
    return {key for key, ok in results.items() if ok}


def link(source: Path, target: Path) -> None:
    """The gitignored OCR model of this checkout, reachable from the base worktree (a junction on Windows)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(source)], capture_output=True, check=True)
    else:
        target.symlink_to(source)


def unlink(target: Path) -> None:
    if sys.platform == "win32":  # rmdir on a junction removes the link, not the model behind it
        subprocess.run(["cmd", "/c", "rmdir", str(target)], capture_output=True)
    elif target.is_symlink():
        target.unlink()


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
            for path in lines:  # the branch's tests, fixtures and screens, over the base's code
                (work / path).parent.mkdir(parents=True, exist_ok=True)
                (work / path).write_bytes(subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, check=True).stdout)
            if (ROOT / OCR).exists() and not (work / OCR).exists():
                link(ROOT / OCR, work / OCR)
            passing = set()
            for n, path in enumerate(sorted({w.split("::")[0] for w in wanted})):  # one run per file: a module that does not import
                junit = Path(tmp) / f"result{n}.xml"                                # on the base must not stop the others
                subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
                                *(w for w in wanted if w.split("::")[0] == path)], cwd=work, capture_output=True, text=True, encoding="utf-8")
                passing |= passed_keys(junit) if junit.exists() else set()
        finally:
            unlink(work / OCR)
            git("worktree", "remove", "--force", str(work), check=False)
    keys = {(Path(w.split("::")[0]).stem, w.split("::")[-1]) for w in wanted}
    on_base = sorted(keys & passing)
    for module, name in on_base:
        print(f"passes on {base}: {module}::{name}")
    print(f"red_check: {len(keys)} test(s) added or changed, {len(on_base)} pass on {base}")
    return 1 if on_base else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
