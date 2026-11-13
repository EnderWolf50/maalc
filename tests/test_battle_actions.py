"""The battle actions (agent/battle_actions.py): the formation, the turns, and a battle's end.

Split out of tests/test_actions.py (#713); the fake Maa context and the helpers other files share stay there."""

import itertools
import time
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import DEFAULT, MagicMock

import numpy as np
import pytest
from PIL import Image

import actions
import battle_actions
import recovery
import battle
import run_start
from agent_patch import patch_all
import test_actions

from test_actions import SCREENS, TimedGame, hits, page_until, reads, screens, taps

clock, context, guarded = test_actions.clock, test_actions.context, test_actions.guarded  # its fixtures


def test_a_missed_victory_does_not_carry_the_battle_clock_into_the_next_battle(context):
    # #80: the last battle ended without VICTORY being seen, its clock and turn count left behind.
    actions.RUN["battle_start"] = time.time() - recovery.BATTLE_LIMIT - 60
    actions.RUN["turn"] = (None, 3)
    battle_actions.Formation().run(context, None)  # the next battle's formation (fading in: no count read)
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[600, 400, 40, 20]))
    assert actions.STUCK["flag"] is None


def test_a_formation_page_still_fading_in_is_read_once_it_is_still(context, monkeypatch):
    # Live (#58): read mid-fade, Total Participants gave 3 alive of 12.
    actions.RUN.update(team={"min_alive": 5, "name": "t"}, settings={"run": {"after_retries": "stop"}})
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: False)
    patch_all(monkeypatch, "tap_shown", lambda *a, **k: None)
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: [])  # ends the action after the count
    screens(context, [60, 120, 120])
    reads_by_image = {60: "3/3", 120: "12/12"}

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        t = reads_by_image.get(int(image[0, 0, 0])) if roi == tuple(battle_actions.PARTICIPANTS) else None
        return SimpleNamespace(all_results=[SimpleNamespace(text=t, box=(1125, 500, 60, 30))]) if t else None
    context.run_recognition.side_effect = run_recognition
    battle_actions.Formation().run(context, None)
    assert actions.RUN["alive"] == 12


def few_alive(context, monkeypatch, after_retries, min_alive):
    """A formation page with 4 of 12 alive; the stops and taps it leads to."""
    actions.RUN.update(team={"min_alive": min_alive, "name": "t"}, settings={"run": {"after_retries": after_retries}})
    stops, taps = [], []
    patch_all(monkeypatch, "stop", lambda context, reason, line=None: stops.append(reason) or False)
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))
    monkeypatch.setattr(run_start, "resolve_plan", lambda *a: [])  # ends the action after the count
    reads(context, {tuple(battle_actions.PARTICIPANTS): [("4/4", (1125, 500, 60, 30))],
                    tuple(battle_actions.DETAILS_BUTTON): [("Details", (0, 0, 10, 10))]})
    result = battle_actions.Formation().run(context, None)
    return result, stops, taps


def test_too_few_alive_forfeits_the_run_like_used_up_wipe_retries(context, monkeypatch):
    # #137: fewer than K alive goes the way of after_retries; forfeit backs out to the map, RouteMap forfeits there.
    result, stops, taps = few_alive(context, monkeypatch, "forfeit", 5)
    assert result is True and stops == []
    assert actions.RUN["forfeit"]
    assert taps == [battle_actions.FORMATION_BACK]


def test_too_few_alive_stops_when_used_up_wipe_retries_stop(context, monkeypatch):
    result, stops, taps = few_alive(context, monkeypatch, "stop", 5)
    assert result is False and len(stops) == 1 and taps == []


def test_no_alive_check_at_0(context, monkeypatch):
    result, stops, taps = few_alive(context, monkeypatch, "forfeit", 0)
    assert all("deployment order" in s for s in stops)  # only the empty order (the stub) stops it
    assert "forfeit" not in actions.RUN


def win_rate_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == (984 + 20, 531 + 14)]


