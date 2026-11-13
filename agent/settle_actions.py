"""The run's settlement: the result page, the weekly bonuses, and the claim or the give-up."""

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import recovery
import settlement
from actions import (DIALOG_CANCEL, DIALOG_CONFIRM, DIALOG_TEXT, ROOT, RUN, STUCK, TASK, current_run, hands_back, log,
                     number, ocr, page_guard, run_line, screen, still, stop, stuck, tap_shown, tap_then, text, until)
from ocrtext import has
from team_queue import requeue


# Settlement (spec 03 section 14): the Exploration Reward window.
RESULT = [300, 400, 100, 85]  # "Floor 5 [NORMAL] 6/6" under the floor icon
WEEKLY_LEFT = [440, 230, 65, 50]  # "n/3"
TOGGLE_X, TOGGLE_ROI = (558, 660, 763), (-45, 237, 90, 30)  # the 3 weekly-bonus toggles: x centre, roi offset
GIVE_UP, CLAIM = (393, 544), (887, 544)
REWARD_TITLE_ROI = [500, 100, 280, 45]
FIRST_FLOOR = [96, 238, 64, 36]  # Dungeon Progress's floor 1 tile, left of the dialog: "[HARD] Floor1" (2026-10-29)


def reward_up(context, image):
    """Whether the Exploration Reward window's title reads; it does under its dialogs too."""
    return has(text(context, image, REWARD_TITLE_ROI), "Exploration Reward")


def claim_asks(context, image):
    """The window's dialog that shows (settlement.claim_dialog), or None."""
    return settlement.claim_dialog(text(context, image, DIALOG_TEXT))


def toggles(context, image):
    """Each weekly-bonus toggle as True (ON), False (OFF) or None (unread)."""
    out = []
    for x in TOGGLE_X:
        dx, y, w, h = TOGGLE_ROI
        t = text(context, image, [x + dx, y, w, h], only_rec=True)
        out.append(False if has(t, "OFF") else True if has(t, "ON") else None)
    return out


