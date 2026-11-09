"""tools/live/giveup.py: ends a Mirror Dungeon run early from a battle, with no Claim.

Its probe names each screen of the way with the pipeline's own nodes (and three dialogs the bot reads inside its
actions), on the live captures of tests/screens. The probe runs MaaFramework, which the pytest process holds in
AgentServer mode: `giveup.py look` runs in a child process, once for every capture.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_pause_menus import BATTLE_BARS, PANEL_BUTTONS, inside, touches
from test_pipeline import load_nodes

from live import giveup as gu

REPO = Path(__file__).resolve().parent.parent
SCREENS = REPO / "tests/screens"

# capture -> the screen the probe must name (None: none of the way's)
NAMED = {
    "BattleTurn.png": "BattleTurn",
    "BattleMenu.png": "BattleMenu",
    "BattlePause.png": "BattlePause",
    "WipeDialog.png": "WipeDialog",
    "Formation.png": "Formation",
    "FormationDetails.png": "Formation",
    "MapNodePanel.png": "MapNodePanel",
    "MirrorMap.png": "MirrorMap",
    "DungeonProgress.png": "ProgressPanel",
    "ProgressPanel.png": "ProgressPanel",
    "ForfeitDialog.png": "ForfeitDialog",
    "DefeatScreen.png": "DefeatScreen",
    "ExplorationComplete.png": "ExplorationComplete",
    "ExplorationReward.png": "ExplorationReward",
    "ExplorationRewardOff.png": "ExplorationReward",
    "GiveUpDialog.png": "GiveUpDialog",
    "ClaimNoBonusDialog.png": "ClaimDialog",
    "ClaimBonusDialog.png": "ClaimDialog",
    "MainWindow.png": "HomeReached",
    "Drive.png": None,
}


@pytest.fixture(scope="module")
def named():
    done = subprocess.run([sys.executable, str(REPO / "tools/live/giveup.py"), "look", "--json", *(str(SCREENS / f) for f in NAMED)],
                          capture_output=True, text=True, timeout=240, cwd=REPO)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("capture", list(NAMED))
def test_the_probe_names_each_screen_of_the_way(named, capture):
    assert named[capture] == NAMED[capture]


GEAR_BOX = (1211, 17, 49, 46)  # the planning phase's gear, top right, measured on BattleTurn.png
CLAIM_BOX = (774, 523, 226, 43)  # the Exploration Reward window's Claim, measured on ExplorationReward.png


def point(xy):
    return (*xy, 1, 1)


def test_the_taps_are_the_bots_own():
    import actions

    def centre(target):
        x, y, w, h = target
        return (x + w // 2, y + h // 2)

    nodes = load_nodes()
    assert (gu.MAP_GEAR, gu.FORFEIT, gu.FORFEIT_CONFIRM) == (actions.GEAR, actions.FORFEIT, actions.FORFEIT_CONFIRM)
    assert (gu.FORFEIT_DIALOG, gu.DIALOG_TEXT) == (actions.FORFEIT_DIALOG, actions.DIALOG_TEXT)
    assert (gu.GIVE_UP_REWARDS, gu.DIALOG_CANCEL, gu.DIALOG_CONFIRM) == (actions.GIVE_UP, actions.DIALOG_CANCEL, actions.DIALOG_CONFIRM)
    assert (gu.ACCEPT_RESULTS, gu.WIPE_CONFIRM, gu.FORMATION_BACK) == (actions.DEFEAT_OPTIONS["forfeit"], actions.DEFEAT_CONFIRM,
                                                                     actions.FORMATION_BACK)
    assert gu.DEFEAT_CONFIRM == centre(nodes["DefeatScreen"]["custom_action_param"]["target"])
    assert gu.CLAIM_REWARDS == centre(nodes["ExplorationComplete"]["custom_action_param"]["target"])


def test_the_battle_taps_land_on_the_gear_give_up_and_forfeit():
    assert inside(point(gu.BATTLE_GEAR), GEAR_BOX)
    assert inside(point(gu.GIVE_UP), BATTLE_BARS["Give Up"])
    assert inside(point(gu.FORFEIT), PANEL_BUTTONS["Forfeit"])


def test_claim_is_never_tapped():
    taps = {name: tuple(xy for xy in step.taps if not isinstance(xy, gu.Key)) for name, step in gu.STEPS.items()}
    assert not any(touches(point(xy), CLAIM_BOX) for points in taps.values() for xy in points)
    # A dialog's Confirm sits where a Claim dialog's does: it is tapped on the give-up dialog only; a Claim dialog is cancelled.
    assert [n for n, points in taps.items() if gu.DIALOG_CONFIRM in points] == ["GiveUpDialog"]
    assert taps["ClaimDialog"] == (gu.DIALOG_CANCEL,)


def test_the_probe_names_only_screens_with_a_node():
    nodes = load_nodes()
    assert not set(gu.DIALOG_NODES) & set(nodes) and gu.PROBE not in nodes  # the probe's own nodes override no pipeline node
    assert set(gu.STEPS) - set(gu.DIALOG_NODES) <= set(nodes)


class Game:
    """The screens a run's looks show in turn, a clock the sleeps move, and what was tapped and shot."""

    def __init__(self, screens):
        self.screens, self.now, self.taps, self.shots, self.said = list(screens), 0.0, [], [], []

    def look(self):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]

    def run(self, timeout=60):
        return gu.give_up(self.look, lambda x, y: self.taps.append((x, y)), self.shots.append,
                          key=lambda code: self.taps.append(gu.Key(code)), timeout=timeout,
                          clock=lambda: self.now, sleep=self.sleep, say=self.said.append)

    def sleep(self, s):
        self.now += s


