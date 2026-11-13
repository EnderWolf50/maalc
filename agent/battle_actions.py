"""A battle's custom actions: the formation, the turns, and the battle's end in a victory or a wipe."""

import time

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import battle
import recovery
import run_start
from actions import (RUN, TO_BATTLE, current_run, drag, end_battle, hands_back, log, page_guard, saturation, screen,
                     seen, still, stop, stuck, tap, tap_settled, tap_shown, tap_then, text, until)
from ocrtext import fraction, has


# Formation page (spec 03 section 3). Cards are in battle.SINNERS order, two rows of six.
CARD_X = [295 + round(132.2 * i) for i in range(6)]  # card centres
CARD_ART_Y = ((180, 300), (380, 500))
CARD_NUMBER_Y = (211, 410)  # centre of the order mark on each row
CARD_TAP_Y = (290, 488)  # the card's name plate
PARTICIPANTS = [1125, 500, 100, 45]  # "10/11": selected / alive
DETAILS_BUTTON = [860, 110, 125, 30]  # reads "Details" in the card view
CLEAR_SELECTION = (1145, 479)
RESET_DIALOG = [450, 330, 380, 35]  # Clear Selection asks "Reset Deployment Order?"
RESET_CONFIRM = (767, 497)
PICK_RETAP = 1.0  # s; a card tap that has not raised the count by then is tapped again (the old fixed wait guessed a tap within ~1 s of the last is lost, #253)
PICK_SETTLE = 1.5  # s; after a repeated tap the count is watched this long for a fall back: the first tap may have taken late (#253: the count showed 0.3-1.2 s after a tap, recordings, unverified)


