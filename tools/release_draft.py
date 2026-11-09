"""Attach the release zip to a draft release of TAG, unless TAG already has a release (draft or published).

    uv run --no-dev python tools/release_draft.py TAG ZIP SHA

The release workflow's last step (.github/workflows/release.yml). A release goes: `workflow_dispatch` with the tag
builds the draft, the draft is checked by hand, then published; publishing creates the tag, and the tag's push runs the
workflow again. That run, or a second dispatch while a draft is up, finds the tag's release and creates nothing: it
prints one line and exits 0 (#587: v0.1.0's tag push made a second draft). The zip is not compared with the attached
one: the release already there is the one checked by hand, and a rebuild is not byte-identical.

The releases are listed with the workflow's token, which has push access, so drafts are listed too.
"""
from __future__ import annotations

import subprocess
import sys


def run_gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def release_tags(gh) -> set[str]:
    """The tag name of every release of the repository, drafts included."""
    out = gh(["api", "--paginate", "repos/{owner}/{repo}/releases", "--jq", ".[].tag_name"])
    return {line.strip() for line in out.splitlines() if line.strip()}


def draft(tag: str, zip_path: str, sha: str, gh=run_gh, say=print) -> int:
    if tag in release_tags(gh):
        say(f"{tag} already has a release: nothing created (draft, check, publish; the tag push after publishing ends here)")
        return 0
    gh(["release", "create", tag, zip_path, "--draft", "--target", sha, "--title", tag, "--generate-notes"])
    say(f"{tag}: draft release created with {zip_path}")
    return 0


def main(argv=None) -> int:
    tag, zip_path, sha = argv if argv is not None else sys.argv[1:]
    return draft(tag, zip_path, sha)


if __name__ == "__main__":
    sys.exit(main())
