"""tools/review_lint.py: the diff-based review checks."""
import subprocess
from pathlib import Path

import review_lint

GLOSSARY = """\
**每週獎勵**：
入口頁的 Weekly Bonuses。
_Avoid_: 困難次數、bonus

**腦啡肽模組**：
打經驗本要花的資源。
_Avoid_: 模組（單說容易和其他模組混淆）

**經驗本**：
Luxcavation 的 EXP 分頁。
_Avoid_: 經驗副本、EXP dungeon；程式裡寫 EXP Luxcavation

**局**：
一次挑戰。
_Avoid_: run（寫程式時可用）、輪
"""


def lines(path, *texts):
    return {path: [(i + 1, t) for i, t in enumerate(texts)]}


def test_avoid_terms_skip_the_code_side_wording_and_short_ascii_words():
    terms = review_lint.avoid_terms(GLOSSARY)
    assert terms == ["困難次數", "模組", "經驗副本", "EXP dungeon"]  # not bonus, 輪 or run: common words


def test_a_prose_line_with_an_avoid_term_is_a_hit():
    hits = review_lint.avoid_hits(GLOSSARY, lines("README.md", "ok", "用經驗副本打 EXP"))
    assert hits == ["README.md:2: uses `經驗副本`, which GLOSSARY.md lists under _Avoid_"]


def test_a_defined_term_holding_an_avoided_word_is_not_a_hit():
    assert review_lint.avoid_hits(GLOSSARY, lines("docs/a.md", "要有足夠的模組"))
    assert not review_lint.avoid_hits(GLOSSARY, lines("docs/a.md", "要有足夠的腦啡肽模組"))


def test_avoid_ok_glossary_and_code_files_are_not_checked():
    assert not review_lint.avoid_hits(GLOSSARY, lines("README.md", "別寫「經驗副本」 <!-- avoid-ok -->"))
    assert not review_lint.avoid_hits(GLOSSARY, lines("GLOSSARY.md", "經驗副本"))
    assert not review_lint.avoid_hits(GLOSSARY, lines("agent/x.py", "# 經驗副本"))
    assert review_lint.avoid_hits(GLOSSARY, lines("assets/locales/zh_tw.json", '"a": "經驗副本"'))


def test_a_new_test_named_after_another_test_file_is_misplaced():
    added = lines("tests/test_actions.py", "def test_shop_scroll_stops_at_the_end():", "def test_tap_waits():")
    assert review_lint.misplaced_tests(added, ["shop", "shop_scroll", "state"]) == [
        "tests/test_actions.py:1: `test_shop_scroll_stops_at_the_end` belongs in tests/test_shop_scroll.py"]
    assert not review_lint.misplaced_tests(lines("tests/test_shop.py", "def test_shop_x():"), ["shop"])


def test_removed_node_still_named_is_stale_unless_put_back():
    pipe = "assets/resource/base/pipeline/navigation.json"
    removed = {pipe: ['    "GoHomeOld": {', '    "Tiny": {'], "agent/a.py": ["OLD_LIMIT = 3", "def old_helper(x):"]}
    names = {n for n, _ in review_lint.removed_names(removed, {})}
    assert names == {"GoHomeOld", "OLD_LIMIT", "old_helper"}  # `Tiny` is too short to search for
    back = lines(pipe, '    "GoHomeOld": {')
    assert {n for n, _ in review_lint.removed_names(removed, back)} == {"OLD_LIMIT", "old_helper"}


