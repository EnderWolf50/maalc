"""Dump everything a reviewer needs about a PR into files, for a reviewer whose Bash tool cannot run.

  uv run python tools/review_pack.py <pr>

Writes `<main checkout>/.local/scratch/review-<pr>/`: `diff.patch`, `body.md`, `ci.txt` (head SHA and the state of
every check), and `issue-<n>.md` for each issue the PR closes or names (title, state, body, comments). Read the files
with the Read tool.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from local_dir import local_dir

MAX_ISSUES = 20


def run(argv: list[str]) -> tuple[int, str]:
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def named_issues(body: str, closing: list[dict], own: int) -> list[int]:
    """The numbers the PR closes (GitHub's list first) or names with `#n` in its body, without the PR itself."""
    found = [c["number"] for c in closing] + [int(n) for n in re.findall(r"(?<![\w/&])#(\d+)\b", body or "")]
    return [n for n in dict.fromkeys(found) if n != own][:MAX_ISSUES]


def ci_text(info: dict) -> str:
    lines = [f"head {info['headRefOid']}"]
    for c in info.get("statusCheckRollup") or []:
        lines.append(f"{c.get('name') or c.get('context')}: {c.get('status') or c.get('state')} "
                     f"{c.get('conclusion') or ''}".rstrip())
    return "\n".join(lines) + "\n"


def issue_text(issue: dict) -> str:
    out = [f"# #{issue['number']} {issue['title']} ({issue['state']})", "", issue.get("body") or "", ""]
    for c in issue.get("comments") or []:
        out += [f"## comment {c.get('createdAt', '')}", c.get("body") or "", ""]
    return "\n".join(out)


def pack(pr: int, out: Path, runner=run) -> list[str]:
    """Writes the files; returns the notes about what could not be read."""
    notes = []

    def gh(*args):
        rc, text = runner(["gh", *args])
        if rc:
            sys.exit(f"review_pack: gh {' '.join(args[:3])} failed\n{text.strip()}")
        return text

    info = json.loads(gh("pr", "view", str(pr), "--json",
                         "number,title,body,headRefOid,baseRefName,closingIssuesReferences,statusCheckRollup"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "diff.patch").write_text(gh("pr", "diff", str(pr)), encoding="utf-8")
    (out / "body.md").write_text(f"# {info['title']} (base {info['baseRefName']})\n\n{info['body'] or ''}\n", encoding="utf-8")
    (out / "ci.txt").write_text(ci_text(info), encoding="utf-8")
    for n in named_issues(info["body"], info["closingIssuesReferences"], pr):
        rc, text = runner(["gh", "issue", "view", str(n), "--json", "number,title,state,body,comments"])
        if rc:
            notes.append(f"#{n} could not be read as an issue")
            continue
        (out / f"issue-{n}.md").write_text(issue_text(json.loads(text)), encoding="utf-8")
    return notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", type=int)
    a = ap.parse_args(argv)
    out = local_dir("scratch") / f"review-{a.pr}"
    notes = pack(a.pr, out)
    print(f"review pack in {out}: {', '.join(sorted(p.name for p in out.iterdir()))}")
    print(*notes, sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
