"""A screen the bot dismisses is kept in logs/dismissed/ first (#244)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import actions
import recovery
from test_pipeline import load_nodes

DISMISSERS = ["Notices", "Mailbox", "SettingsMenu", "HelpPager", "RetryPopup", "PopupButton", "ParallelModePrompt", "RecoverL1"]


@pytest.fixture
def game(monkeypatch, tmp_path):
    state = SimpleNamespace(taps=[], keys=[], ctx=MagicMock())
    ctx = state.ctx
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: np.full((720, 1280, 3), 7, np.uint8)
    ctx.tasker.controller.post_click.side_effect = lambda x, y: state.taps.append((x, y)) or MagicMock()
    ctx.tasker.controller.post_click_key.side_effect = lambda k: state.keys.append(k) or MagicMock()
    monkeypatch.setattr(actions, "ROOT", tmp_path)
    actions.RUN.clear()
    actions.DISMISSED_AT.clear()
    actions.RUN["settings"] = {"run": {"keep_dismissed_screens": True}}
    state.folder = tmp_path / "logs" / "dismissed"
    yield state
    actions.RUN.clear()


def button(text):
    """What the And of PopupButton hands the action: its PopupButtonText sub-result read `text`."""
    sub = SimpleNamespace(name="PopupButtonText", best_result=SimpleNamespace(text=text))
    return SimpleNamespace(best_result=SimpleNamespace(sub_results=[SimpleNamespace(name="Or", best_result=None), sub]))


def arg(node, param=None, box=(100, 200, 40, 20), reco_detail=None):
    return SimpleNamespace(node_name=node, custom_action_param=param, box=box, reco_detail=reco_detail or button("Confirm"))


def test_the_screen_is_kept_under_its_time_and_node_before_the_key(game):
    assert actions.DismissShot().run(game.ctx, arg("Notices", '{"back": true}'))
    (shot,) = game.folder.iterdir()
    assert shot.name.endswith("-Notices.png") and shot.read_bytes().startswith(b"\x89PNG")
    assert game.keys == [actions.BACK_KEY] and game.taps == []


def test_a_box_is_tapped_at_its_centre(game):
    actions.DismissShot().run(game.ctx, arg("PopupButton"))
    assert game.taps == [(120, 210)] and game.keys == []
    assert len(list(game.folder.iterdir())) == 1


def test_a_popup_pressed_is_logged_with_its_text_and_button(game, monkeypatch, capsys):
    # #382: the previous session's "Please claim your rewards" was closed with no line saying what it was.
    texts = []
    monkeypatch.setattr(actions, "text", lambda context, image, roi, only_rec=False: texts.append(roi) or "The previous session has expired. Please claim your rewards.")
    actions.DismissShot().run(game.ctx, arg("PopupButton", reco_detail=button("Confirm")))
    assert texts == [actions.DIALOG_TEXT]  # the dialog is the only OCR it adds: the button's text is the recognition's
    assert "popup: 'The previous session has expired. Please claim your rewards.': pressed 'Confirm'" in capsys.readouterr().out


def test_off_dismisses_without_a_shot(game):
    actions.RUN["settings"]["run"]["keep_dismissed_screens"] = False
    actions.DismissShot().run(game.ctx, arg("PopupButton"))
    assert game.taps == [(120, 210)] and not game.folder.exists()


def test_a_full_disk_does_not_keep_the_popup_open(game, monkeypatch):
    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(recovery, "keep_capture", fail)
    assert actions.DismissShot().run(game.ctx, arg("RetryPopup"))
    assert game.taps == [(120, 210)]
    assert "RetryPopup" not in actions.DISMISSED_AT  # a failed save does not start the gap


def test_only_a_gapped_node_leaves_a_time_behind(game):
    actions.DismissShot().run(game.ctx, arg("PopupButton"))
    actions.DismissShot().run(game.ctx, arg("RetryPopup"))
    assert list(actions.DISMISSED_AT) == ["RetryPopup"]


def test_only_retry_popup_is_kept_once_a_minute(game, monkeypatch):
    clock = iter([100.0, 130.0, 159.9, 160.0, 161.0, 161.0, 161.0])
    monkeypatch.setattr(actions.time, "monotonic", lambda: next(clock))
    stamps = iter(f"2026-10-24T00:00:0{i}Z" for i in range(7))
    monkeypatch.setattr(actions.settlement, "now", lambda: next(stamps))
    for node in ("RetryPopup", "RetryPopup", "RetryPopup", "RetryPopup", "Notices", "Notices", "PopupButton"):
        actions.DismissShot().run(game.ctx, arg(node))
    names = sorted(p.name[20:] for p in game.folder.iterdir())
    assert names == ["-Notices.png"] * 2 + ["-PopupButton.png"] + ["-RetryPopup.png"] * 2  # RetryPopup at 100 and 160 s
    assert len(game.taps) == 7  # every popup is still closed


def test_the_folder_keeps_only_the_latest(game):
    for i in range(recovery.DISMISSED_KEEP + 3):
        recovery.keep_capture(actions.ROOT, "dismissed", np.zeros((4, 4, 3), np.uint8), f"{i:04}-Notices", recovery.DISMISSED_KEEP)
    assert len(list(game.folder.iterdir())) == recovery.DISMISSED_KEEP


def test_every_dismissing_node_goes_through_the_shot():
    nodes = load_nodes()
    assert [n for n in DISMISSERS if nodes[n].get("custom_action") != "DismissShot"] == []
    assert [n for n in ("Notices", "HelpPager", "RecoverL1", "HomeBack") if nodes[n]["custom_action_param"].get("back") is not True] == []


@pytest.fixture
def clock(monkeypatch):
    """A fake clock that time.sleep moves on; returns the list of sleeps."""
    now, sleeps = [1000.0], []

    def sleep(s):
        sleeps.append(s)
        now[0] += s
    monkeypatch.setattr(actions.time, "sleep", sleep)
    monkeypatch.setattr(actions.time, "monotonic", lambda: now[0])
    return sleeps


def shows(game, node, looks):
    """node hits from the looks-th screenshot on (the kept screen is the first), every other node misses."""
    shots = game.ctx.tasker.controller.post_screencap
    game.ctx.run_recognition.side_effect = lambda name, image, override=None: (
        SimpleNamespace(hit=True, box=(0, 0, 1, 1)) if name == node and shots.call_count >= looks else None)


UNTIL_HOME = {"until": "HomeReached", "timeout": 1.5}


def test_a_popup_with_until_hands_back_once_the_page_under_it_shows(game, clock):
    # #258: the Mailbox slept 1.5 s after its Close; in all 5 live closes the main window was up at the first look after.
    shows(game, "HomeReached", looks=3)
    assert actions.DismissShot().run(game.ctx, arg("Mailbox", json.dumps(UNTIL_HOME)))
    assert game.taps == [(120, 210)] and sum(clock) == pytest.approx(0.2)  # one 0.2 s look, no 1.5 s sleep
    assert "Mailbox: screen changed after 0.2 s" in actions.LOG[-1]


def test_a_popup_still_up_hands_back_after_its_timeout(game, clock):
    shows(game, "HomeReached", looks=99)
    actions.DismissShot().run(game.ctx, arg("Notices", json.dumps({"back": True, **UNTIL_HOME})))
    assert game.keys == [actions.BACK_KEY] and 1.5 <= sum(clock) < 1.8
    assert "Notices: no change after 1.6 s" in actions.LOG[-1]


def test_a_popup_without_until_does_not_wait(game, clock):
    actions.DismissShot().run(game.ctx, arg("PopupButton", "null"))  # MaaFramework's param when the node sets none
    assert game.taps == [(120, 210)] and clock == []  # its post_delay waits instead
