"""The title's User Agreement and the game's download and update dialogs (#85, #86), on the live captures."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

import actions
from test_pipeline import load_nodes

SCREENS = Path(__file__).parent / "screens"
UNTICKED, TICKED = (np.asarray(Image.open(SCREENS / f"{n}.png").convert("RGB"))[:, :, ::-1].copy()
                    for n in ("UserAgreement", "UserAgreementTicked"))


def tick(image, box):
    x, y = box
    out = image.copy()
    a, b = 4, actions.AGREE_SIZE + 4  # the box's frame too
    out[y - a:y + b, x - a:x + b] = TICKED[y - a:y + b, x - a:x + b]
    return out


@pytest.fixture
def game(monkeypatch):
    """A fake game on the User Agreement: a tap on a box ticks it unless frozen; taps and stops are recorded."""
    state = SimpleNamespace(image=UNTICKED, taps=[], stops=[], frozen=False)
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: state.image

    def click(x, y):
        state.taps.append((x, y))
        n = actions.AGREE_SIZE
        for box in actions.AGREE_BOXES:
            if not state.frozen and box[0] <= x < box[0] + n and box[1] <= y < box[1] + n:
                state.image = tick(state.image, box)
        return MagicMock()
    ctx.tasker.controller.post_click.side_effect = click
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "stop", lambda context, reason, line=None, whole_list=False: state.stops.append(reason) or False)
    actions.RUN.clear()
    actions.RUN["settings"] = {"run": {"auto_accept_terms": True, "auto_download": True}}
    actions.STUCK["updates"] = 0
    state.ctx = ctx
    yield state
    actions.RUN.clear()
    actions.STUCK["updates"] = 0


def test_the_boxes_read_ticked_or_not():
    assert not any(actions.agree_ticked(UNTICKED, *b) for b in actions.AGREE_BOXES)
    assert all(actions.agree_ticked(TICKED, *b) for b in actions.AGREE_BOXES)


def test_sweep_where_both_boxes_read_ticked():
    # CODING_STANDARDS: the brightness test's false positives over tests/screens. Harmless: it is read only once
    # UserAgreement hit, and a box reading ticked by mistake is only left untapped (Confirm stays dim).
    hits = []
    for png in sorted(SCREENS.glob("*.png")):
        image = np.asarray(Image.open(png).convert("RGB"))[:, :, ::-1]
        if image.shape[:2] == (720, 1280) and all(actions.agree_ticked(image, *b) for b in actions.AGREE_BOXES):
            hits.append(png.name)
    assert hits == ["BattleTurnLit.png", "BossGiftTrialsHard.png", "EventNotices.png", "Mailbox.png", "RunVictory.png",
                    "SinnersTab.png", "SystemNotices.png", "TeamSelect.png", "Title.png", "UserAgreementTicked.png"]


def test_both_boxes_are_ticked_then_confirm(game):
    assert actions.AcceptTerms().run(game.ctx, None)
    boxes = [(x + actions.AGREE_SIZE // 2, y + actions.AGREE_SIZE // 2) for x, y in actions.AGREE_BOXES]
    assert game.taps == [*boxes, actions.AGREE_CONFIRM]
    assert all(actions.agree_ticked(game.image, *b) for b in actions.AGREE_BOXES)


def test_a_ticked_box_is_not_tapped_again(game):
    game.image = TICKED
    actions.AcceptTerms().run(game.ctx, None)
    assert game.taps == [actions.AGREE_CONFIRM]  # a tap would untick it


def test_no_confirm_while_a_box_stays_unticked(game):
    game.frozen = True
    assert actions.AcceptTerms().run(game.ctx, None)  # MirrorHub looks again
    assert actions.AGREE_CONFIRM not in game.taps


def test_terms_off_stops_without_a_tap(game):
    actions.RUN["settings"]["run"]["auto_accept_terms"] = False
    assert not actions.AcceptTerms().run(game.ctx, None)
    assert game.taps == [] and "auto_accept_terms" in game.stops[0]


def test_download_off_stops_without_a_tap(game):
    actions.RUN["settings"]["run"]["auto_download"] = False
    box = SimpleNamespace(box=[600, 460, 80, 20])
    assert not actions.ConfirmDownload().run(game.ctx, box)
    assert not actions.AcceptUpdate().run(game.ctx, box)
    assert game.taps == [] and len(game.stops) == 2
    game.ctx.run_task.assert_not_called()


def test_an_update_dialog_is_pressed_and_the_game_restarted(game):
    actions.RUN.update(turn=(None, 3), map_misses=2)
    assert actions.AcceptUpdate().run(game.ctx, SimpleNamespace(box=[600, 460, 80, 20]))
    assert game.taps == [(640, 470)]
    game.ctx.run_task.assert_called_once_with("RecoverL3")
    assert "turn" not in actions.RUN and "map_misses" not in actions.RUN  # the restarted game starts the battle over


def test_an_update_notice_that_keeps_coming_back_stops_the_bot(game):
    box = SimpleNamespace(box=[600, 460, 80, 20])
    assert actions.AcceptUpdate().run(game.ctx, box) and actions.AcceptUpdate().run(game.ctx, box)
    assert not actions.AcceptUpdate().run(game.ctx, box)
    assert game.ctx.run_task.call_count == 2 and "update" in game.stops[0]


def test_confirm_download_taps_the_button_and_holds_the_watchdog(game):
    # #86: until the download's progress screen is up, nothing counts as stuck.
    actions.STUCK["watch"].reset()
    actions.ConfirmDownload().run(game.ctx, SimpleNamespace(box=[700, 450, 100, 30]))
    assert game.taps == [(750, 465)]
    assert actions.STUCK["watch"].held(actions.time.monotonic() + 60)
    actions.STUCK["watch"].reset()


def test_a_download_starts_the_floor_clock_over(game, monkeypatch):
    # Live 2026-10-21: 32 min of download; the floor's limit would have restarted the game mid-download.
    monkeypatch.setattr(actions.time, "time", lambda: 5000.0)
    actions.RUN.update(deadline=0, floor_limit=2700)
    actions.ConfirmDownload().run(game.ctx, SimpleNamespace(box=[600, 460, 80, 20]))
    assert actions.RUN["deadline"] == 7700
    monkeypatch.setattr(actions.time, "time", lambda: 9000.0)
    actions.StuckFlag.see("Downloading", UNTICKED)  # any picture: the clock goes by the screen type
    assert actions.RUN["deadline"] == 11700  # still downloading: the floor's whole time is left after it
    actions.STUCK["watch"].reset()


def test_a_client_too_old_for_the_server_stops_the_bot_without_a_tap(game):
    # #86 live 2026-10-22: `Game client is not up to date`, Close / Go to Store, after TOUCH TO START. The bot leaves
    # the store alone (Close only brings the dialog back): it stops, the webhook says why.
    nodes = load_nodes()
    node = nodes["ClientOutdated"]
    assert node["action"] == "Custom" and node["custom_action"] == "Halt"
    entries = nodes["HubText"]["custom_recognition_param"]["entries"]
    assert entries.index("ClientOutdated") < min(entries.index("DownloadDialog"), entries.index("PopupButton"))
    argv = SimpleNamespace(node_name="ClientOutdated", custom_action_param=json.dumps(node["custom_action_param"]))
    assert not actions.Halt().run(game.ctx, argv)
    assert game.taps == [] and "Play Store" in game.stops[0]