def test_a_turn_label_on_a_moving_screen_is_not_played(context):
    # Live (#58): the label matched in the first frames of a turn playing out; Win Rate and START were tapped.
    screens(context, [0, 60, 120, 180, 240, 30, 90, 150, 210, 20, 80, 140])
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    context.tasker.controller.post_click.assert_not_called()


def test_a_turn_over_a_moving_battlefield_is_played(context, monkeypatch):
    # Live 2026-10-21: a swarm of enemies moved over the whole battlefield, the HUD at rest; the screen never
    # read still and turn 3 waited 18 min, twice (BattleTurnSwarm*.png, 3 s apart).
    frames = [np.asarray(Image.open(SCREENS / f"BattleTurnSwarm{s}.png"))[:, :, ::-1] for s in ("", "Next")]
    shots = itertools.cycle(frames)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = lambda: next(shots)
    clicks = context.tasker.controller.post_click.call_args_list
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: bool(clicks))  # lit by the Win Rate tap
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[946, 531, 40, 29]))
    assert [c.args for c in clicks[:2]] == [(946 + 20, 531 + 14), (946 + battle_actions.START_DISC[0], 531 + battle_actions.START_DISC[1])]


def test_a_win_rate_tap_lost_in_the_turns_opening_is_tapped_again(context, monkeypatch):
    # Live (#58): 0.3 s after the label showed, a Win Rate tap did nothing: label not pressed, disc unlit.
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: len(win_rate_taps(context)) >= 2)
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert len(win_rate_taps(context)) == 2


def test_a_pressed_win_rate_is_not_tapped_again_while_the_disc_reads_unlit(context, monkeypatch):
    # #69: Win Rate on, the disc dim (staggered slots): a second tap would clear the picks.
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: False)
    pressed = "Battle/BattleTurnPressed.png"

    def run_recognition(name, image, override=None):
        node = (override or {}).get(name, {})
        if name == "BattleTurn" and node.get("template") == pressed and win_rate_taps(context):
            return SimpleNamespace(hit=True, box=[984, 531, 40, 29])
        return None
    context.run_recognition.side_effect = run_recognition
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert len(win_rate_taps(context)) == 1


def test_a_turn_at_rest_is_tapped_one_wait_after_its_label_shows(context, clock, monkeypatch):
    # #177: BattleTurn's 200 ms pre_delay and still()'s 0.2 s between its two screenshots slept back to back (live
    # 2026-11-03 to 07: 201 and 235 ms a turn). Two alike screenshots 0.2 s apart are the rest a tap needs, no more.
    from test_pipeline import load_nodes
    clicks = context.tasker.controller.post_click.call_args_list
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: bool(clicks))
    first = []
    context.tasker.controller.post_click.side_effect = lambda *a: first.append(
        (sum(clock), context.tasker.controller.post_screencap.call_count)) or DEFAULT
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    slept, shots = first[0]
    assert load_nodes("mirror_dungeon.json")["BattleTurn"].get("pre_delay", 200) / 1000 + slept == pytest.approx(0.2)
    assert shots == 3  # still()'s two, then win_rate's look at the disc


def test_a_turn_starts_after_win_rate_lights_the_disc(context, monkeypatch):
    lit = iter([False, True])  # unlit on the turn's first look, lit after the Win Rate tap
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: next(lit, True))
    assert battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))


def touches(context):
    """The controller's touch and tap calls, in order: ("down", (x, y)), ("up", ()), ("click", (x, y))."""
    names = {"post_touch_down": "down", "post_touch_up": "up", "post_click": "click"}
    return [(names[n], a) for n, a, _ in context.tasker.controller.method_calls if n in names]


@pytest.mark.parametrize("shown", [("BattleTurn",), ("Victory",), ("WipeDialog",), ("RetryPopup",), ("Event",)])
def test_a_held_finger_lifts_once_the_next_turn_or_another_screen_shows(context, clock, shown):
    # #150: held from the turn's start until the next turn waits for input or the battle leaves the screen.
    hits(context, *shown)
    battle_actions.hold_turn(context)
    assert touches(context) == [("down", battle_actions.HOLD_SPOT), ("up", ())]
    assert sum(clock) < 1