@AgentServer.custom_action("Settle")
class Settle(CustomAction):
    """Claim check, weekly-bonus toggles, then Claim or GiveUpRewards; then the team queue and runs.jsonl (spec 03 section 14).

    Claim is pressed only after the toggles read back exactly as wanted; anything unexpected stops.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        if claim_asks(context, image):
            # left over from an earlier try: back out and decide again
            tap_then(context, *DIALOG_CANCEL, lambda im: not claim_asks(context, im), timeout=1.5)
            return True
        lines = sorted(ocr(context, image, RESULT), key=lambda r: r[1][1])  # results come out of order
        result = settlement.read_result(" ".join(t for t, _ in lines))
        if not result:
            return True  # fading in: let MirrorHub look again
        floor, hard = result.floor, result.hard
        log(f"exploration reward: Floor {floor} [{(result.difficulty or '?').upper()}] {result.cleared}/{result.total}")
        if not settlement.claim_ok(result):
            return self.give_up(context, run, result)

        s, team = run["settings"]["run"], run["team"]
        left = number(text(context, image, WEEKLY_LEFT).split("/")[0])
        # The difficulty each floor was played on, as the theme pack page showed it: a run with no plan in memory (an
        # expired session's dialog came first, #382) counts the same. Floors not seen (a resumed run): the window's floor 1 tile.
        floors_hard = RUN.get("floors_hard", {})

        def first_tile():
            tile = text(context, image, FIRST_FLOOR)
            log(f"floors before {min(floors_hard, default=floor + 1)} were not seen: the window's floor 1 tile reads {tile!r}")
            return tile
        want = settlement.claim_bonuses(result, s["target_floor"], s["weekly_bonus_use"], s["weekly_bonus_amount"], left or 0, floors_hard, first_tile)
        for _ in range(6):
            states = toggles(context, page_guard(context, "ExplorationReward"))
            on = [i for i, v in enumerate(states) if v]
            if None in states and len(on) <= want:
                # an unread toggle may be ON: never claim on a guess
                until(context, lambda im: None not in toggles(context, im), timeout=1)
                continue
            if len(on) == want:
                break
            i = on[-1] if len(on) > want else states.index(False)
            tap_then(context, TOGGLE_X[i], 252, lambda im: toggles(context, im)[i] is (not states[i]), timeout=1.5)
        else:
            return stop(context, f"weekly bonus toggles read {states}, want {want} ON: not claiming")
        log(f"weekly bonuses left {left}, use {s['weekly_bonus_use']}/{s['weekly_bonus_amount']}: toggles {states} verified, {want} ON")

        # Live: Claim asks to confirm with bonuses left and none ON (2026-10-15), and with any ON (2026-10-16).
        # Confirm only the dialog of what the toggles were set and read back to; a bonus is spent only then.
        asked = "bonus" if want else "no_bonus"

        def answered(im):
            return not reward_up(context, im) or claim_asks(context, im) == asked
        tap_then(context, *CLAIM, answered, timeout=2)
        for _ in range(5):
            image = screen(context)
            if not reward_up(context, image):
                break
            if claim_asks(context, image) == asked:
                # it moves for about 0.5 s after its first frame (2026-10-29, 2026-11-08 recordings); tapped once still
                still(context, timeout=1.5)
                tap_then(context, *DIALOG_CONFIRM, lambda im: not reward_up(context, im), timeout=2)
                continue
            until(context, answered, timeout=1)
        else:
            # Anything else, too few Enkephalin Modules most likely: nothing more is tapped, so nothing is bought.
            return stop(context, f"Claim did not close the window: {text(context, image, DIALOG_TEXT)!r}",
                        run_line(run, "stop", hard, settlement.floors_passed(result), want))
        log(f"claimed with {want} weekly bonus(es)")
        self.record(run, result, want, "clear")
        log(requeue(ROOT, team["id"]) if run.get("planned") else "this run's team is not known: the team queue stays")
        RUN.clear()
        return True

    def give_up(self, context, run, result):
        """GiveUpRewards, then `End expedition without claiming rewards?` Confirm; no module is spent.

        A run that earned nothing (`Floor 1 [NORMAL] 0/6`) gets no dialog: the window closes on GiveUpRewards, a run
        given up all the same (live 2026-11-08, #586). The run is recorded once the window goes: one that stays would
        bring Settle back to give it up again and write a second line for it (#566). The dialog is confirmed again while
        it stays, as Claim's is.
        """
        def closed(im):
            return not reward_up(context, im)
        for _ in range(3):
            page_guard(context, "ExplorationReward")  # also under its give-up dialog (maatools: GiveUpDialog.png)
            image = tap_shown(context, *GIVE_UP, lambda im: claim_asks(context, im) == "giveup" or closed(im), timeout=1.5)
            if image is not None:
                break
        else:
            return stuck("GiveUpRewards brought up no `End expedition without claiming rewards?` and left the window up")
        for _ in range(5):
            if claim_asks(context, image) == "giveup":
                page_guard(context, "ExplorationReward", image=image)
                image = tap_then(context, *DIALOG_CONFIRM, closed, timeout=2)
            else:
                image = until(context, closed, timeout=1)
            if image is not None:
                break
            image = still(context, timeout=1.5)  # a dialog fading out is not tapped again
            if image is None:
                image = screen(context)
        else:
            return stuck("the Exploration Reward window stayed after its give-up Confirm")
        log("floor 5 not passed: gave up the rewards")
        self.record(run, result, 0, "giveup")
        RUN.clear()
        return True

    @staticmethod
    def record(run, result, bonuses, outcome):
        settlement.append_run(ROOT, run_line(run, outcome, result.hard, settlement.floors_passed(result), bonuses))
        counts = settlement.counts_as_run(outcome)
        TASK["runs"] += counts
        TASK["forfeits"] = [] if counts else [*TASK.get("forfeits", []), run.get("forfeited")]
        TASK["settled"] = True
        STUCK["ladder"] = recovery.Ladder()
