import pytest

import after_land


def fake_git(branch="main", dirty="", fail=None):
    calls = []

    def git(*args):
        calls.append(args)
        if args[0] == fail:
            return 1, "boom"
        if args[0] == "rev-parse":
            return 0, branch + "\n"
        if args[0] == "status":
            return 0, dirty
        return 0, ""

    return git, calls


def test_sync_fetches_then_fast_forwards():
    git, calls = fake_git()
    after_land.sync_main(git)
    assert [c[0] for c in calls][-2:] == ["fetch", "pull"]
    assert "--ff-only" in calls[-1]


@pytest.mark.parametrize("kw, msg", [
    ({"branch": "feature"}, "not on main"),
    ({"dirty": " M agent/x.py\n"}, "not clean"),
    ({"fail": "pull"}, "fast-forward"),
    ({"fail": "fetch"}, "fetch"),
])
def test_sync_refuses(kw, msg):
    git, calls = fake_git(**kw)
    with pytest.raises(SystemExit, match=msg):
        after_land.sync_main(git)
    if "fail" not in kw:
        assert not any(c[0] in ("fetch", "pull") for c in calls)


def test_main_refuses_on_emulator_ticket_before_touching_git(tmp_path, monkeypatch):
    (tmp_path / ".local/queue/emulator").mkdir(parents=True)
    (tmp_path / ".local/queue/emulator/x.ticket").write_text("1")
    monkeypatch.setattr(after_land, "REPO", tmp_path)
    monkeypatch.setattr(after_land, "sync_main", lambda: pytest.fail("git touched"))
    with pytest.raises(SystemExit, match="emulator queue"):
        after_land.main()