def test_a_held_finger_stays_down_while_the_pause_button_shows(context, clock):
    # In a turn's first frames the Win Rate label can still match: the pause button says the turn plays.
    hits(context, "BattlePause", "BattleTurn")
    battle_actions.hold_turn(context)
    assert touches(context) == [("down", battle_actions.HOLD_SPOT), ("up", ())]
    assert sum(clock) == pytest.approx(battle_actions.HOLD_LIMIT, abs=battle_actions.HOLD_EVERY)


@pytest.mark.parametrize("shown", battle_actions.BATTLE_POPUPS)
def test_a_held_finger_lifts_on_a_popup_over_the_battle(context, clock, shown):
    # A popup over the battle with the pause button still showing: lift at once, not on it 6 s later.
    hits(context, "BattlePause", shown)
    battle_actions.hold_turn(context)
    assert touches(context) == [("down", battle_actions.HOLD_SPOT), ("up", ())]
    assert sum(clock) < 1


def test_a_held_finger_reads_no_text_while_the_pause_button_shows(context, clock):
    # #157: no OCR while a turn plays. The screens read by text (Victory, the wipe dialog, an event) hide the
    # pause button (maa-tools test: BattlePause misses on each; it scores 0.34 at most, threshold 0.8).
    hits(context, "BattlePause")
    battle_actions.hold_turn(context)
    looked = {c.args[0] for c in context.run_recognition.call_args_list}
    assert looked == {"BattlePause", *battle_actions.BATTLE_POPUPS}


def test_a_held_finger_lifts_through_a_controller_fetched_after_the_looks(context, clock):
    # Live 2026-10-20: in the agent, a controller kept from before the looks (screen() fetches another) failed
    # its touch up with an access violation, every hold: the finger stayed down until the next tap.
    fresh = []

    def controller(self):
        ctl = MagicMock()
        fresh.append(ctl)
        return ctl
    hits(context, "BattleTurn")
    type(context.tasker).controller = property(controller)
    try:
        battle_actions.hold_turn(context)
    finally:
        del type(context.tasker).controller
    assert [c for c in fresh if c.post_touch_up.called] == [fresh[-1]]


def test_a_held_finger_lifts_when_the_task_is_stopping(context, clock):
    # #145: a finger left down when the bot stopped kept the panel tilted; L1-L3 and a game restart followed.
    hits(context, "BattlePause")
    looks = iter([False, False, True])
    type(context.tasker).stopping = property(lambda self: next(looks))
    try:
        battle_actions.hold_turn(context)
    finally:
        del type(context.tasker).stopping
    assert touches(context) == [("down", battle_actions.HOLD_SPOT), ("up", ())]


def test_a_held_finger_lifts_on_an_error(context, clock):
    context.tasker.controller.post_screencap.side_effect = RuntimeError("controller gone")
    with pytest.raises(RuntimeError):
        battle_actions.hold_turn(context)
    assert touches(context) == [("down", battle_actions.HOLD_SPOT), ("up", ())]


def test_a_turn_started_by_play_turn_is_held_until_the_next_turn(context, monkeypatch):
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: True)
    patch_all(monkeypatch, "turn_started", lambda context, image: True)
    hits(context, "BattleTurn")
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert [t for t, _ in touches(context)] == ["click", "down", "up"]  # START, then the hold


def test_a_turn_that_did_not_start_is_not_held(context, monkeypatch):
    monkeypatch.setattr(battle, "disc_lit", lambda image, x, y: True)
    patch_all(monkeypatch, "turn_started", lambda context, image: False)
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert "down" not in [t for t, _ in touches(context)]


def test_the_pause_button_holds_the_turn(context, clock):
    hits(context, "Victory")
    assert battle_actions.HoldTurn().run(context, None)
    assert touches(context) == [("down", battle_actions.HOLD_SPOT), ("up", ())]


