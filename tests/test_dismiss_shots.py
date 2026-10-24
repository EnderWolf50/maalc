"""A screen the bot dismisses is kept in logs/dismissed/ first (#244)."""

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


def arg(node, param=None, box=(100, 200, 40, 20)):
    return SimpleNamespace(node_name=node, custom_action_param=param, box=box)


def test_the_screen_is_kept_under_its_time_and_node_before_the_key(game):
    assert actions.DismissShot().run(game.ctx, arg("Notices", '"back"'))
    (shot,) = game.folder.iterdir()
    assert shot.name.endswith("-Notices.png") and shot.read_bytes().startswith(b"\x89PNG")
    assert game.keys == [actions.BACK_KEY] and game.taps == []


def test_a_box_is_tapped_at_its_centre(game):
    actions.DismissShot().run(game.ctx, arg("PopupButton"))
    assert game.taps == [(120, 210)] and game.keys == []
    assert len(list(game.folder.iterdir())) == 1


def test_off_dismisses_without_a_shot(game):
    actions.RUN["settings"]["run"]["keep_dismissed_screens"] = False
    actions.DismissShot().run(game.ctx, arg("PopupButton"))
    assert game.taps == [(120, 210)] and not game.folder.exists()


def test_a_full_disk_does_not_keep_the_popup_open(game, monkeypatch):
    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(recovery, "keep_capture", fail)
    assert actions.DismissShot().run(game.ctx, arg("PopupButton"))
    assert game.taps == [(120, 210)]
    assert "PopupButton" not in actions.DISMISSED_AT  # a failed save does not start the gap


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
    assert [n for n in ("Notices", "HelpPager", "RecoverL1") if nodes[n].get("custom_action_param") != "back"] == []