def test_diff_lines_reads_added_with_numbers_and_removed(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    run("init", "-q", "-b", "main")
    (tmp_path / "a.md").write_text("one\ntwo\nthree\n")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    (tmp_path / "a.md").write_text("one\n2\nthree\nfour\n")
    run("commit", "-qam", "change")
    monkeypatch.setattr(review_lint, "ROOT", Path(tmp_path))
    added, removed = review_lint.diff_lines("main")
    assert added == {"a.md": [(2, "2"), (4, "four")]} and removed == {"a.md": ["two"]}

def test_a_removed_name_still_used_is_stale_but_one_defined_elsewhere_is_not(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / "a.py").write_text("OLD_LIMIT = 3\nSHARED_LIMIT = 4\n")
    (tmp_path / "README.md").write_text("OLD_LIMIT is the cap\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    (tmp_path / "a.py").write_text("SHARED_LIMIT = 4\nSHARED_LIMIT = 4\n")
    monkeypatch.setattr(review_lint, "ROOT", Path(tmp_path))
    removed = {"a.py": ["OLD_LIMIT = 3", "SHARED_LIMIT = 4"]}
    assert review_lint.stale_references(removed, {}) == ["a.py: `OLD_LIMIT` was removed but is still named at README.md:1"]


def test_a_removed_name_nobody_names_any_more_is_not_a_crash(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / "a.py").write_text("DEAD_LIMIT = 3\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    (tmp_path / "a.py").write_text("")
    monkeypatch.setattr(review_lint, "ROOT", Path(tmp_path))
    assert review_lint.stale_references({"a.py": ["DEAD_LIMIT = 3"]}, {}) == []


def test_diff_lines_reads_the_lines_of_a_deleted_file(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / "gone.py").write_text("GONE_LIMIT = 3\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    run("rm", "-q", "gone.py")
    run("commit", "-qm", "delete")
    monkeypatch.setattr(review_lint, "ROOT", Path(tmp_path))
    assert review_lint.diff_lines("main")[1] == {"gone.py": ["GONE_LIMIT = 3"]}


def test_a_closing_keyword_before_an_issue_number_is_a_hit():
    for message in ["fix: #387 review: one cover default", "Fixes #12", "closes EnderWolf50/maalc#5", "CLOSED: #7",
                    "feat: shop\n\nResolves #9"]:
        assert review_lint.closing_keyword_hits("abc1234", message), message


def test_refs_a_keyword_without_an_issue_and_a_merge_subject_are_not_hits():
    for message in ["Refs #387", "fix(release): tag the build", "Merge pull request #601 from EnderWolf50/feat/x",
                    "review(#387): quoted names", "prefix #3 is fine", "feat: floors 1-15 (#387)"]:
        assert review_lint.closing_keyword_hits("abc1234", message) == [], message


def test_a_hit_names_the_commit_the_line_and_the_fix():
    hits = review_lint.closing_keyword_hits("142a2c2", "fix: #387 review: one cover default\n\nbody")
    assert len(hits) == 1
    assert hits[0].startswith("commit 142a2c2: `fix: #387 review: one cover default` closes #387 on merge")
    assert "PR body" in hits[0] and "review(#387): ..." in hits[0] and "Refs #387" in hits[0]
    other = review_lint.closing_keyword_hits("abc1234", "closes owner/repo#5")
    assert len(other) == 1 and "closes owner/repo#5 on merge" in other[0] and "Refs owner/repo#5" in other[0]


def test_commit_messages_skip_merge_commits_and_stop_at_the_merge_base(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    run("init", "-q", "-b", "main")
    (tmp_path / "a.md").write_text("one\n")
    run("add", ".")
    run("commit", "-qm", "fix: #1 on main already")
    run("checkout", "-qb", "side")
    (tmp_path / "b.md").write_text("side\n")
    run("add", ".")
    run("commit", "-qm", "side work")
    run("checkout", "-qb", "feat", "main")
    (tmp_path / "a.md").write_text("two\n")
    run("commit", "-qam", "fix: #387 review: names")
    run("merge", "-q", "--no-ff", "side", "-m", "Merge branch side, fixes #2")
    monkeypatch.setattr(review_lint, "ROOT", Path(tmp_path))
    hits = review_lint.commit_closing_hits("main")
    assert len(hits) == 1 and "`fix: #387 review: names` closes #387" in hits[0]


def test_a_removed_name_a_commit_marks_ok_is_not_stale(tmp_path, monkeypatch):
    # #439: `BATTLE` left recovery.py, but the docs name the game's BATTLE node and AALC's BATTLE assets, not the constant.
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / "a.py").write_text("BATTLE = 1\nOLD_LIMIT = 3\n")
    (tmp_path / "README.md").write_text("the game's BATTLE node; OLD_LIMIT is the cap\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    (tmp_path / "a.py").write_text("\n")
    run("commit", "-qam", "drop the constants\n\nRemoved-name-ok: BATTLE (the game's word in the docs)\n"
                          "Removed-name-ok: OLD_LIMIT\nRemoved-name-ok:\n\nRefs #439")  # no why, no name: not ok
    monkeypatch.setattr(review_lint, "ROOT", Path(tmp_path))
    assert review_lint.removed_name_oks("main") == {"BATTLE"}
    removed = {"a.py": ["BATTLE = 1", "OLD_LIMIT = 3"]}
    assert review_lint.stale_references(removed, {}, review_lint.removed_name_oks("main")) == [
        "a.py: `OLD_LIMIT` was removed but is still named at README.md:1"]
