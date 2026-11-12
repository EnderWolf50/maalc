import os
import subprocess
import sys

import pytest

import after_land


def fake_git(branch="main", dirty="", fail=(), head="abc", origin="abc"):
    """A git whose commands named in `fail` fail once each time they are listed there, in order."""
    calls, fails = [], list(fail)

    def git(*args):
        calls.append(args)
        if fails and args[0] == fails[0]:
            fails.pop(0)
            return 1, "boom"
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return 0, branch + "\n"
        if args == ("rev-parse", "HEAD"):
            return 0, head + "\n"
        if args == ("rev-parse", "origin/main"):
            return 0, origin + "\n"
        if args[0] == "status":
            return 0, dirty
        return 0, ""

    return git, calls


def test_sync_fetches_then_fast_forwards_to_origin_main():
    git, calls = fake_git()
    after_land.sync_main(git)
    assert [c for c in calls if c[0] in ("fetch", "merge", "pull")] == [("fetch", "origin"), ("merge", "--ff-only", "origin/main")]


def test_a_fetch_that_fails_is_made_again_up_to_fetch_tries():
    git, calls = fake_git(fail=["fetch"] * (after_land.FETCH_TRIES - 1))
    after_land.sync_main(git)
    assert [c[0] for c in calls].count("fetch") == after_land.FETCH_TRIES
    assert calls[-1] == ("merge", "--ff-only", "origin/main")


def test_a_fetch_that_fails_fetch_tries_times_stops_the_sync():
    git, calls = fake_git(fail=["fetch"] * after_land.FETCH_TRIES)
    with pytest.raises(SystemExit, match="fetch"):
        after_land.sync_main(git)
    assert [c[0] for c in calls].count("fetch") == after_land.FETCH_TRIES
    assert not any(c[0] == "merge" for c in calls)


def test_a_failed_merge_counts_when_main_is_already_at_origin_main():
    git, calls = fake_git(fail=["merge"], head="def", origin="def")
    after_land.sync_main(git)
    assert ("merge", "--ff-only", "origin/main") in calls


@pytest.mark.parametrize("kw, msg", [
    ({"branch": "feature"}, "not on main"),
    ({"dirty": " M agent/x.py\n"}, "not clean"),
    ({"fail": ["merge"], "head": "abc", "origin": "def"}, "fast-forward"),
])
def test_sync_refuses(kw, msg):
    git, calls = fake_git(**kw)
    with pytest.raises(SystemExit, match=msg):
        after_land.sync_main(git)
    if "fail" not in kw:
        assert not any(c[0] in ("fetch", "merge") for c in calls)


def test_main_refuses_on_emulator_ticket_before_touching_git(tmp_path, monkeypatch):
    (tmp_path / ".local/queue/emulator").mkdir(parents=True)
    (tmp_path / f".local/queue/emulator/1-{os.getpid()}-x.ticket").write_text("1")
    monkeypatch.setattr(after_land, "REPO", tmp_path)
    monkeypatch.setattr(after_land, "sync_main", lambda: pytest.fail("git touched"))
    with pytest.raises(SystemExit, match="emulator queue"):
        after_land.main()


def test_main_goes_on_past_the_ticket_of_a_dead_process(tmp_path, monkeypatch):
    # #667: the queue's own reading, as `queue.py status` shows it: a dead process's ticket holds nothing.
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    (tmp_path / ".local/queue/emulator").mkdir(parents=True)
    (tmp_path / f".local/queue/emulator/1-{gone.pid}-x.ticket").write_text("1")
    monkeypatch.setattr(after_land, "REPO", tmp_path)
    monkeypatch.setattr(after_land, "sync_main", lambda: sys.exit("synced"))
    with pytest.raises(SystemExit, match="synced"):
        after_land.main()
