import json

import review_pack


def fake_gh(pr_body, closing=(), unreadable=()):
    info = {"number": 5, "title": "feat: x", "body": pr_body, "headRefOid": "c" * 40, "baseRefName": "main",
            "closingIssuesReferences": [{"number": n} for n in closing],
            "statusCheckRollup": [{"name": "ci-ok", "status": "COMPLETED", "conclusion": "SUCCESS"}]}

    def runner(argv):
        if argv[:3] == ["gh", "pr", "view"]:
            return 0, json.dumps(info)
        if argv[:3] == ["gh", "pr", "diff"]:
            return 0, "diff --git a/x b/x\n"
        n = int(argv[3])
        if n in unreadable:
            return 1, "not found"
        return 0, json.dumps({"number": n, "title": f"issue {n}", "state": "OPEN", "body": "text",
                              "comments": [{"createdAt": "d", "body": "a comment"}]})
    return runner


def test_named_issues_takes_closing_first_then_body_without_the_pr_itself():
    assert review_pack.named_issues("Closes #12, see #9 and #5 and #12", [{"number": 12}], own=5) == [12, 9]


def test_named_issues_ignores_other_repos_and_anchors():
    assert review_pack.named_issues("other/repo#3 and a&#39; and #4", [], own=1) == [4]


def test_pack_writes_diff_body_ci_and_each_issue(tmp_path):
    notes = review_pack.pack(5, tmp_path / "r", fake_gh("Closes #12, mentions #9", closing=[12]))
    files = sorted(p.name for p in (tmp_path / "r").iterdir())
    assert files == ["body.md", "ci.txt", "diff.patch", "issue-12.md", "issue-9.md"]
    assert notes == []
    assert "ci-ok: COMPLETED SUCCESS" in (tmp_path / "r/ci.txt").read_text()
    assert "a comment" in (tmp_path / "r/issue-12.md").read_text()


def test_pack_notes_a_number_that_is_not_an_issue(tmp_path):
    notes = review_pack.pack(5, tmp_path / "r", fake_gh("see #9", unreadable=[9]))
    assert notes == ["#9 could not be read as an issue"]
    assert not (tmp_path / "r/issue-9.md").exists()