GEAR = (272, 557)  # the left gear of a 7-slot panel (battle.guard_chain)


DISC = (918, 557)  # its START disc


WIN_RATE_XY = (1004, 545)


# Slot 2's STAGGER plate of tests/screens/BattleTurnStagger.png (#69), 80 px round its portrait.
STAGGER_PLATE = np.asarray(Image.open(SCREENS / "BattleTurnStagger.png").convert("RGB"))[620:700, 403:483, ::-1]


class Panel:
    """A battle's skill panel (7 slots, Win Rate label at x 984): a portrait tap swaps the slot's lower skill
    and its guard skill. A drag from the left gear links the chain, all but drops[k] slots on the k-th drag
    (live #145: under load the finger crosses a slot between two frames and the chain ends there); a drag
    from the gear or a tap on it while a chain is linked clears it. The disc lights once anything is linked,
    the START plaque shows (and START starts the turn) only once every slot is. units[i] is the unit in
    slot i (slots reorder by speed every turn); guard[u] whether unit u shows its guard skill. The plaque swings
    in plaque_after s after the chain is complete (live 2026-10-18, 30 fps recording: upright 0.33-0.47 s after
    the panel levels, ~0.5-0.65 s after the lift; a minimised emulator held it mid-swing for over 2 s).
    A staggered unit (#427) shows a STAGGER plate for its portrait, which a tap does not swap, and needs no skill: the
    plaque shows once every other slot is linked (#69)."""

    def __init__(self, context, guard, drops=(), lost_start=0, plaque_after=0.6, staggered=()):
        self.xs = battle.slot_xs(984)
        self.units, self.guard, self.dealt = list(range(7)), list(guard), 0
        self.staggered, self.acting = set(staggered), 7 - len(staggered)
        self.linked, self.win_rate, self.started, self.at, self.lifted = 0, False, False, None, -1.0
        self.drops, self.lost_start, self.plaque_after, self.complete_at = list(drops), lost_start, plaque_after, None
        self.drags = []  # how long each chain drag took, s
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.render
        ctl.post_click.side_effect = self.click
        ctl.post_touch_down.side_effect = self.down
        ctl.post_touch_up.side_effect = self.lift
        context.run_recognition.side_effect = self.recognise

    def down(self, x, y, *a):
        self.at, self.t0 = (x, y), actions.time.monotonic()
        return DEFAULT

    def lift(self, *a):
        self.lifted = actions.time.monotonic()
        if self.at == GEAR:
            if self.linked:
                self.linked = 0
            else:
                self.linked = self.acting - (self.drops.pop(0) if self.drops else 0)
                self.complete_at = self.lifted if self.linked == self.acting else None
                self.drags.append(actions.time.monotonic() - self.t0)
        return DEFAULT

    def click(self, x, y):
        if y == battle_actions.SLOT_PORTRAIT_Y:
            u = self.units[min(range(7), key=lambda i: abs(self.xs[i] - x))]
            if u not in self.staggered:
                self.guard[u] = not self.guard[u]
        elif (x, y) == GEAR:
            self.linked = 0
            self.win_rate = False
        elif (x, y) == WIN_RATE_XY:
            self.win_rate = not self.win_rate
            self.linked = self.acting if self.win_rate else 0
            self.complete_at = actions.time.monotonic() if self.win_rate else None
        elif (x, y) == DISC and self.linked == self.acting and actions.time.monotonic() - self.lifted >= 0.15:
            # live #145: a press while the panel still tilts back from a drag misses the disc
            if self.lost_start:
                self.lost_start -= 1
            else:
                self.started = True
        return DEFAULT

    def recognise(self, name, image, override=None):
        node = (override or {}).get(name, {})
        plaque = self.linked == self.acting and actions.time.monotonic() - self.complete_at >= self.plaque_after
        hit = {"BattlePause": self.started, "BattleStart": plaque,
               "BattleTurn": not self.started and actions.time.monotonic() - self.lifted >= 0.15  # live: the panel
               and (self.win_rate or "Pressed" not in node.get("template", ""))}  # tilts back 0.15 s, the label gone
        return SimpleNamespace(hit=True, box=[984, 531, 40, 20]) if hit.get(name) else None

    def next_turn(self, order=None):
        self.linked, self.started, self.win_rate, self.dealt = 0, False, False, self.dealt + 1
        self.units = order or self.units

    def render(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        for i, u in enumerate(self.units):
            x, y = battle_actions.lower_x(self.xs[i]), battle_actions.LOWER_Y
            if self.guard[u]:  # a flat brown icon, its own shape per unit
                image[y - 20:y + 20, x - 20:x + 20] = (50, 100, 150)
                image[y - 15 + u:y - 5 + u, x - 12:x + 2 * u] = (20, 40, 60)
            else:  # line art: a new skill is dealt each turn
                rng = np.random.default_rng(100 * u + self.dealt)
                image[y - 20:y + 20, x - 20:x + 20] = rng.integers(0, 255, (40, 40, 3))
            if u in self.staggered:
                image[620:700, self.xs[i] - 40:self.xs[i] + 40] = STAGGER_PLATE
        if self.linked:
            image[547:567, 908:928] = 255  # the START disc at (918, 557)
        return image


def portrait_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args[1] == battle_actions.SLOT_PORTRAIT_Y]