def card_xy(i, ys):
    return CARD_X[i % 6], ys[i // 6]


def participants(context, image):
    """(selected, alive) from Total Participants, or None when it is not readable."""
    return fraction(text(context, image, PARTICIPANTS))


def dead_sinners(image):
    """Sinners whose card is grey: mean S ~2 against 65+ for any living card, picked or not."""
    dead = set()
    for i, sinner in enumerate(battle.SINNERS):
        x, (y0, y1) = CARD_X[i % 6], CARD_ART_Y[i // 6]
        if saturation(image[y0:y1, x - 50:x + 50]).mean() < 30:
            dead.add(sinner)
    return dead


def order_marks(context, image):
    """{sinner: order mark or None}.

    The marks (orange SELECTED, cyan BACKUP) are cut out by colour first: OCR on the card art
    misread 4, 6 and 9 in live captures; on the mask, one line per card, it read all 22 right.
    """
    mask = (image.max(axis=2) > 200) & (saturation(image) > 120)
    plain = np.where(mask[..., None], 0, 255).astype(np.uint8).repeat(3, axis=2)
    marks = {}
    for i, sinner in enumerate(battle.SINNERS):
        x, y = card_xy(i, CARD_NUMBER_Y)
        t = text(context, plain, [x - 25, y - 23, 50, 46], only_rec=True).strip()
        marks[sinner] = int(t) if t.isdigit() else None
    return marks


FORMATION_BACK = (98, 43)  # the formation page's back arrow, top left


@AgentServer.custom_action("Formation")
class Formation(CustomAction):
    """Re-pick the deployment order, skipping the dead, then Chain To Battle! (spec 03 section 3).

    The game keeps the last battle's picks: they are read off the cards and redone only when they differ.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        end_battle()  # a new battle: its clock and turn count start over, also when the last VICTORY went unseen (#80)
        image = still(context)
        count = image is not None and participants(context, image)
        if not count:
            return True  # page fading in or out: let MirrorHub look again
        alive, need = count[1], run["team"]["min_alive"]
        RUN["alive"] = alive  # the shop's heal reads it (spec 03 section 13)
        if not has(text(context, image, DETAILS_BUTTON), "Details"):
            # its » folds the details view (skills, E.G.O), which hides the order marks
            tap_shown(context, 826, 125, lambda im: has(text(context, im, DETAILS_BUTTON), "Details"), timeout=1.5)
            image = screen(context)
        dead = dead_sinners(image)
        if len(dead) != 12 - alive:
            # The grey cards say who is dead, which the order needs; they decide (#616).
            log(f"formation: {12 - alive} dead by the count, grey cards {sorted(dead)}: the grey cards decide")
        order = battle.formation_order(run_start.resolve_plan(run["settings"], run["team"], "deployment_order"), dead)
        log(f"formation: {len(order)} of the deployment order alive, {alive} alive on screen, team needs {need}")
        if len(order) < need:  # need 0: no check; only the deployment order's sinners count (#616)
            # Like used-up wipe retries (#137): stop, or back out to the map, where RouteMap forfeits.
            reason = f"{len(order)} sinners of the deployment order alive, team {run['team']['name']!r} needs {need}"
            if run["settings"]["run"]["after_retries"] == "stop":
                return stop(context, reason)
            log(f"{reason}: forfeit the run")
            RUN["forfeit"] = reason
            # MirrorHub must not find the page again and back out twice.
            tap_then(context, *FORMATION_BACK, lambda im: seen(context, im, "Formation") is None, timeout=2)
            return True
        if not order:  # a short order (sinners left out) with all its sinners dead
            return stop(context, f"no sinner in team {run['team']['name']!r}'s deployment order is alive")
        if battle.formation_matches(order_marks(context, image), order):
            log(f"formation as planned, {alive} alive")
        elif not self.pick(context, order):
            return True  # pick() handed it to recovery
        for _ in range(3):
            page_guard(context, "Formation")
            tap(context, *TO_BATTLE, wait=0)
            if until(context, lambda im: not participants(context, im), timeout=3) is not None:
                return True
        return stuck("Chain To Battle! did nothing")

    @staticmethod
    def pick(context, order):
        """Clear Selection, then tap the order card by card, each tap checked by the count going up by one (#253).

        Every tap is followed at once by until()'s looks at the count. A card whose count was read but is not n after
        PICK_RETAP s is tapped again. A second tap on a card that took the first one picks it off, so after a repeated
        tap the count is watched PICK_SETTLE s for a fall back, which is one more tap (the repeats wait PICK_SETTLE s
        for the count too); once that fall back shows, the later cards wait PICK_SETTLE s for their first tap as well.
        A count that could not be read for the whole wait (a page still moving) is waited for once more before the
        card is tapped again. Two taps after which the count was not n end the pick as stuck, for recovery.
        """
        def count_is(n, seen=None):
            def done(image):
                count = participants(context, image)
                if count and seen is not None:
                    seen.append(count[0])
                return count is not None and count[0] == n
            return done

        def fell_from(n):
            return lambda image: (count := participants(context, image)) is not None and count[0] != n

        dialog = []

        def cleared(image):
            dialog[:] = [has(text(context, image, RESET_DIALOG), "Reset Deployment")]
            return dialog[0] or count_is(0)(image)

        start, retaps, first_wait = time.monotonic(), 0, PICK_RETAP
        for _ in range(3):
            page_guard(context, "Formation")
            image = tap_then(context, *CLEAR_SELECTION, cleared, timeout=1.5)
            if image is not None and dialog[0]:
                image = tap_then(context, *RESET_CONFIRM, count_is(0), timeout=3)
            if image is not None:  # the count 0 it waited for
                break
        else:
            stuck("Clear Selection did not clear the formation")
            return False
        for n, sinner in enumerate(order, 1):
            picked, misses = False, 0  # taps (3 at most) after which the count was not n, 2 of them end the pick
            for attempt in range(3):
                page_guard(context, "Formation")
                seen = []
                done = count_is(n, seen)
                wait = first_wait if attempt == 0 else PICK_SETTLE  # a repeat has nothing to gain by hurrying
                image = tap_then(context, *card_xy(battle.SINNERS.index(sinner), CARD_TAP_Y), done, timeout=wait)
                if image is None and not seen:
                    image = until(context, done, timeout=wait)
                if image is not None:
                    if attempt == 0 or until(context, fell_from(n), timeout=PICK_SETTLE) is None:
                        picked = True
                        break
                    first_wait = PICK_SETTLE  # a tap took late: the next cards' first taps wait as long
                retaps += 1
                misses += image is None
                if misses == 2:
                    break
            if not picked:
                stuck(f"tapping {sinner} did not pick them")
                return False
        log(f"formation re-picked: {', '.join(order)}")
        log(f"formation pick took {time.monotonic() - start:.1f} s, {retaps} taps repeated")
        return True


# Battle (spec 03 section 8). Offsets are from the BattleTurn (Win Rate label) template's top-left.
WIN_RATE = (20, 14)
START_DISC = (-66, 26)
TURN_NUMBER = [55, 57, 45, 30]
SLOT_PORTRAIT_Y = 665  # tapping a slot's portrait swaps its lower skill and its guard skill
LOWER_Y = 577  # a slot's lower skill, at rest (while a drag is down it sits at y 665: battle.guard_chain)
# Live 2026-10-18 (#119): portrait taps 52 ms apart lost 9 of 28, 72 ms apart 1 of 28, 83-350 ms apart none
# of 168; this wait plus ~50 ms for the tap puts them 150 ms apart.
GUARD_TAP_WAIT = 0.1


def lower_x(x):
    """x of a slot's lower skill: the skill rows lean in towards the middle (x ~604) by about 6%."""
    return round(x + (604 - x) * 0.06)


def guard_score(image, x):
    """(brown, texture) at a lower skill, for battle.guard_shown; guard icons are flat brown (~(150, 100, 50) RGB)."""
    p = image[LOWER_Y - 14:LOWER_Y + 14, x - 14:x + 14].astype(int)
    b, g, r = p[..., 0], p[..., 1], p[..., 2]
    v = p.sum(axis=2)
    texture = np.abs(np.diff(v, axis=0)).mean() + np.abs(np.diff(v, axis=1)).mean()
    return float(((r > 90) & (r - g > 20) & (g - b > 10)).mean()), float(texture)


def lower_skills(context, xs, before=None, timeout=1.5):
    """The first screenshot whose lower skills at xs read as they did 0.1 s before, after every one of them
    swapped from before (battle.guard_shown tells); without before, every one shows something. The last
    screenshot after timeout s. Live (#119): a swap shows 0.1-0.6 s after the tap and fades for ~0.4 s."""
    last = [None]

    def done(image):
        now = [guard_score(image, x) for x in xs]
        steady = last[0] is not None and all(abs(a[1] - b[1]) <= 2 for a, b in zip(now, last[0]))
        last[0] = now
        changed = None not in battle.guard_shown(before, now) if before else min(t for _, t in now) > 20
        return steady and changed
    image = until(context, done, timeout=timeout, every=0.1)
    return screen(context) if image is None else image


def win_rate_on(context, image, x, y):
    """Whether the Win Rate label at (x, y) shows pressed (on): its two templates match each other at only 0.70."""
    node = {"template": "Battle/BattleTurnPressed.png", "roi": [x - 10, y - 10, 60, 49]}
    detail = context.run_recognition("BattleTurn", image, {"BattleTurn": node})
    return bool(detail and detail.hit)


def start_shown(context, image, disc):
    """Whether the START plaque hangs over the disc: the game shows it only once every slot has a skill (#145).

    The disc lights as soon as any slot is linked, so it cannot tell a chain that ended short. Live 2026-10-18:
    the plaque template scored 0.58-1.0 with it (0.58-0.66 mid-swing) and 0.20-0.35 without it on 431 screens
    of every floor, the snow maps included; it swings in 0.53-0.7 s after the drag's lift, after START works.
    """
    x, y = disc
    return seen(context, image, "BattleStart", [x - 45, y - 75, 95, 45]) is not None


def turn_started(context, image):
    """The turn plays out: the pause button is up, or the Win Rate label is gone."""
    return seen(context, image, "BattlePause") is not None or seen(context, image, "BattleTurn") is None


# Live 2026-10-18 (#145): a turn starts 0.45-0.7 s after START. Right after a drag the panel tilts back for
# ~0.15 s and the Win Rate label does not match: the first look waits START_LEAST s.
START_WAIT = 1.5
START_LEAST = 0.3
# The plaque appears tilted on the disc's right once the chain is complete, rests there ~0.3 s and swings up to
# the top: upright (template >= 0.5) 0.33-0.47 s after the panel levels, settled from 0.40-0.53 s (30 fps
# recording, 3 drags; 0.48-0.71 s after the lift in 73 drags polled by screenshot). A minimised emulator held it
# mid-swing for over 2 s, so "no plaque" is only concluded after this much more polling.
PLAQUE_WAIT = 1.5


def press_start(context, disc):
    """Press START: whether the turn starts. Pressed once more when it did not although the plaque shows
    (looked for up to PLAQUE_WAIT s: it can still be swinging in)."""
    for _ in range(2):
        tap(context, *disc, wait=0)
        if until(context, lambda im: turn_started(context, im), timeout=START_WAIT, least=START_LEAST) is not None:
            return True
        if until(context, lambda im: start_shown(context, im, disc), timeout=PLAQUE_WAIT, every=0.1) is None:
            return False
    return False


# #150: a finger held on the screen while a turn plays speeds up its E.G.O animations (user, 2026-10-18; no
# difference seen on turns without one: 5.9 s held, 6.4 s not, over 16 turns). The top-left corner held then
# touched nothing (docs/perf/2026-10-18-guard-chain-145.md); a lift there is a tap on whatever screen follows.
HOLD_SPOT = (1, 1)
HOLD_EVERY = 0.3  # s between looks, MirrorHub's rate_limit
HOLD_LIMIT = 6  # s at most per hold (a turn without E.G.O plays ~6 s): then MirrorHub (its watchdog, recovery) looks; BattlePause holds a longer turn again
# Screens that can follow a turn, besides the next turn: the finger lifts before their node acts.
BATTLE_POPUPS = ("Connecting", "RetryPopup", "PopupButton")  # template-gated: looked for while a turn plays, no OCR (#157)
# EgoCard (#468): in the daily run of 2026-11-07 the card was up after `turn 1: started`, still on TURN 1; what opened it
# there is unverified (a long press on a portrait opens it). A hold that meets it lifts at once, not after HOLD_LIMIT.
BATTLE_LEFT = BATTLE_POPUPS + ("Victory", "WipeDialog", "Event", "ClaimPopup", "Loading", "EgoCard")


def hold_turn(context):
    """Hold a finger on HOLD_SPOT while the turn plays: until the next turn waits for input, a screen of
    BATTLE_LEFT shows, the task is stopping or HOLD_LIMIT s. Always lifted on return, also on an error:
    a finger left down keeps the panel tilted and MirrorHub blind (#145)."""
    end = time.monotonic() + HOLD_LIMIT
    try:
        context.tasker.controller.post_touch_down(*HOLD_SPOT).wait()
        while time.monotonic() < end and not context.tasker.stopping:
            time.sleep(HOLD_EVERY)
            image = screen(context)
            if seen(context, image, "BattlePause"):  # playing (the Win Rate label can still match in a turn's first frames)
                if any(seen(context, image, n) for n in BATTLE_POPUPS):
                    return  # a popup over the turn (the network)
                continue
            if seen(context, image, "BattleTurn") or any(seen(context, image, n) for n in BATTLE_LEFT):
                return
    finally:
        # Fetched again: in the agent, one kept from before the looks failed its touch up with an access
        # violation (live 2026-10-20, every hold), and the finger stayed down until the next tap.
        context.tasker.controller.post_touch_up().wait()


@AgentServer.custom_action("HoldTurn")
class HoldTurn(CustomAction):
    """BattlePause: a turn playing out (after a hold timed out, a recovery or an agent restart): hold_turn."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        hold_turn(context)
        return True


# The guard chain drag, slower on each try (#145, live 2026-10-18, 12 slots). The game links a slot only if it
# draws a frame while the finger is on it; during the drag it draws 9-30 frames a second, fewer under load
# or with its window covered or minimised. 10 px moves 10 ms apart and no rest (#119) missed 7 of 88 drags
# whose frames came within 90 ms (p90) and 27 of 43 slower; a 0.03 s rest on each slot 0 of 90 and 11 of 32;
# a 0.1 s rest 14 of 14 at 9-12 frames a second (16 cores busy). A miss costs ~2 s to see and clear.
GUARD_DRAGS = ({"settle": 0.05, "dwell": 0.03, "hold": 0.05, "pause": 0.01},
               {"settle": 0.05, "dwell": 0.1, "hold": 0.1, "pause": 0.02},
               {"settle": 0.05, "dwell": 0.2, "hold": 0.1, "pause": 0.02})


@AgentServer.custom_action("PlayTurn")
class PlayTurn(CustomAction):
    """Guard or Win Rate (one tap), press the START disc, check the turn plays (spec 03 section 8, 06)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        x, y = argv.box[0], argv.box[1]
        dx, dy = x + START_DISC[0], y + START_DISC[1]
        if time.time() - RUN.setdefault("battle_start", time.time()) > recovery.BATTLE_LIMIT:
            return stuck(f"battle over {recovery.BATTLE_LIMIT // 60} min", level=2)  # skips L1 (spec 06)
        # Live 2026-10-17: the Win Rate label also matches in the first frames of a turn playing out (the
        # screen moving), and a tap in the turn's opening can do nothing: act on a still HUD only. Live
        # 2026-10-21 (#229): a swarm of enemies kept the battlefield moving for good; turn 3 waited 18 min, twice.
        image = still(context, timeout=1, roi=battle.hud_band(argv.box), share=battle.HUD_MOVED)
        if image is None:
            return True  # moving: MirrorHub looks again
        turn = text(context, image, TURN_NUMBER, only_rec=True).strip() or None
        tries = battle.same_turn(RUN.get("turn"), turn)
        if tries[1] > 3:
            return stuck(f"turn {turn} unchanged after 3 submits")
        guarded = False
        if RUN.get("guard", 0) > 0 and tries[1] == 1:  # a turn submitted again plays as before #52
            if battle.gear_hollow(image, battle.slot_xs(x)[0] - 86, 576):
                # #127: a focused encounter. Its skills are dragged one by one onto enemy skill slots that move
                # with the camera; no chain starts from the ring. The guard turns wait for a battle that has one.
                log(f"turn {turn}: hollow left gear (focused encounter): Win Rate, guard turns kept")
            else:
                guarded = self.guard(context, x, (dx, dy))
                if not guarded:
                    log(f"turn {turn}: guard did not take, Win Rate instead")
        started = True
        if guarded:
            RUN["guard"] = battle.guard_left(RUN["guard"], guarded)
            log(f"turn {turn}: started on guard, {RUN['guard']} guard turns left")
        elif self.win_rate(context, x, y, (dx, dy), turn):
            log(f"turn {turn}: started")
        else:
            started = False
            log(f"turn {turn}: START did not start the turn")
        RUN["turn"] = tries  # counted once submitted: a hand-back (#118) is no submit
        if started:
            hold_turn(context)
        return True

    @staticmethod
    def win_rate(context, x, y, disc, turn):
        """Win Rate (one tap), then START at once: whether the turn started. If it did not, the picks are
        cleared at the left gear and Win Rate and START are tried once more, here rather than on MirrorHub's
        next looks (#145: those took 3 submits, a stuck and recovery L1, ~23 s)."""
        for attempt in range(2):
            image = screen(context)
            for _ in range(2):
                if battle.disc_lit(image, *disc) or start_shown(context, image, disc):
                    break
                # Win Rate toggles: a second tap clears the skills the first picked, so it is tapped again only
                # when its label does not show pressed: live, a tap in the turn's opening did nothing (#58).
                image = page_guard(context, "BattleTurn", image=image)
                tap(context, x + WIN_RATE[0], y + WIN_RATE[1], wait=0)
                lit = until(context, lambda im: battle.disc_lit(im, *disc), timeout=1.5)
                image = screen(context) if lit is None else lit
                if lit is not None or win_rate_on(context, image, x, y):
                    break
                log(f"turn {turn}: Win Rate did not take")
            if press_start(context, disc):
                return True
            xs = battle.slot_xs(x)
            if attempt == 0 and xs:
                # A chain left short (the disc lights, START does nothing) or picks the game dropped.
                log(f"turn {turn}: START did not start the turn: clearing the picks for Win Rate again")
                page_guard(context, "BattleTurn")
                tap(context, *battle.guard_chain(xs)[0], wait=0)
                until(context, lambda im: not battle.disc_lit(im, *disc), timeout=1)
        return False

    @staticmethod
    def guard(context, x, disc):
        """Pick every slot's guard skill and press START: whether the turn started on guard.

        A portrait tap swaps the slot's lower skill and its guard skill, and the game can keep the swap
        from turn to turn, so every portrait is tapped once and the lower skills compared before and
        after (the check that every slot shows its guard skill); the slots that went off guard are
        tapped back. Then one drag from the left gear through every slot's lower skill picks them
        (battle.guard_chain); no Win Rate. START is pressed right after it. The picked icons cannot be told
        apart reliably (banners, chain and glow cover them) and the disc lights with one slot linked, so a turn
        that does not start means the chain ended short (#145): a tap on the left gear clears it (a chain
        cannot be continued from its last slot) and a slower drag links it again (GUARD_DRAGS). A drag that
        links nothing (a hollow gear, #127) is not tried again.

        A staggered slot (battle.staggered, #427) acts no skill this turn and a tap on its portrait swaps nothing: it is
        neither tapped nor compared, and the chain makes no stop on it. The other slots guard, and the turn counts as a
        guard turn. With every slot staggered there is nothing to pick: START is pressed as it is (#69), and the turn
        counts too.
        """
        xs = battle.slot_xs(x)
        image = lower_skills(context, [lower_x(sx) for sx in xs])  # live: a first turn slides the portraits in late
        staggered = battle.staggered(image, xs)
        if all(staggered):  # #69: the plaque shows with no skill picked
            log("guard: every slot staggered, nothing to pick")
            page_guard(context, "BattleTurn", image=image)
            return press_start(context, disc)
        if any(staggered):
            log(f"guard: slots {[n for n, s in enumerate(staggered, 1) if s]} staggered, the rest on guard")
        numbers = [n for n, s in enumerate(staggered, 1) if not s]  # the slots that act: their numbers and x
        acting = [sx for sx, s in zip(xs, staggered) if not s]
        lows = [lower_x(sx) for sx in acting]
        before = [guard_score(image, lx) for lx in lows]
        page_guard(context, "BattleTurn", image=image)
        for sx in acting:  # ponytail: one check per batch of portrait taps (0.1 s apart), not a screenshot per tap
            tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        image = lower_skills(context, lows, before)
        after = [guard_score(image, lx) for lx in lows]
        shown = battle.guard_shown(before, after)
        unsure = [i for i, s in enumerate(shown) if s is None]
        if unsure:  # live: the glow on a unit's slot flickers; swap those back and compare once more
            page_guard(context, "BattleTurn", image=image)
            for i in unsure:
                tap(context, acting[i], SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
            image = lower_skills(context, [lows[i] for i in unsure], [after[i] for i in unsure])
            again = battle.guard_shown([after[i] for i in unsure], [guard_score(image, lows[i]) for i in unsure])
            for i, s in zip(unsure, again):
                shown[i] = s
        if None in shown:
            log(f"guard: cannot tell the guard skill of slots {[n for n, s in zip(numbers, shown) if s is None]}")
            return False
        page_guard(context, "BattleTurn", image=image)
        for sx, on in zip(acting, shown):
            if not on:
                tap(context, sx, SLOT_PORTRAIT_Y, wait=GUARD_TAP_WAIT)
        chain = battle.guard_chain(xs, staggered)
        for n, params in enumerate(GUARD_DRAGS, 1):
            page_guard(context, "BattleTurn")
            drag(context, chain, **params)
            # Live (#145): the panel tilts back for ~0.15 s after the lift; a START pressed in it was lost 4 times
            # in 18. The Win Rate label matching again says it is back.
            until(context, lambda im: seen(context, im, "BattleTurn") is not None, timeout=1, every=0.05)
            if press_start(context, disc):
                return True
            image = screen(context)
            if not battle.disc_lit(image, *disc):
                log("guard: the chain drag linked nothing")
                return False
            log(f"guard: START did not start the turn after chain drag {n} ({params['dwell']} s a slot): clearing it")
            page_guard(context, "BattleTurn", image=image)
            tap(context, *chain[0], wait=0)
            until(context, lambda im: not battle.disc_lit(im, *disc), timeout=1)
        return False


@AgentServer.custom_action("Victory")
class Victory(CustomAction):
    """VICTORY ends the battle; it needs no tap. The encounter's retry count starts over."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if "turn" in RUN:
            log("victory")
        end_battle()
        RUN["wipes"] = 0
        return True


DEFEAT_OPTIONS = {"retry": (790, 354), "forfeit": (790, 446)}  # Retry Stage, Accept results
DEFEAT_CONFIRM = (645, 527)
DEFEAT_TEXT = [330, 360, 270, 50]


@AgentServer.custom_action("Wipe")
class Wipe(CustomAction):
    """DEFEAT dialog: Retry Stage up to wipe_retries times, then stop or forfeit (spec 03 section 9).

    Accept results only on the way to forfeiting: it keeps the deaths.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        settings = current_run(context)["settings"]["run"]
        used = RUN.get("wipes", 0)
        choice = battle.after_wipe(used, settings["wipe_retries"], settings["after_retries"])
        log(f"wipe: {used} of {settings['wipe_retries']} retries used: {choice}")
        if choice == "stop":
            return stop(context, "retries used up")
        for _ in range(3):
            tap_settled(context, *DEFEAT_OPTIONS[choice], timeout=1.2)  # the options are cards: pick one, then Confirm
            if tap_then(context, *DEFEAT_CONFIRM, lambda im: not has(text(context, im, DEFEAT_TEXT), "participating"),
                        timeout=2.5) is not None:
                break
        else:
            return stuck(f"the DEFEAT dialog did not take {choice}")
        end_battle()
        if choice == "retry":
            RUN["wipes"] = used + 1
        else:
            RUN["forfeit"] = "wipe retries used up"  # Accept results lands on the map; RouteMap forfeits from there
        return True
