"""End a Mirror Dungeon run early from a battle, with no Claim: Give Up, Forfeit, Defeat, then GiveUpRewards.

    uv run --group probe python tools/live/giveup.py [--port 16384] run --out DIR [--timeout S]
    uv run --group probe python tools/live/giveup.py look [--json] IMAGE...

A live test that needs only the early floors forfeits the run and gives its rewards up, with no Claim (the user's
standing rule): no Enkephalin Module is spent. Run it with the bot stopped or frozen; a live test owns the emulator
first (the maalc-live-test skill).

**run** looks at the screen, taps what that screen asks, and looks again, until the main window shows after
GiveUpRewards:

  BattleTurn (the planning phase)        the gear, top right; it takes a tap only in the planning phase
  BattlePause (a turn playing out)       no tap: wait for the planning phase
  BattleMenu (the pause menu)            Give Up
  WipeDialog (DEFEAT, the team wiped)    Accept results, then Confirm 1.2 s later with no look between (the cards
                                         read the same picked or not; the bot's Wipe taps them so too): to the map
  Formation (the bot stopped there)      back: to the map
  MapNodePanel (a node's panel open)     the Back key: it closes the panel, and the next look sees MirrorMap; live
                                         (2026-11-08) the gear took no tap while the panel was open
  MirrorMap                              the gear
  ProgressPanel (Dungeon Progress)       Forfeit
  ForfeitDialog (Quit exploring the dungeon?)   Confirm
  DefeatScreen                           Confirm
  ExplorationComplete                    Claim Rewards: it only opens the Exploration Reward window
  ExplorationReward                      GiveUpRewards; live (2026-11-07) it brought no dialog: Connecting, Now Loading,
                                         then the main window (HomeReached), the end
  GiveUpDialog (End expedition without claiming rewards?)   Confirm, when it shows; the reward window then fades out
  ClaimDialog (a Claim's confirm dialog) Cancel; the window's Claim is never tapped

It may start on any of these screens. Each screen is named with the pipeline's own node (`look`'s probe), and the three
dialogs with the text the bot reads inside its actions; it is checked before every tap but WipeDialog's Confirm. A screenshot of each screen
before its tap goes to --out, and one of the main window at the end. Exit 1, with a screenshot, when no known screen
shows for --timeout seconds (60), one screen stays after its looks, or the main window shows before any give-up.

**look** names the screen of each image with the same probe: the tests' seam, and a check on a capture.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from live import screen_probe  # noqa: E402

BATTLE_GEAR = (1235, 40)  # the pause menu's gear, top right of the planning phase (tests/screens/BattleTurn.png)
GIVE_UP = (640, 428)  # the pause menu's Give Up bar (BattleMenu.png)
ACCEPT_RESULTS, WIPE_CONFIRM = (790, 446), (645, 527)  # the DEFEAT dialog's card and Confirm (actions.DEFEAT_OPTIONS, DEFEAT_CONFIRM)
FORMATION_BACK = (98, 43)  # actions.FORMATION_BACK
MAP_GEAR = (1232, 45)  # map_actions.GEAR
FORFEIT = (541, 435)  # the Dungeon Progress panel's Forfeit (map_actions.FORFEIT)
FORFEIT_CONFIRM = (760, 488)  # map_actions.FORFEIT_CONFIRM
FORFEIT_DIALOG = [450, 335, 380, 40]  # map_actions.FORFEIT_DIALOG
DEFEAT_CONFIRM = (1127, 568)  # the centre of DefeatScreen's target
CLAIM_REWARDS = (1135, 597)  # the centre of ExplorationComplete's target
GIVE_UP_REWARDS = (393, 544)  # actions.GIVE_UP
DIALOG_TEXT = [360, 280, 560, 140]  # actions.DIALOG_TEXT
DIALOG_CANCEL, DIALOG_CONFIRM = (515, 493), (763, 493)  # actions.DIALOG_CANCEL, actions.DIALOG_CONFIRM
# Copied, not imported: agent/actions.py and its page modules import MaaFramework's AgentServer, and a process that has
# loaded it runs no Tasker of its own (the tests run theirs in a child process, tests/test_hub_text_screens.py).
# tests/test_live_giveup.py checks that they match.


class Key(NamedTuple):
    code: int  # an Android key code, pressed in place of a tap

    def __str__(self):
        return f"key {self.code}"


BACK = Key(4)  # actions.BACK_KEY: closes the node panel


class Step(NamedTuple):
    taps: tuple  # the points tapped (or Keys pressed) in turn, TAP_GAP s apart; none: only wait
    wait: float  # s before the next look
    tries: int  # looks in a row at this screen before it gives up


TAP_GAP = 1.2  # s between two taps of one screen: the DEFEAT dialog's card, then its Confirm (as the bot's Wipe waits)
# Screen -> its step, in the order the probe tries them: the first that hits names the screen. Dialogs come before the
# page under them, which still reads (GiveUpDialog.png reads as ExplorationReward too, ForfeitDialog.png and
# DungeonProgress.png as MirrorMap, BattleMenu.png as BattleTurn).
STEPS = {
    "GiveUpDialog": Step((DIALOG_CONFIRM,), 3, 3),
    "ClaimDialog": Step((DIALOG_CANCEL,), 2, 3),
    "ExplorationReward": Step((GIVE_UP_REWARDS,), 2, 3),
    "ExplorationComplete": Step((CLAIM_REWARDS,), 3, 3),
    "DefeatScreen": Step((DEFEAT_CONFIRM,), 3, 3),
    "ForfeitDialog": Step((FORFEIT_CONFIRM,), 5, 3),
    "ProgressPanel": Step((FORFEIT,), 2, 3),
    "WipeDialog": Step((ACCEPT_RESULTS, WIPE_CONFIRM), 3, 3),
    "Formation": Step((FORMATION_BACK,), 2, 3),
    "MapNodePanel": Step((BACK,), 2, 3),
    "MirrorMap": Step((MAP_GEAR,), 2, 3),
    "BattleMenu": Step((GIVE_UP,), 5, 3),
    "BattleTurn": Step((BATTLE_GEAR,), 1.5, 20),
    "BattlePause": Step((), 1, 180),
}
# The probe's own nodes: the dialogs the bot reads inside Settle and forfeit, not as pipeline nodes.
DIALOG_NODES = {
    "GiveUpDialog": {"recognition": "OCR", "roi": DIALOG_TEXT, "expected": "without claiming"},
    "ClaimDialog": {"recognition": "OCR", "roi": DIALOG_TEXT, "expected": "without using|Claim the rewards|Spend your"},
    "ForfeitDialog": {"recognition": "OCR", "roi": FORFEIT_DIALOG, "expected": "Quit exploring"},
}
# After GiveUpRewards (and its dialog's Confirm, when one shows) these fade out: nothing is tapped on them again, for up
# to FADE_LOOKS looks a second apart in all, whichever of them shows.
FADING = ("ExplorationReward", "ExplorationComplete")
FADE_LOOKS = 10
# The end: the main window, after GiveUpRewards (live 2026-11-07: with no dialog, then Connecting and Now Loading) or
# after the dialog's Confirm. Tried after every step's screen.
END = "HomeReached"
PROBE = "GiveUpProbe"
SCREENS = (*STEPS, END)  # the probe's order
LOOK_MS = 1500  # how long one look tries before it names no screen


def probe_override() -> dict:
    """The pipeline override of one look: the screens tried in order, each with its action switched off."""
    return screen_probe.override(PROBE, SCREENS, LOOK_MS, DIALOG_NODES)


def first_hit(node_names: list[str]) -> str | None:
    return screen_probe.first_hit(node_names, SCREENS)


def tasker(controller, resource: Path):
    from maa.resource import Resource
    from maa.tasker import Tasker

    res = Resource()
    res.post_bundle(str(resource)).wait()
    t = Tasker()
    t.bind(res, controller)
    return t


def look(t) -> str | None:
    """The screen the probe names now, or None."""
    return screen_probe.look(t, PROBE, probe_override(), SCREENS)


def give_up(look, tap, shot, key, timeout: float = 60, clock=time.monotonic, sleep=time.sleep, say=print) -> int:
    """Look, tap (or press the key) what the screen asks, look again, until the main window shows after GiveUpRewards (exit 0). After
    GiveUpRewards only the give-up dialog's Confirm is tapped. Exit 1 when no known screen shows for `timeout` seconds,
    one screen stays after its looks in a row, the reward screens stay FADE_LOOKS looks after GiveUpRewards, or the main
    window shows before any give-up (no run to end).
    """
    known_at, last, in_row, gave_up, faded = clock(), None, 0, False, 0
    while True:
        name = look()
        if name == END:
            shot("end")
            if gave_up:
                say("the main window: the run is over, its rewards given up, nothing claimed")
                return 0
            say("stop: the main window, and no run was given up here")
            return 1
        if name is None:
            if clock() - known_at >= timeout:
                shot("unknown")
                say(f"stop: no known screen for {timeout:.0f} s")
                return 1
            sleep(1)
            continue
        known_at = clock()
        in_row = in_row + 1 if name == last else 1
        last = name
        step = STEPS[name]
        if gave_up and name in FADING:
            faded += 1
            if faded > FADE_LOOKS:
                shot(f"stuck-{name}")
                say(f"stop: the reward screens stayed {FADE_LOOKS} looks after GiveUpRewards")
                return 1
            sleep(1)
            continue
        if in_row > step.tries:
            shot(f"stuck-{name}")
            say(f"stop: {name} stayed after {in_row - 1} looks")
            return 1
        if step.taps:
            shot(name)
            for i, xy in enumerate(step.taps):
                if i:
                    sleep(TAP_GAP)
                if isinstance(xy, Key):
                    key(xy.code)
                else:
                    tap(*xy)
            say(f"{name}: tap {' then '.join(map(str, step.taps))}")
            gave_up = gave_up or name in ("ExplorationReward", "GiveUpDialog")
        sleep(step.wait)


def still_controller():
    """A controller whose screen is the image put in `.image` (BGR, 1280x720), and nothing moves."""
    import numpy as np
    from maa.controller import CustomController

    class Still(CustomController):
        image = np.zeros((720, 1280, 3), np.uint8)

        def connect(self):
            return True

        def request_uuid(self):
            return "giveup-look"

        def screencap(self):
            return self.image

        def __getattr__(self, name):
            return lambda *args: True

    ctl = Still()
    ctl.post_connection().wait()
    return ctl


def look_files(files: list[str], resource: Path) -> dict:
    import numpy as np
    from PIL import Image

    ctl = still_controller()
    t = tasker(ctl, resource)
    named = {}
    for f in files:
        ctl.image = np.ascontiguousarray(np.asarray(Image.open(f).convert("RGB"))[:, :, ::-1])
        named[Path(f).name] = look(t)
        print(f"{Path(f).name}: {named[Path(f).name]}", flush=True)
    return named


def run(a) -> int:
    from live.device import connect, shot, stamp

    ctl = connect(a.port)
    t = tasker(ctl, a.resource)
    a.out.mkdir(parents=True, exist_ok=True)

    def say(line):
        print(stamp(), line, flush=True)

    return give_up(lambda: look(t), lambda x, y: ctl.post_click(x, y).wait(),
                   lambda name: shot(ctl, a.out / f"{stamp()}-{name}.png"), lambda code: ctl.post_click_key(code).wait(),
                   timeout=a.timeout, say=say)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=16384)
    ap.add_argument("--resource", type=Path, default=REPO / "assets/resource/base")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--out", type=Path, required=True, help="the screenshots, HHMMSS.fff-<screen>.png")
    p.add_argument("--timeout", type=float, default=60)
    p = sub.add_parser("look")
    p.add_argument("--json", action="store_true", help="the names as one JSON line at the end")
    p.add_argument("images", nargs="+")
    a = ap.parse_args(argv)
    if a.command == "run":
        return run(a)
    if a.command == "look":
        named = look_files(a.images, a.resource)
        if a.json:
            print(json.dumps(named))
    return 0


if __name__ == "__main__":
    sys.exit(main())