def guard_turn(context, guard_left=3):
    actions.RUN["guard"] = guard_left
    return battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))


def test_a_first_guard_turn_taps_each_portrait_once_when_every_slot_shows_its_skill(context):
    panel = Panel(context, guard=[False] * 7)
    assert battle_actions.PlayTurn.guard(context, 984, DISC)
    assert panel.started and all(panel.guard)
    assert len(portrait_taps(context)) == 7
    assert [c.args for c in context.tasker.controller.post_click.call_args_list].count(DISC) == 1


def test_slots_already_on_guard_are_swapped_off_and_tapped_back(context):
    # Live (2026-10-18): the swap can stay from the last turn; the first taps then take those slots off guard.
    panel = Panel(context, guard=[True, False, True, False, False, False, True])
    assert battle_actions.PlayTurn.guard(context, 984, DISC)
    assert panel.started and all(panel.guard)
    assert len(portrait_taps(context)) == 7 + 3


def test_a_chain_that_misses_its_tail_is_cleared_and_dragged_again_slower_before_the_turn_starts(context):
    # #145 (live 2026-10-18): the chain ended two slots short, the disc lit anyway and START did nothing.
    panel = Panel(context, guard=[False] * 7, drops=[2])
    guard_turn(context)
    assert panel.started and panel.linked == 7 and not panel.win_rate
    assert len(panel.drags) == 2 and panel.drags[1] > panel.drags[0]
    assert actions.RUN["guard"] == 2


def test_a_chain_that_never_links_falls_back_to_win_rate_and_keeps_the_guard_turn(context):
    # Every drag misses (a heavily loaded PC): the chain is cleared so Win Rate picks every slot; the turn does
    # not count as a guard turn.
    panel = Panel(context, guard=[False] * 7, drops=[1, 1, 1])
    guard_turn(context)
    assert panel.started and panel.win_rate
    assert len(panel.drags) == 3
    assert actions.RUN["guard"] == 3


def test_start_is_pressed_again_within_the_call_when_the_first_press_is_lost(context):
    # #145: a START that did not take went back to MirrorHub: 3 more looks, a stuck and recovery, ~23 s a time.
    panel = Panel(context, guard=[False] * 7, lost_start=1)
    guard_turn(context)
    assert panel.started
    assert actions.RUN["guard"] == 2
    assert actions.STUCK["flag"] is None


def test_a_plaque_still_swinging_in_is_waited_for_before_the_chain_is_dragged_again(context):
    # PR #148 follow-up: a minimised emulator held the plaque mid-swing for over 2 s; one look after START did not
    # take read "no plaque", cleared a complete chain and dragged it again. The plaque is waited for instead.
    panel = Panel(context, guard=[False] * 7, lost_start=1, plaque_after=2.5)
    guard_turn(context)
    assert panel.started and len(panel.drags) == 1
    assert actions.RUN["guard"] == 2


