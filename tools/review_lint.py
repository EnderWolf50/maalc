"""Checks on what a branch adds, for findings reviewers caught by hand (CODING_STANDARDS.md "Tests", GLOSSARY.md).

  python tools/review_lint.py <base>      # e.g. origin/main; looks at the diff from the merge base to the working tree

- A test added to tests/test_actions.py whose name starts with another feature file's name belongs in that file.
- An added line of a Markdown, locale or i18n file uses a term GLOSSARY.md lists under `_Avoid_`.
  A line carrying `avoid-ok` is skipped (a doc that quotes the term to explain it).
- A node, task or helper removed by the diff is still named somewhere in the tree.

Exit code = number of problems. CI runs it on every pull request.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROSE = re.compile(r"(?:.*\.md|assets/locales/.*\.json|gui/src/i18n\.ts)$")
DEF_TEST = re.compile(r"^\s*(?:async\s+)?def (test_\w+)")


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=check).stdout


def diff_lines(base: str) -> tuple[dict[str, list[tuple[int, str]]], dict[str, list[str]]]:
    """(added, removed) lines per file of `git diff -U0 <merge base of base and HEAD>`; added ones carry their line number."""
    added: dict[str, list[tuple[int, str]]] = {}
    removed: dict[str, list[str]] = {}
    path, old, at = "", "", 0
    for line in git("diff", "-U0", "--no-color", git("merge-base", base, "HEAD").strip()).splitlines():
        if line.startswith("diff --git "):
            path, old = "", ""
        elif not path and line.startswith("--- a/"):
            old = line[6:]
        elif not path and line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else old  # a deleted file: `+++ /dev/null`
        elif m := re.match(r"@@ -\S+ \+(\d+)", line):
            at = int(m[1])
        elif path and line.startswith("+") and not line.startswith("+++"):
            added.setdefault(path, []).append((at, line[1:]))
            at += 1
        elif path and line.startswith("-") and not line.startswith("---"):
            removed.setdefault(path, []).append(line[1:])
    return added, removed


def avoid_terms(glossary: str) -> list[tuple[str, bool]]:
    """The `_Avoid_:` terms specific enough to search for. Text after `；` is the code-side wording, which is
    allowed. A bare word (`bonus`, `輪`, `場`, `獎勵`) is common prose, so it is left out unless its （…） note
    begins 單說, which says the word alone is wrong (`模組`); so is a term whose note says 單指 or （寫程式時可用）."""
    found = []
    for line in glossary.splitlines():
        if not line.startswith("_Avoid_:"):
            continue
        for entry in re.split(r"[、，]", line[len("_Avoid_:"):].split("；")[0]):
            term = re.sub(r"（.*?）", "", entry).strip()
            note = re.search(r"（(.*?)）", entry)
            specific = len(term) >= 3 if not term.isascii() else " " in term and not term[-1].isdigit()
            if term and (note.group(1).startswith("單說") if note else specific):
                found.append(term)
    return found


def avoid_hits(glossary: str, added: dict[str, list[tuple[int, str]]]) -> list[str]:
    """A defined term that holds an avoided word (腦啡肽模組 holds 模組) is blanked out of the line first."""
    terms = avoid_terms(glossary)
    defined = re.findall(r"^\*\*(.+?)\*\*", glossary, re.M)
    problems = []
    for path, lines in added.items():
        if not PROSE.match(path) or path == "GLOSSARY.md":
            continue
        for n, text in lines:
            if "avoid-ok" in text:
                continue
            masked = text
            for word in sorted(defined, key=len, reverse=True):  # a defined term holds the word: 腦啡肽模組
                masked = masked.replace(word, " ")
            for term in terms:
                if re.search(re.escape(term), masked, re.I):
                    problems.append(f"{path}:{n}: uses `{term}`, which GLOSSARY.md lists under _Avoid_")
    return problems


def feature_files() -> list[str]:
    return sorted(p.stem[len("test_"):] for p in (ROOT / "tests").glob("test_*.py") if p.stem != "test_actions")


def misplaced_tests(added: dict[str, list[tuple[int, str]]], features: list[str]) -> list[str]:
    """Tests added to test_actions.py that are named after another test file, which takes them."""
    problems = []
    for n, text in added.get("tests/test_actions.py", []):
        if m := DEF_TEST.match(text):
            owner = max((f for f in features if m[1].startswith(f"test_{f}")), key=len, default=None)
            if owner:
                problems.append(f"tests/test_actions.py:{n}: `{m[1]}` belongs in tests/test_{owner}.py")
    return problems


NODE_KEY = re.compile(r'^\s{0,4}"(\w+)"\s*:\s*\{')  # a pipeline node: the top level of the file
TASK_NAME = re.compile(r'^\s*"name"\s*:\s*"(\w+)"')  # an interface.json task
PY_DEF = re.compile(r"^(?:def |class )(\w+)|^([A-Z][A-Z0-9_]+)\s*(?::[^=]+)?=")  # a module-level helper or constant


def removed_names(removed: dict[str, list[str]], added: dict[str, list[tuple[int, str]]]) -> list[tuple[str, str]]:
    """(name, file) of nodes, tasks, helpers and constants the diff takes out and does not put back."""
    back = {t for lines in added.values() for _, t in lines}
    out = []
    for path, lines in removed.items():
        if path.startswith("assets/resource/base/pipeline/"):
            pattern = NODE_KEY
        elif path == "assets/interface.json":
            pattern = TASK_NAME
        elif path.endswith(".py") and not path.startswith("tests/"):
            pattern = PY_DEF
        else:
            continue
        for text in lines:
            if (m := pattern.match(text)) and (name := next(g for g in m.groups() if g)) and len(name) >= 5:
                if not any(re.search(rf'\b{name}\b', t) and pattern.match(t) for t in back):
                    out.append((name, path))
    return out


def stale_references(removed: dict[str, list[str]], added: dict[str, list[tuple[int, str]]]) -> list[str]:
    problems = []
    for name, path in sorted(set(removed_names(removed, added))):
        hits = git("grep", "-n", "-w", "-e", name, "--", ".", ":(exclude)tests/screens", check=False).splitlines()  # exit 1: no match
        hits = [h for h in hits if not h.startswith((".local/", "docs/adr/"))]  # an ADR records history
        defined = [h for h in hits if any((m := p.match(h.split(":", 2)[2])) and name in m.groups() for p in (NODE_KEY, TASK_NAME, PY_DEF))]
        if hits and not defined:  # a definition elsewhere in the tree: the name was moved or defined twice, not removed
            problems.append(f"{path}: `{name}` was removed but is still named at {hits[0].split(':', 2)[0]}:{hits[0].split(':', 2)[1]}"
                            + (f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""))
    return problems


def main(base: str) -> int:
    added, removed = diff_lines(base)
    glossary = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
    problems = [*misplaced_tests(added, feature_files()), *avoid_hits(glossary, added), *stale_references(removed, added)]
    for p in problems:
        print(p)
    print(f"review_lint: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