def test_a_run_ends_from_a_turn_playing_out_to_the_give_up_dialogs_confirm():
    game = Game(["BattlePause", "BattleTurn", "BattleTurn", "BattleMenu", None, "MirrorMap", "ProgressPanel", "ForfeitDialog",
                 "DefeatScreen", "ExplorationComplete", "ExplorationReward", "GiveUpDialog", "ExplorationReward", "ExplorationComplete",
                 None, "HomeReached"])
    assert game.run() == 0
    assert game.taps == [gu.BATTLE_GEAR, gu.BATTLE_GEAR, gu.GIVE_UP, gu.MAP_GEAR, gu.FORFEIT, gu.FORFEIT_CONFIRM, gu.DEFEAT_CONFIRM,
                         gu.CLAIM_REWARDS, gu.GIVE_UP_REWARDS, gu.DIALOG_CONFIRM]  # nothing after the confirm: the window fades out
    assert game.shots[-1] == "end" and game.shots[:3] == ["BattleTurn", "BattleTurn", "BattleMenu"]


def test_the_end_waits_for_the_reward_window_to_go():
    # After the give-up Confirm the window fades out: no tap, and success only once it has gone.
    game = Game(["GiveUpDialog", "ExplorationReward"])
    assert game.run() == 1
    assert game.taps == [gu.DIALOG_CONFIRM] and game.shots[-1] == "stuck-ExplorationReward"


def test_a_wipe_accepts_the_results_and_a_formation_backs_out_to_the_map():
    # The bot stops at either when it ran out of retries or sinners (`after_retries: stop`): both lead to the map's Forfeit.
    game = Game(["WipeDialog", "Formation", "MirrorMap", "ProgressPanel", "ForfeitDialog", "DefeatScreen", "ExplorationComplete",
                 "ExplorationReward", "GiveUpDialog", None, "HomeReached"])
    assert game.run() == 0
    assert game.taps[:4] == [gu.ACCEPT_RESULTS, gu.WIPE_CONFIRM, gu.FORMATION_BACK, gu.MAP_GEAR]


def test_an_open_node_panel_is_closed_with_back_before_the_gear(named):
    # Live 2026-11-08 (#585): with the node panel open the gear did not respond; Back closed it, then the map's gear did.
    assert gu.STEPS[named["MapNodePanel.png"]].taps == (gu.BACK,)
    game = Game(["MapNodePanel", "MirrorMap", "ProgressPanel", "ForfeitDialog", "DefeatScreen", "ExplorationComplete",
                 "ExplorationReward", "GiveUpDialog", None, "HomeReached"])
    assert game.run() == 0
    assert game.taps[:3] == [gu.BACK, gu.MAP_GEAR, gu.FORFEIT] and game.shots[:2] == ["MapNodePanel", "MirrorMap"]


def test_back_is_the_bots_back_key():
    import actions

    assert gu.BACK == gu.Key(actions.BACK_KEY)


def test_the_give_up_dialog_is_confirmed_again_while_it_stays():
    game = Game(["GiveUpDialog", "GiveUpDialog", None, "HomeReached"])
    assert game.run() == 0 and game.taps == [gu.DIALOG_CONFIRM] * 2


def test_giveuprewards_with_no_dialog_ends_on_the_main_window():
    # Live 2026-11-07, a forfeited NORMAL floor 1: GiveUpRewards brought no dialog; Connecting, Now Loading, the main window.
    game = Game(["ExplorationReward", None, None, "HomeReached"])
    assert game.run() == 0 and game.taps == [gu.GIVE_UP_REWARDS] and game.shots[-1] == "end"


def test_nothing_behind_the_give_up_is_tapped_again_while_it_fades_out():
    # With no dialog the window and the page under it may still read for a moment after GiveUpRewards.
    game = Game(["ExplorationReward", "ExplorationReward", "ExplorationComplete", None, "HomeReached"])
    assert game.run() == 0 and game.taps == [gu.GIVE_UP_REWARDS]


def test_reward_screens_that_keep_alternating_after_the_give_up_stop_it():
    # A screen change resets the looks-in-a-row count: the fade has a count of its own.
    game = Game(["GiveUpDialog"] + ["ExplorationReward", "ExplorationComplete"] * 200)
    assert game.run() == 1
    assert game.taps == [gu.DIALOG_CONFIRM] and game.shots[-1].startswith("stuck-") and len(game.screens) > 350


def test_the_main_window_before_any_give_up_is_no_run_to_end():
    game = Game(["HomeReached"])
    assert game.run() == 1 and game.taps == []


def test_no_known_screen_for_the_timeout_stops_with_a_screenshot():
    game = Game(["BattleMenu", None])
    assert game.run(timeout=30) == 1
    assert game.taps == [gu.GIVE_UP] and game.shots[-1] == "unknown" and 30 <= game.now <= 40


def test_a_screen_that_stays_after_its_taps_stops():
    game = Game(["ProgressPanel"])
    assert game.run() == 1
    assert game.taps == [gu.FORFEIT] * gu.STEPS["ProgressPanel"].tries and game.shots[-1] == "stuck-ProgressPanel"