@pytest.fixture
def chains(monkeypatch):
    """The points of every drag the action makes, in order; the drags still reach the fake controller."""
    seen, real = [], actions.drag
    patch_all(monkeypatch, "drag", lambda context, points, **kw: seen.append(points) or real(context, points, **kw))
    return seen


def test_a_guard_turn_with_staggered_slots_guards_the_rest_and_counts(context, chains):
    # #427 (live 2026-11-04, EXP Luxcavation turn 5): slots 6 and 7 STAGGER+. A tap on their portraits swaps nothing,
    # so their guard skills could not be told and the whole team played Win Rate. Now they are left out: the other
    # portraits are tapped (slot 2's twice, it was on guard), the chain links slots 1-5, and the turn counts.
    panel = Panel(context, guard=[False, True, False, False, False, False, False], staggered={5, 6})
    guard_turn(context)
    assert panel.started and not panel.win_rate
    assert all(panel.guard[:5])
    assert sorted({c.args[0] for c in portrait_taps(context)}) == panel.xs[:5] and len(portrait_taps(context)) == 6
    assert chains == [[GEAR] + [(x, 665) for x in panel.xs[:5]]]
    assert actions.RUN["guard"] == 2
    assert any(line.endswith("guard: slots [6, 7] staggered, the rest on guard") for line in actions.LOG)


def test_a_staggered_slot_between_two_others_is_left_out_of_the_chain(context, chains):
    # #427: the finger crosses a staggered slot in the middle without a stop there; the slots after it are linked.
    panel = Panel(context, guard=[False] * 7, staggered={2})
    guard_turn(context)
    assert panel.started and not panel.win_rate
    assert chains == [[GEAR] + [(x, 665) for i, x in enumerate(panel.xs) if i != 2]]
    assert len(portrait_taps(context)) == 6 and actions.RUN["guard"] == 2


def test_a_turn_with_every_slot_staggered_presses_start_and_counts(context, chains):
    # #427, #69: nothing can be picked and the plaque shows from the turn's start: START at once, no Win Rate. The
    # turn counts as a guard turn, as one with some slots staggered does.
    panel = Panel(context, guard=[False] * 7, staggered=set(range(7)))
    panel.complete_at = actions.time.monotonic() - 1
    guard_turn(context)
    assert panel.started and not win_rate_taps(context)
    assert not portrait_taps(context) and chains == []
    assert actions.RUN["guard"] == 2


def test_a_win_rate_turn_presses_start_at_once_and_counts_no_guard_turn(context):
    panel = Panel(context, guard=[False] * 7)
    guard_turn(context, guard_left=0)
    assert panel.started and panel.win_rate
    assert len(portrait_taps(context)) == 0 and actions.RUN["guard"] == 0


def test_a_guard_turn_on_a_hollow_gear_plays_win_rate_and_keeps_its_guard_turn(context):
    # #127 (live 2026-10-18): in a focused encounter the left gear is a hollow ring and no chain starts from it;
    # each skill has to be dragged onto an enemy's skill slot, which moves with the camera.
    panel = Panel(context, guard=[False] * 7)
    data = (Path(__file__).resolve().parent / "gears" / "hollow_boss.png").read_bytes()  # tests/test_battle.py gear()
    rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(80, 1 + 80 * 3)
    ring = rows[:, 1:].reshape(80, 80, 3)[:, :, ::-1]

    def render():
        image = panel.render()
        image[536:616, 236:316] = ring  # round the left gear of 7 slots, (276, 576)
        return image
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = render
    actions.RUN["guard"] = 3
    battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert not portrait_taps(context)
    assert [c.args for c in context.tasker.controller.post_touch_down.call_args_list] == [battle_actions.HOLD_SPOT]  # no drag
    assert win_rate_taps(context)
    assert actions.RUN["guard"] == 3


