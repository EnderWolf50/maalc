import json
from pathlib import Path

import pytest

import ship

HEAD = "a" * 40
MERGE = "b" * 40


def info(**kw):
    base = {"number": 7, "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE", "baseRefName": "main",
            "headRefName": "feat/x", "headRefOid": HEAD, "isCrossRepository": False,
            "statusCheckRollup": [{"name": "agent (0)", "status": "COMPLETED", "conclusion": "SUCCESS"},
                                  {"name": "ci-ok", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
    return {**base, **kw}


class Fake:
    """A runner that answers `gh` and `git` calls from a table and records them.

    `routes` maps a tuple of leading words to (rc, output) or a list of them (one per call, the last repeats)."""

    def __init__(self, **routes):
        self.calls = []
        self.routes = routes

    def __call__(self, argv, cwd=None):
        self.calls.append(list(argv))
        for n in range(len(argv), 0, -1):
            hit = self.routes.get(" ".join(argv[:n]))
            if hit is not None:
                if isinstance(hit, list):
                    hit = hit.pop(0) if len(hit) > 1 else hit[0]
                return hit
        return 0, ""

    def ran(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == list(prefix)]


def land_fake(pr=None, stacked=(), main_ci=(("completed", "success"),), queue="emulator:\n  free\n", **extra):
    runs = [(0, json.dumps([{"status": s, "conclusion": c, "url": "u"}])) for s, c in main_ci]
    return Fake(**{"gh pr view 7": [(0, json.dumps(pr or info())),
                                    (0, json.dumps({"mergeCommit": {"oid": MERGE}}))],
                   "gh pr list": (0, json.dumps(list(stacked))), "gh run list": runs,
                   "gh pr merge": (0, ""), "gh pr edit": (0, ""), "gh api": (0, ""),
                   f"{ship.sys.executable} tools/live/queue.py status": (0, queue),
                   "uv run python tools/after_land.py": (0, "after_land done"), **extra})


def land(fake, go=True):
    return ship.cmd_land(fake, 7, go, sleep=lambda s: None, repo=Path("main-checkout"))


@pytest.mark.parametrize("rollup, want", [
    ([{"name": "ci-ok", "status": "COMPLETED", "conclusion": "SUCCESS"}], "SUCCESS"),
    ([{"name": "ci-ok", "status": "COMPLETED", "conclusion": "FAILURE"}], "FAILURE"),
    ([{"name": "ci-ok", "status": "IN_PROGRESS", "conclusion": ""}], "pending"),
    ([{"name": "agent (0)", "status": "COMPLETED", "conclusion": "SUCCESS"}], "missing"),
    ([], "missing"),
])
def test_ci_state(rollup, want):
    assert ship.ci_state(info(statusCheckRollup=rollup)) == want


def test_ready_line_lists_head_ci_mergeable_draft_base_and_stack():
    line = ship.ready_line(info(), [{"number": 9}, {"number": 12}])
    assert "#7 head aaaaaaaaaa ci-ok SUCCESS mergeable MERGEABLE draft false base main" in line
    assert line.endswith("stacked #9,#12")


def test_ready_prints_one_line_per_pr(capsys):
    fake = Fake(**{"gh pr view": (0, json.dumps(info())), "gh pr list": (0, "[]")})
    assert ship.cmd_ready(fake, [7, 8]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 2


@pytest.mark.parametrize("kw, text", [
    ({"isDraft": True}, "draft"),
    ({"mergeable": "CONFLICTING"}, "conflicting"),
    ({"state": "MERGED"}, "MERGED"),
    ({"statusCheckRollup": []}, "ci-ok is missing"),
    ({"statusCheckRollup": [{"name": "ci-ok", "status": "COMPLETED", "conclusion": "FAILURE"}]}, "ci-ok is FAILURE"),
])
def test_land_refuses_and_merges_nothing(kw, text, capsys):
    fake = land_fake(pr=info(**kw))
    assert land(fake) == 1
    assert text in capsys.readouterr().err
    assert not fake.ran("gh", "pr", "merge")


def test_land_without_go_merges_nothing():
    fake = land_fake()
    assert land(fake, go=False) == 0
    assert not fake.ran("gh", "pr", "merge")


def test_land_merges_pinned_to_the_checked_head_with_a_merge_commit():
    fake = land_fake()
    assert land(fake) == 0
    merge = fake.ran("gh", "pr", "merge")[0]
    assert "--merge" in merge and merge[merge.index("--match-head-commit") + 1] == HEAD


def test_land_retargets_stacked_prs_before_the_branch_is_deleted():
    fake = land_fake(stacked=[{"number": 9, "headRefName": "feat/y"}])
    assert land(fake) == 0
    order = [c[:3] for c in fake.calls]
    assert ["gh", "pr", "edit"] in order
    assert order.index(["gh", "pr", "edit"]) < order.index(["gh", "api", "-X"])
    assert fake.ran("gh", "pr", "edit")[0][3:] == ["9", "--base", "main"]


def test_land_keeps_the_branch_of_a_fork():
    fake = land_fake(pr=info(isCrossRepository=True))
    land(fake)
    assert not fake.ran("gh", "api")


def test_land_waits_until_the_main_run_finishes():
    fake = land_fake(main_ci=[("queued", None), ("in_progress", None), ("completed", "success")])
    assert land(fake) == 0
    assert len(fake.ran("gh", "run", "list")) == 3
    assert fake.ran("uv", "run", "python", "tools/after_land.py")


def test_land_exits_non_zero_on_a_red_main_and_skips_after_land(capsys):
    fake = land_fake(main_ci=[("completed", "failure")])
    assert land(fake) == 1
    assert "failure" in capsys.readouterr().err
    assert not fake.ran("uv", "run", "python", "tools/after_land.py")


def test_land_prints_the_command_when_the_emulator_has_a_holder(capsys):
    fake = land_fake(queue="emulator:\n  1234-bot (pid 5)\n")
    assert land(fake) == 0
    assert "tools/after_land.py" in capsys.readouterr().out
    assert not fake.ran("uv", "run", "python", "tools/after_land.py")


def test_land_into_a_stacked_base_does_not_wait_for_a_main_run(capsys):
    fake = land_fake(pr=info(baseRefName="feat/base"))
    assert land(fake) == 0
    assert not fake.ran("gh", "run", "list") and not fake.ran("uv", "run", "python", "tools/after_land.py")
    assert "feat/base" in capsys.readouterr().out


def test_wait_for_main_ci_times_out():
    clock = iter(range(0, 10000, 100))
    fake = Fake(**{"gh run list": (0, "[]")})
    assert ship.wait_for_main_ci(fake, "main", MERGE, sleep=lambda s: None, now=lambda: next(clock), timeout=300) == "timeout"


def into_fake(merge=(0, ""), check=(0, "checks ok"), conflicts="a.py\nb.py\n", prs="[]", tree="/wt/integration"):
    listing = f"worktree {tree}\nHEAD {HEAD}\nbranch refs/heads/integration\n\n"
    return Fake(**{"git worktree list": (0, listing), "git status": (0, ""), "git rev-parse": (0, HEAD + "\n"),
                   "git merge --ff-only": (0, ""), "git merge --abort": (0, ""), "git merge": merge, "git diff": (0, conflicts),
                   "uv run python tools/live/queue.py": check, "gh pr list": (0, prs), "gh pr create": (0, "https://example.test/pr/1\n")})


def test_into_pushes_only_after_green_checks_and_opens_a_draft_pr():
    fake = into_fake()
    assert ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout")) == 0
    names = [" ".join(c[:2]) for c in fake.calls]
    assert names.index("git push") > max(i for i, c in enumerate(fake.calls) if "tools/check.py" in c)
    bench = next(c for c in fake.calls if "tools/check.py" in c and "queue.py" in " ".join(c))
    assert bench[bench.index("--resource") + 1] == "bench"
    merge = fake.ran("git", "merge", "--no-ff", "-m")[0]
    assert merge[-1] == "origin/feat/x"
    create = fake.ran("gh", "pr", "create")[0]
    assert "--draft" in create and create[create.index("--head") + 1] == "integration"


def test_into_opens_no_second_pr():
    fake = into_fake(prs='[{"number": 3}]')
    assert ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout")) == 0
    assert not fake.ran("gh", "pr", "create")


def test_into_stops_on_a_conflict_and_aborts_the_merge(capsys):
    fake = into_fake(merge=(1, "CONFLICT"))
    assert ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout")) == 1
    assert "a.py, b.py" in capsys.readouterr().err
    assert fake.ran("git", "merge", "--abort") and not fake.ran("git", "push")


def test_into_resets_and_does_not_push_on_red_checks(capsys):
    fake = into_fake(check=(1, "pytest failed"))
    assert ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout")) == 1
    assert fake.ran("git", "reset", "--hard", HEAD) and not fake.ran("git", "push")
    assert not fake.ran("gh", "pr", "create")


def test_into_installs_the_packages_of_a_new_worktree():
    fake = into_fake()
    fake.routes["git worktree list"] = (0, "worktree main-checkout\nbranch refs/heads/main\n\n")
    assert ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout")) == 0
    add = next(i for i, c in enumerate(fake.calls) if c[:3] == ["git", "worktree", "add"])
    pnpm = next(i for i, c in enumerate(fake.calls) if c[:2] == ["pnpm", "install"])
    check = next(i for i, c in enumerate(fake.calls) if "queue.py" in " ".join(c))
    assert add < pnpm < check


def test_into_resets_a_merge_it_did_not_push_when_a_step_exits():
    fake = into_fake()
    fake.routes["uv run python tools/fetch_ocr.py"] = (1, "no network")
    with pytest.raises(SystemExit):
        ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout"))
    assert fake.ran("git", "reset", "--hard", HEAD) and not fake.ran("git", "push")


def test_into_reports_a_failed_merge_that_is_not_a_conflict(capsys):
    fake = into_fake(merge=(1, "fatal: not something we can merge"), conflicts="")
    fake.routes["git merge --abort"] = (128, "There is no merge to abort")
    assert ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout")) == 1
    assert "not something we can merge" in capsys.readouterr().err


def test_into_refuses_a_dirty_integration_worktree():
    fake = into_fake()
    fake.routes["git status"] = (0, " M agent/x.py\n")
    with pytest.raises(SystemExit, match="local changes"):
        ship.cmd_into(fake, "integration", "feat/x", repo=Path("main-checkout"))
    assert not fake.ran("git", "merge", "--no-ff", "-m")
