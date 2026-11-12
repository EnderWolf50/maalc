"""Checks on what a branch adds, for findings reviewers caught by hand (CODING_STANDARDS.md "Tests", GLOSSARY.md).

  python tools/review_lint.py <base>      # e.g. origin/main; looks at the diff from the merge base to the working tree
                                          # and at the commits from the merge base to HEAD

- A test added to tests/test_actions.py whose name starts with another feature file's name belongs in that file.
- An added line of a Markdown, locale or i18n file uses a term GLOSSARY.md lists under `_Avoid_`.
  A line carrying `avoid-ok` is skipped (a doc that quotes the term to explain it).
- A node, task or helper removed by the diff is still named somewhere in the tree. A branch commit's
  `Removed-name-ok: <name> (<why>)` line skips a name the tree uses for another thing (#439: the game's BATTLE node).
- A commit from the merge base to HEAD (merge commits left out) carries a GitHub closing keyword before an issue
  number (`fix: #387`, `Fixes #12`, `closes owner/repo#5`): merged into main it closes the issue whatever the PR
  body says (docs/agents/pr.md "Language").

Exit code 1 when there is a problem, else 0. CI runs it on every pull request.
"""
import re
import sys
from pathlib import Path

import git_diff
from git_diff import git

ROOT = Path(__file__).resolve().parent.parent
PROSE = re.compile(r"(?:.*\.md|assets/locales/.*\.json|gui/src/i18n\.ts)$")
DEF_TEST = re.compile(r"^\s*(?:async\s+)?def (test_\w+)")


def merge_base(base: str) -> str:
    return git("merge-base", base, "HEAD", cwd=ROOT).strip()


def diff_lines(base: str) -> tuple[dict[str, list[tuple[int, str]]], dict[str, list[str]]]:
    """(added, removed) lines per file of `git diff -U0 <merge base of base and HEAD>`; added ones carry their line number."""
    added: dict[str, list[tuple[int, str]]] = {}
    removed: dict[str, list[str]] = {}
    for line in git_diff.lines(git("diff", "-U0", "--no-color", merge_base(base), cwd=ROOT)):
        # left out, as this walk did before git_diff: a file named without a/ b/ (a quoted path) and a line that
        # starts like a file header (`+++`, `---`)
        if line.path is None or line.text.startswith(line.sign * 2):
            continue
        if line.sign == "+":
            added.setdefault(line.path, []).append((line.no, line.text))
        else:
            removed.setdefault(line.path, []).append(line.text)  # a deleted file's under its old name
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


REMOVED_OK = re.compile(r"^Removed-name-ok:[ \t]*(\w+)[ \t]+\(.+\)", re.M)  # one name a line, its why required


def branch_messages(base: str) -> list[tuple[str, str]]:
    """(short sha, message) of the branch's own commits, merge commits left out."""
    log = git("log", "--no-merges", "--format=%h%x00%B%x1e", f"{merge_base(base)}..HEAD", cwd=ROOT)
    return [tuple(entry.strip("\n").split("\x00", 1)) for entry in log.split("\x1e") if "\x00" in entry]


def removed_name_oks(base: str) -> set[str]:
    """Names a branch commit marks `Removed-name-ok: <name> (<why>)`: the tree still names them, but as another thing
    (the game's BATTLE node, an AALC asset group), not the removed one. The whole name, on this branch only: the merge
    base moves on once it lands."""
    return {name for _, message in branch_messages(base) for name in REMOVED_OK.findall(message)}


def stale_references(removed: dict[str, list[str]], added: dict[str, list[tuple[int, str]]],
                     ok: frozenset[str] | set[str] = frozenset()) -> list[str]:
    problems = []
    for name, path in sorted({(n, p) for n, p in removed_names(removed, added) if n not in ok}):
        hits = git("grep", "-n", "-w", "-e", name, "--", ".", ":(exclude)tests/screens", cwd=ROOT, check=False).splitlines()  # exit 1: no match
        hits = [h for h in hits if not h.startswith((".local/", "docs/adr/"))]  # an ADR records history
        defined = [h for h in hits if any((m := p.match(h.split(":", 2)[2])) and name in m.groups() for p in (NODE_KEY, TASK_NAME, PY_DEF))]
        if hits and not defined:  # a definition elsewhere in the tree: the name was moved or defined twice, not removed
            problems.append(f"{path}: `{name}` was removed but is still named at {hits[0].split(':', 2)[0]}:{hits[0].split(':', 2)[1]}"
                            + (f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""))
    return problems


# GitHub's closing keywords, any case, an optional colon, then #N or owner/repo#N:
# https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s*((?:[\w.-]+/[\w.-]+)?#\d+)", re.I)


def closing_keyword_hits(sha: str, message: str) -> list[str]:
    problems = []
    for line in message.splitlines():
        for m in CLOSING.finditer(line):
            problems.append(f"commit {sha}: `{line.strip()}` closes {m[1]} on merge; say Closes or Refs in the PR body"
                            f" and reword the commit to `review({m[1]}): ...` or `Refs {m[1]}`")
    return problems


def commit_closing_hits(base: str) -> list[str]:
    """Closing keywords in the messages of the branch's own commits, merge commits left out."""
    return [p for sha, message in branch_messages(base) for p in closing_keyword_hits(sha, message)]


def main(base: str) -> int:
    added, removed = diff_lines(base)
    glossary = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
    problems = [*misplaced_tests(added, feature_files()), *avoid_hits(glossary, added), *stale_references(removed, added, removed_name_oks(base)),
                *commit_closing_hits(base)]
    for p in problems:
        print(p)
    print(f"review_lint: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