def test_a_formation_left_mid_pick_taps_no_card(context, guarded):
    with pytest.raises(actions.PageGone):
        battle_actions.Formation.pick(context, ["Yi Sang"])
    assert taps(context) == []


def test_a_battle_gone_before_win_rate_is_handed_back(context, guarded):
    assert battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert taps(context) == []
    assert actions.STUCK["flag"] is None


WIPE_TEXT = tuple(battle_actions.DEFEAT_TEXT)


RETRY_STAGE = battle_actions.DEFEAT_OPTIONS["retry"]


def wipe(context, monkeypatch, card, confirm):
    """The DEFEAT dialog's Wipe with retries left: the answers of the Retry Stage card and of Confirm."""
    actions.RUN.update(settings={"run": {"wipe_retries": 2, "after_retries": "stop"}}, wipes=0)
    game = TimedGame(monkeypatch, context, {WIPE_TEXT: "All participating Sinners have been killed."},
                     {RETRY_STAGE: card, battle_actions.DEFEAT_CONFIRM: confirm})
    assert battle_actions.Wipe().run(context, None)
    return game


def test_wipe_confirms_once_the_picked_card_settles_and_hands_back_once_the_dialog_goes(context, clock, monkeypatch):
    # #258: the card slept 1.2 s, Confirm 2.5 s. The card now waits for the dialog to move and stop; Confirm for the
    # dialog's text to go.
    game = wipe(context, monkeypatch, [(0.2, {}, 60)], [(0.6, {WIPE_TEXT: ""}, 0)])
    assert game.taps == [RETRY_STAGE, battle_actions.DEFEAT_CONFIRM]
    assert actions.RUN["wipes"] == 1
    assert sum(clock) < 1.6  # was 3.7 s


def test_wipe_picks_the_card_again_when_confirm_does_not_take(context, clock, monkeypatch):
    # The card's tap lost: the dialog never moves, Confirm on no card does nothing, and after its old 2.5 s both go again.
    game = wipe(context, monkeypatch, [None, (0.2, {}, 60)], [None, (0.6, {WIPE_TEXT: ""}, 0)])
    assert game.taps == [RETRY_STAGE, battle_actions.DEFEAT_CONFIRM, RETRY_STAGE, battle_actions.DEFEAT_CONFIRM]
    assert actions.RUN["wipes"] == 1 and actions.STUCK["flag"] is None


def test_a_battle_handed_back_again_and_again_is_no_unchanged_turn(context, guarded):
    # Each hand-back is no submit: the turn count is for turns that START did not move on.
    for _ in range(5):
        assert battle_actions.PlayTurn().run(context, SimpleNamespace(box=[984, 531, 40, 20]))
    assert actions.STUCK["flag"] is None


def test_a_formation_gone_after_the_first_card_taps_no_more(context, guarded, monkeypatch):
    ctl = context.tasker.controller
    patch_all(monkeypatch, "participants", lambda context, image: (max(0, ctl.post_click.call_count - 1), 5))
    page_until(context, "Formation", 2)  # Clear Selection, then Yi Sang
    with pytest.raises(actions.PageGone):
        battle_actions.Formation.pick(context, ["Yi Sang", "Hong Lu"])
    assert taps(context) == [battle_actions.CLEAR_SELECTION, battle_actions.card_xy(battle.SINNERS.index("Yi Sang"), battle_actions.CARD_TAP_Y)]


def test_a_battle_gone_after_the_portrait_taps_swaps_nothing_back(context, guarded):
    panel = Panel(context, guard=[True, False, True, False, False, False, True])  # 3 slots go off guard and want a tap back
    page_until(context, "BattleTurn", 7)  # gone right after the first round of portrait taps
    with pytest.raises(actions.PageGone):
        battle_actions.PlayTurn.guard(context, 984, DISC)
    assert len(portrait_taps(context)) == 7 and DISC not in taps(context)
    assert context.tasker.controller.post_touch_down.call_count == 0 and not panel.started
