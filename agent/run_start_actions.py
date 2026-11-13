"""A run's start: the plan, Parallel Mode, the team, starlight and its graces, the starting gift and its search, and
the theme pack."""

import functools
import re
import time

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import gift_search
import pack_cover
import recovery
import run_start
import settlement
from actions import (GET_CONFIRM, GET_NAME, GET_TITLE, ROOT, RUN, STUCK, TASK, TO_BATTLE, back, current_run, data,
                     finish, grid_moved, hands_back, log, number, ocr, page_guard, restart_floor_clock, run_team,
                     screen, scroll, seen, shows, still, stop, stuck, swipe, tap, tap_then, text, until)
from ocrtext import compact, floor_number, has
from settings import GIFT_KEYWORDS, SettingsError, gift_tables, load_settings
from team_queue import pick_team


WEEKLY_SLOTS = (922, 960, 998)  # x of the 3 Weekly Bonuses slots on the entry page, y 285-297
TEAM_LIST = [75, 292, 115, 245]
ENTER_DIALOG = [400, 325, 480, 45]  # "Will you enter ...?"
TEAM_TITLE = [220, 112, 210, 26]  # "TEAMS #n" over the card list

LEVEL_WARNING = [400, 230, 480, 90]  # "... lower than the recommended level ..."
STARLIGHT_HEADER = [890, 30, 115, 28]  # "Available"
STARLIGHT_DIALOG = [480, 210, 320, 35]  # "Continue with selected effects?"
STARTING_GIFT_HEADER = [780, 145, 230, 35]  # "Selected E.G.O Gift"
STARLIGHT_AVAILABLE = [1010, 30, 80, 28]
STARLIGHT_NOTE = [660, 395, 320, 90]  # the line under Convert Starlight to Cost: "unspent" when off, "remaining" when on
STARLIGHT_OWNED = [830, 30, 90, 28]  # "4035", "4035-60" while owned starlight pays
GRACE_ORIGIN_X, GRACE_ORIGIN_Y = (138, 152), (152, 390)  # top-left of card 1; step 198 px per column
PACK_TITLES = [120, 400, 1040, 100]  # up to 5 cards (live: 5 with two Theme Pack Selection +1 graces)
# #246, recordings: dealt cards slide in and swing until ~2.8 s after the deal; their titles are read once they stop.
PACK_CARDS = [120, 170, 1040, 360]
CARDS_SETTLE = 4.0  # s; a page still swinging by then is read anyway
# The theme pack page's Refresh button (frame, icon and word): lit while a free refresh is left, greyed once none is,
# with or without its `n/m` (#482: one free refresh shows none). How many of its px are brighter than REFRESH_BRIGHT
# (max channel), on the pack pages of 46 live runs' recordings (2026-10-22 to 11-07, 288 frames): lit 765-2108 (253
# frames), greyed 0 (35 frames, the brightest px 54-56). The ThemePack captures of tests/screens: lit 1176-1321, greyed 0.
REFRESH_BUTTON = (1001, 25, 163, 45)
REFRESH_BRIGHT, REFRESH_LIT_MIN = 120, 100


@AgentServer.custom_action("PlanRun")
class PlanRun(CustomAction):
    """Entry page, no run under way: check settings, pick difficulty and team, press Enter (spec 03 sections 1, 2).

    Nothing left to do (the run count reached, the weekly bonuses out, no enabled team, none for the difficulty) ends
    the task a success at the main window (GoHome, then done; live-2 G4); bad settings fail it (returning False), and
    so do settings that forfeit run after run (the stop procedure, settlement.forfeits_stop).
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            settings = load_settings(ROOT)
        except SettingsError as e:
            log(f"stop: {e}")
            return False
        if not any(t["enabled"] for t in settings["teams"]):
            return finish(context, "no enabled team")
        hsv_v = screen(context)[285:297].max(axis=2)  # V of HSV
        # Live: a filled slot reads V ~240, an empty one ~5 (2026-10-15).
        weekly = sum(hsv_v[:, x:x + 30].mean() > 40 for x in WEEKLY_SLOTS)
        run = settings["run"]
        if settlement.runs_done(TASK["runs"], run["runs"]):
            return finish(context, f"{TASK['runs']} of {run['runs']} runs done")
        if why := settlement.forfeits_stop(TASK.get("forfeits", [])):
            return stop(context, why)
        if run["stop_when_weekly_bonus_out"] and weekly == 0:
            return finish(context, "weekly bonuses used up")
        difficulty = run_start.run_difficulty(run["difficulty"], weekly, run["target_floor"])
        team = pick_team(settings["teams"], difficulty)
        if team is None:
            return finish(context, f"no enabled team may run {difficulty}")
        if run_start.team_difficulty(run["difficulty"], difficulty, team["hard_from_floor"]) != difficulty:
            log(f"team {team['name']!r} never switches to hard and the difficulty is {run['difficulty']}: a normal run")
            difficulty = "normal"
        # The entry page has no Modules panel (tests/screens/EntryNewRun.png): the Drive page's read (OpenDrive) is this trip's.
        step = settlement.new_run_gate(TASK.get("modules", settlement.NOT_SEEN), TASK.get("gate_backs", 0))
        if step == "back":  # not through Drive since the last run: back out, the hub's navigation reads it on the way in
            TASK["gate_backs"] = TASK.get("gate_backs", 0) + 1
            log("new run: the Modules were not read on the way here, back to the Drive page to read them")
            back(context)
            return True
        modules = TASK.pop("modules", None)
        TASK.pop("gate_backs", None)
        if step == "done":
            return finish(context, f"Modules {modules} < {settlement.CLAIM_COST}, one Claim could not be paid: no new run")
        if modules is None:
            log("new run: the Modules number did not read, starting anyway")
        else:
            log(f"new run: Modules {modules} >= {settlement.CLAIM_COST}")
        RUN.clear()
        # planned: the run's team is known (picked here, or after a restart the queue's, current_run), so the claim may
        # move it to the end of the queue and runs.jsonl names it.
        limit = recovery.floor_limit(recovery.read_runs(ROOT), team["id"], run["target_floor"])
        # guard: the run's guard turns left (spec 03 section 8), counted across its battles.
        # floor_limit: each floor's time; the first clock runs from here, PickThemePack restarts it (spec 06).
        RUN.update(settings=settings, team=run_team(settings, team), difficulty=difficulty, planned=True, start=settlement.now(), deadline=time.time() + limit,
                   floor_limit=limit, guard=team["guard_turns"], packs=[])
        STUCK["ladder"] = recovery.Ladder()
        log(f"new run: {difficulty}, team {team['name']!r} (TEAMS #{team['game_team']}), weekly bonuses left {weekly}, time limit {limit / 60:.0f} min a floor")
        tap_then(context, 1108, 494, shows(context, ENTER_DIALOG, "Will you enter"), timeout=3)
        return True


INFINITY_TITLE = [890, 330, 330, 28]  # entry page: "Parallel Superposition Mode : ON" / "OFF" (the pipeline's roi)
INFINITY_BUTTON = (1053, 377)  # INFINITY MIRROR under it


@AgentServer.custom_action("ParallelModeOff")
class ParallelModeOff(CustomAction):
    """Entry page with Parallel Superposition Mode ON: tap INFINITY MIRROR until it reads OFF (#94, spec 02).

    v1 never plays past floor 5 (#434 opens it for a target above 5); the prompt after floor 5 (ParallelModePrompt)
    is cancelled as a second guard.
    Still ON after two taps: stop, nothing else is tried.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        for _ in range(2):
            if tap_then(context, *INFINITY_BUTTON, shows(context, INFINITY_TITLE, r":\s*[O0]FF"), timeout=3) is not None:
                log("Parallel Superposition Mode switched OFF")
                return True
        return stop(context, "Parallel Superposition Mode stays ON after tapping INFINITY MIRROR")


def team_rows(context, image):
    """The picker list's fully shown rows: {slot number: y of its centre}."""
    visible = {}
    for t, (x, y, w, h) in ocr(context, image, TEAM_LIST):
        m = re.search(r"#\s*(\d+)", t)
        if m and 300 <= y + h // 2 <= 515:  # rows cut off at the list edge do not count
            visible[int(m[1])] = y + h // 2
    return visible


def team_list_top(context, home="TeamSelect"):
    """Drag the picker list to its top, a stroke at a time until the rows on show stay (#226): it opens where it was left.

    The rows' numbers, not their y: OCR boxes move by a pixel or two at rest (live 2026-10-27: 10 drags at the top)."""
    seen = None
    for k in range(15):
        rows = set(team_rows(context, page_guard(context, home)))
        if rows and rows == seen:  # no rows read is not a list at rest
            log(f"team list at its top after {k - 1} drags that moved it")
            return
        seen = rows
        scroll(context, 130, 340, 0, 140)
    log("team list still moving after 15 drags: looking for the team from here")


def pick_team_slot(context, n, home="TeamSelect"):
    """Have the title read the in-game TEAMS #N: that screenshot, or None when 15 strokes found no such row.

    Already on the title: nothing to do. Else tap its row, scrolling from where the list is towards it (team_list_move);
    the list goes to its top first only when no row reads (#226). Only the number counts: a team's name is the user's.
    home: the node of the page (the mirror's TeamSelect, LuxTeamSelect) for page_guard."""
    titled = shows(context, TEAM_TITLE, rf"#\s*{n}\b")
    image = page_guard(context, home)
    if titled(image):
        return image
    if not team_rows(context, image):
        team_list_top(context, home)
        image = None
    for _ in range(15):
        visible = team_rows(context, page_guard(context, home) if image is None else image)
        image = None
        move = run_start.team_list_move(visible, n)
        if move == "down":
            scroll(context, 130, 480, 0, -140)
        elif move == "up":
            scroll(context, 130, 340, 0, 140)
        else:
            shot = tap_then(context, 130, move[1], titled)
            if shot is not None:
                return shot
    return None


@AgentServer.custom_action("SelectTeam")
class SelectTeam(CustomAction):
    """Pick the team's in-game TEAMS #N slot (pick_team_slot), press Confirm."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # No plan here means a run resumed on the entry page, paused before team selection: the entry page only
        # offers Resume again, so backing out looped (#128). Make one up from settings, as after a restart.
        n = current_run(context)["team"]["game_team"]
        image = pick_team_slot(context, n)
        if image is None:
            return stop(context, f"could not select TEAMS #{n}")
        RUN["planned"] = True  # the title reads the slot: the run's team is known, whatever the queue fits (#436)
        bonus = number(text(context, image, [1160, 522, 60, 34]))
        log(f"team TEAMS #{n}, Starlight Bonus {bonus}")
        # LevelWarning when the team is under the recommended level, else the starlight page; the team page
        # reads through the warning, so leaving it early would have MirrorHub pick the team twice.
        warning, starlight = shows(context, LEVEL_WARNING, "recommended level"), shows(context, STARLIGHT_HEADER, "Available")
        tap_then(context, 1145, 587, lambda im: warning(im) or starlight(im), timeout=4)
        return True


@AgentServer.custom_action("LuxSelectTeam")
class LuxSelectTeam(CustomAction):
    """A Luxcavation hub's team page (#366, shared by the EXP and Thread hubs): the mirror's page, with To Battle! where
    it has Confirm. Pick RUN["team"]'s in-game slot once, then press To Battle! until the page goes. The task's Enter
    action drops RUN["team_picked"] when it enters a stage: each battle picks again."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        n = RUN["team"]["game_team"]
        if not RUN.get("team_picked"):
            if pick_team_slot(context, n, "LuxTeamSelect") is None:
                return stop(context, f"Luxcavation: could not select TEAMS #{n}")
            RUN["team_picked"] = True
            log(f"Luxcavation: TEAMS #{n}")
        # A dialog over the page reads through it: the page staying is for the hub's watchdog to judge.
        if tap_then(context, *TO_BATTLE, lambda im: not seen(context, im, "LuxTeamSelect"), timeout=4) is None:
            log("Luxcavation: To Battle! pressed, the team page stays")
        return True


def grace_box(n):
    """Top-left corner of grace card n (1-10)."""
    col, row = (n - 1) % 5, (n - 1) // 5
    return GRACE_ORIGIN_X[row] + 198 * col, GRACE_ORIGIN_Y[row]


def grace_selected(image, n):
    # A selected card is washed white: mean V ~135 against ~60.
    x, y = grace_box(n)
    return image[y + 2:y + 222, x + 2:x + 182].max(axis=2).mean() > 100


def read_available(context, image):
    """Starlight left of Available; negative by what owned starlight pays when it reads like "0+60" (#96)."""
    t = text(context, image, STARLIGHT_AVAILABLE)
    m = re.fullmatch(r"\D*(\d+)\s*\+\s*(\d+)\D*", t)
    return int(m[1]) - int(m[2]) if m else number(t)


@AgentServer.custom_action("BuyStarlight")
class BuyStarlight(CustomAction):
    """Select graces per the team's starlight plan, then press Enter (spec 03 section 4).

    Live 2026-10-14: tapping a card selects it at the level its + / ++ buttons show;
    the buttons only set the level (tapping the lit one turns it back to base).
    A card dearer than Available is still selected, paid from owned starlight: choosing the grace is the
    user's consent to that (#96), so only Available plus Owned bounds the purchases, and Available is
    re-read after every tap.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        plan = run_start.resolve_plan(run["settings"], run["team"], "starlight")
        image = screen(context)
        available = read_available(context, image)
        if available is None:
            return stuck("could not read Available on the starlight page")
        owned = re.match(r"\D*(\d+)", text(context, image, STARLIGHT_OWNED))
        unaffordable = run["settings"]["run"]["starlight_unaffordable"]
        # Back from MirrorHub (#118): Available already has the graces selected so far taken off.
        paid = sum(run_start.grace_price(n, level) for n, level in enumerate(plan["levels"], 1)
                   if level != "none" and grace_selected(image, n))
        buys, missed = run_start.starlight_purchases(plan, available + paid + (int(owned[1]) if owned else 0), unaffordable)
        for n, level, price in missed:
            log(f"grace {n} {level} costs {price}: not bought")
        if missed and unaffordable == "stop":
            return stop(context, "a planned grace is unaffordable")
        for n, level, price in buys:
            x, y = grace_box(n)
            image = page_guard(context, "StarlightPage")
            if grace_selected(image, n):
                log(f"grace {n} already selected")
                continue
            if not self.set_level(context, n, level):
                return stuck(f"could not set grace {n} to {level}")
            for _ in range(2):
                page_guard(context, "StarlightPage")
                # Until Available reads what the grace leaves, at most the 1 s the tap slept (#58); any other number is
                # read once that 1 s is over, as before, so a number still counting down is not judged.
                image = tap_then(context, x + 92, y + 100, lambda im: read_available(context, im) == available - price,
                                 timeout=1.0)
                image = screen(context) if image is None else image
                now = read_available(context, image)
                if now != available:
                    break
            if now != available - price:
                page_guard(context, "StarlightPage", image=image)  # gone after the tap: back from MirrorHub, `paid` counts it
                return stop(context, f"grace {n} {level}: Available {available} -> {now}, expected -{price}")
            log(f"grace {n} {level} for {price}, {now} left" if now >= 0 else f"grace {n} {level} for {price}, {-now} paid from owned starlight")
            available = now
        run["starlight_unspent"] = max(available, 0)  # added to the Owned box at once unless ConfirmStarlight converts it (#73)
        tap_then(context, 1195, 672, shows(context, STARLIGHT_DIALOG, "Continue with selected"), timeout=3)
        return True

    @staticmethod
    def set_level(context, n, level):
        x, y = grace_box(n)
        base = run_start.GRACE_BASE[n - 1]
        want = run_start.LEVEL_MULT[level]
        def shown(image):
            price = number(text(context, image, [x + 112, y - 3, 80, 28]))
            return price // base if price and price % base == 0 else None

        for _ in range(4):
            now = shown(screen(context))
            if now == want:
                return True
            if now not in (1, 2, 3):
                time.sleep(0.5)  # kept: the price did not read (a fade, OCR); read it again
                continue
            button = want if want > 1 else now  # back to base = tap the lit button again
            page_guard(context, "StarlightPage")
            # until the price shows the level, at most the 1 s the tap slept (#58)
            tap_then(context, x + (50 if button == 2 else 132), y + 203, lambda im: shown(im) == want, timeout=1.0)
        return False


@AgentServer.custom_action("ConfirmStarlight")
class ConfirmStarlight(CustomAction):
    """Set Convert Starlight to Cost per the plan, press Confirm."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        want = run_start.resolve_plan(run["settings"], run["team"], "starlight")["convert_leftover"]
        for _ in range(4):
            image = screen(context)
            # The line under the checkbox: "Any unspent Starlight will be added ..." when off,
            # "Coverts any remaining Starlight ..." when on.
            note = text(context, image, STARLIGHT_NOTE)
            on = True if has(note, "remaining") else False if has(note, "unspent") else None
            if on == want:
                if want:
                    run["starlight_unspent"] = 0
                # The dialog stays up behind the game's Connecting; MirrorHub would confirm it twice.
                tap_then(context, 738, 530, shows(context, STARTING_GIFT_HEADER, "Selected E"), timeout=4)
                return True
            if on is not None:
                tap_then(context, 727, 363, lambda im: has(text(context, im, STARLIGHT_NOTE), "remaining" if want else "unspent"))
        return stuck("could not set Convert Starlight to Cost")


@AgentServer.custom_action("PickStartingGift")
class PickStartingGift(CustomAction):
    """Open the team keyword's cabinet, take its gifts in order until Select n/m is full, press Select."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        team = current_run(context)["team"]
        keyword = team["keyword"]
        self.set_gift_search(context, bool(team["gift_search"]["enabled"] and team["gift_search"]["gifts"]))
        if not self.full(context):
            for _ in range(3):
                image = page_guard(context, "StartingGift")
                label = next((b for t, b in ocr(context, image, [145, 145, 590, 430]) if compact(t) == compact(keyword)), None)
                if label:
                    break
                scroll(context, 440, 480, 0, -250)  # Pierce and Blunt sit below the fold
            else:
                return stuck(f"no {keyword} cabinet")
            x, y, w, h = label
            tap(context, x + w // 2, y + h // 2 + 75, wait=0)
            still(context, timeout=1.5)  # the cabinet's gifts slide in
            for gift_y in (262, 370, 475):
                before = self.count(context, page_guard(context, "StartingGift"))
                if before and before[0] == before[1]:
                    break
                tap_then(context, 970, gift_y, lambda im: self.count(context, im) != before, timeout=1.5)
            still(context, timeout=1.0)  # Live: Select ignores a tap in the picking animation
        # Live: the first tap on Select right after picking is often ignored.
        header, popup = shows(context, STARTING_GIFT_HEADER, "Selected"), shows(context, GET_TITLE, "GET")
        for _ in range(4):
            page_guard(context, "StartingGift")
            if tap_then(context, 1080, 587, lambda im: popup(im) or not header(im), timeout=2.5) is not None:
                log(f"starting gift: {keyword}")
                return True
        return stuck("Select did not take the starting gift")

    @staticmethod
    def set_gift_search(context, want):
        """Turn the Activate Gift Search switch on only for a team with gifts to search (spec 03 section 5).

        Live 2026-10-16: off skips the E.G.O Gift Search page; the next run keeps the switch (back on after a restart).
        An unread switch is left alone: the search page, if it comes, refuses or picks anyway.
        """
        def switch(image):
            shown = text(context, image, [1100, 145, 85, 28])
            return False if has(shown, "OFF") else True if has(shown, "ON") else None

        for _ in range(3):
            on = switch(page_guard(context, "StartingGift"))
            if on is None or on == want:
                return
            tap_then(context, 1140, 158, lambda im: switch(im) == want, timeout=1.5)
            log(f"Activate Gift Search: {'on' if want else 'off'}")

    @staticmethod
    def count(context, image=None):
        """The (n, m) strings of Select n/m, or None."""
        m = re.search(r"(\d)\s*/\s*(\d)", text(context, screen(context) if image is None else image, [990, 565, 190, 45]))
        return m.groups() if m else None

    @staticmethod
    def full(context):
        """Select n/m reads n == m."""
        n = PickStartingGift.count(context)
        return bool(n) and n[0] == n[1]


@AgentServer.custom_action("GiftGet")
class GiftGet(CustomAction):
    """Close the E.G.O Gift GET! popups, one after another, until none is up (#115).

    A search or a cabinet that gives n gifts pops n windows. The name plate tells the next window from the one
    just closed, which is closed once the screen is still, with no pass of MirrorHub in between. Taps are never
    sent ahead: under the last window lies the page the gifts came from (the search grid or the starting gift
    page), where one would pick; a window fading out still shows its title over a half-drawn plate.
    A window still up with the same name after the wait: the tap was lost, and MirrorHub looks again.
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        title = shows(context, GET_TITLE, "GET")
        image = screen(context)
        for _ in range(GIFT_WINDOWS):
            before = text(context, image, GET_NAME).strip()

            def closed(im):
                if not title(im):
                    return True
                now = text(context, im, GET_NAME).strip()
                return bool(before and now and now != before)
            image = tap_then(context, *GET_CONFIRM, closed, timeout=2)
            if image is not None and title(image):
                image = still(context, timeout=1)
            if image is None or not title(image):
                return True
        return True


GIFT_WINDOWS = 6  # GET! windows GiftGet closes in one go: a cabinet's gifts or a search's 3, with room to spare


# E.G.O Gift Search page (live 2026-10-16, 1.117.0). Tabs left to right, 62 px apart.
GRID_SWITCH_TIMEOUT = 5  # s a tab's gifts may take to show; they change in well under that, an empty tab pays it all
SEARCH_TABS = tuple(GIFT_KEYWORDS)  # the schema's keyword enum is the tabs, in order
SEARCH_COUNT = [1010, 550, 190, 50]  # "Select 0/3"
SEARCH_OWNED = ([935, 26, 120, 38], [1065, 26, 80, 38])  # "1315-270" and "1045"
SEARCH_PANEL_Y = (205, 316, 427)  # name lines of the Selected E.G.O Gift panel's 3 entries
SEARCH_SELECT = (1100, 575)
SEARCH_REFUSE = (922, 575)
SEARCH_DIALOG = [400, 315, 480, 60]  # "Consume 70 Starlight to search and obtain these E.G.O Gifts?"
FORGO_DIALOG = [480, 330, 320, 35]  # Refuse Gift's "Forgo ...?"
SEARCH_DIALOG_BUTTONS = {"cancel": (513, 495), "confirm": (765, 495)}
# A gift's icon (image/GiftSearch/<id>.png) scores 0.71-0.97 on its own cell, other cells up to ~0.75 (2026-10-16):
# low enough to try a dark icon; the panel name check undoes a lookalike.
SEARCH_ICON_MIN = 0.65
GRID_MID = 420  # a dragged-to gift's row lands here: whole rows above and below it


@AgentServer.custom_action("GiftSearch")
class GiftSearch(CustomAction):
    """E.G.O Gift Search (spec 03 section 5): the team's gifts in its order until Select n/m is full, then Select.

    Off, no gifts, or none of them found: Refuse Gift (the Forgo dialog is MirrorHub's). Gifts cost owned
    starlight; choosing them in the settings is the user's consent (#54). A gift is found by its icon among
    the cells of its tier (pick), tapped once, and kept only when the panel names it.
    """

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        search = run["team"]["gift_search"]
        wanted = search["gifts"] if search["enabled"] else []
        names = [g["name"] for g in wanted]
        if has(text(context, screen(context), SEARCH_DIALOG), "Consume"):
            # left open by an earlier try: check the picks again
            tap_then(context, *SEARCH_DIALOG_BUTTONS["cancel"], lambda im: not has(text(context, im, SEARCH_DIALOG), "Consume"), timeout=1.5)
        tried, dropped = [], 0
        while True:
            image = page_guard(context, "GiftSearch")
            count = gift_search.select_count(text(context, image, SEARCH_COUNT))
            if count is None:
                return True  # fading in or out: let MirrorHub look again
            chosen = self.chosen(context, image, names)
            unwanted = [k for k, c in enumerate(chosen) if c not in names]
            if unwanted and dropped < 3:
                # Left over from a tap that missed: tapping its panel entry unselects it (live 2026-10-16).
                log(f"gift search: unselecting {chosen[unwanted[0]]}, not in the team's list")
                tap_then(context, 1000, SEARCH_PANEL_Y[unwanted[0]] + 45, lambda im: self.chosen(context, im, names) != chosen, timeout=1.5)
                dropped += 1
                continue
            gift = gift_search.next_gift(wanted, chosen, tried, count)
            if gift is None:
                break
            tried.append(gift)
            if not self.pick(context, gift):
                log(f"gift search: {gift['name']} ({gift['keyword']} tier {gift['tier']}) not picked: not on the page, owned or unaffordable")
        if not chosen or unwanted:
            log("gift search: refused" + (f", {chosen} would not unselect" if unwanted else ""))
            tap_then(context, *SEARCH_REFUSE, shows(context, FORGO_DIALOG, "Forgo"), timeout=2)
            return True
        owned = gift_search.owned_starlight(*(text(context, image, roi) for roi in SEARCH_OWNED))
        # Select asks "Consume N Starlight to search and obtain these E.G.O Gifts?"; the GET! windows are MirrorHub's.
        for _ in range(3):
            page_guard(context, "GiftSearch")
            asked = tap_then(context, *SEARCH_SELECT, shows(context, SEARCH_DIALOG, "Consume"), timeout=2)
            if asked is not None:
                ask = text(context, asked, SEARCH_DIALOG)
                break
        else:
            return stuck("Select did not ask to consume starlight")
        # Live (run13c): the dialog reads while it still drops in on its chains, and a tap then does nothing.
        page_guard(context, "GiftSearch", image=still(context, timeout=1.5))  # also under its Consume dialog (maatools: GiftSearchConfirm.png)
        # The search page reads through the dialog and again before the first window: leaving early would buy twice.
        tap_then(context, *SEARCH_DIALOG_BUTTONS["confirm"], shows(context, GET_TITLE, "GET"), timeout=4)
        price = number(ask.split("Starlight")[0])
        # The Owned box counts the Starlight left unspent on the starlight page (#73): not the account's before the run.
        before = owned[0] - RUN.get("starlight_unspent", 0) if owned else None
        after = before - price if before is not None and price is not None else None
        log(f"gift search: bought {', '.join(chosen)} for {price} owned starlight; owned starlight {before} -> {after}")
        run["gift_search"] = {"gifts": chosen, "starlight": price, "owned_before": before, "owned_after": after}
        return True

    @staticmethod
    def chosen(context, image, names):
        """The gifts the Selected E.G.O Gift panel lists, as the team's names where they match."""
        texts = [text(context, image, [922, y, 270, 34]) for y in SEARCH_PANEL_Y]
        return [run_start.match_name(t, names) or t for t in texts if t.strip()]

    @staticmethod
    def pick(context, gift):
        """Select gift: find its icon among its tier's cells, tap it once, and check the panel names it.

        The observation table's order says how far down the tab the gift sits, so the tab is dragged
        straight there; when the icon is not on that screen (the account lacks a gift above it, or the drag
        fell short) the tab is searched from the top, screen by screen. Cells are never tapped to read names.
        """
        tab = [g for g in gift_tables()[0] if g["keyword"] == gift["keyword"]]
        entry = next((g for g in tab if g["tier"] == gift["tier"] and run_start.match_name(g["en"], [gift["name"]])), None)
        if entry is None:
            log(f"gift search: {gift['name']} is not in data/gift_search.json")
            return False
        start = time.time()
        GiftSearch.open_tab(context, gift["keyword"])
        y = gift_search.expected_cell(tab, entry["en"])[1]
        guessed = y > gift_search.LAST_Y
        if guessed:
            GiftSearch.scroll(context, y - GRID_MID)
            # Line the grid up by the section headers on screen, not by the distance dragged.
            y = gift_search.cell_y(tab, entry["en"], gift_search.section_headers(screen(context)))
            if y is not None and abs(y - GRID_MID) > 140:
                GiftSearch.scroll(context, y - GRID_MID)
        for _ in range(12):
            image = page_guard(context, "GiftSearch")
            cells = gift_search.gift_cells(image)
            for k, (score, x, y) in enumerate(GiftSearch.icon_scores(context, image, entry["id"], [c for c in cells if c[2] == gift["tier"]])[:2]):
                if score < SEARCH_ICON_MIN:
                    break
                if k:
                    image = page_guard(context, "GiftSearch")  # the first candidate's tap and wait lie behind this one
                if GiftSearch.tap_and_check(context, image, x, y, gift["name"]):
                    log(f"gift search: {gift['name']} selected in {time.time() - start:.1f} s (icon {score:.2f})")
                    return True
            if guessed:
                guessed = False
                log(f"gift search: {gift['name']} is not where the table puts it: searching {gift['keyword']} from the top")
                GiftSearch.open_tab(context, gift["keyword"])
                continue
            if any(tier < gift["tier"] for _, _, tier in cells):
                return False  # the tiers below have started: the wanted tier is done
            GiftSearch.scroll(context, 300)
            if not grid_moved(image, screen(context)):
                return False  # the end of the tab
        return False

    @staticmethod
    def open_tab(context, keyword):
        """Open keyword's tab at its top: switching tabs resets the scroll (live 2026-10-16), so via a neighbour."""
        i = SEARCH_TABS.index(keyword)
        for x, attempts in ((113 + 62 * (i + 1 if i == 0 else i - 1), 1), (113 + 62 * i, 2)):
            # Live (run13): the tab lights up at once, its gifts a few looks later; a tap sent before then was
            # lost, or the grid read showed the last tab's gifts. Wait for the gifts to change, then the fade.
            # Live 2026-10-20 (#190): Keywordless's grid took over 1.6 s, so a 1 s wait read Blunt's gifts.
            before = page_guard(context, "GiftSearch")
            for attempt in range(attempts):  # the wanted tab's tap may be lost: the grid then never moves, so tap it again
                if attempt:
                    page_guard(context, "GiftSearch")  # the retry comes after GRID_SWITCH_TIMEOUT: the page may be gone by then
                if tap_then(context, x, 190, lambda im: grid_moved(before, im), timeout=GRID_SWITCH_TIMEOUT) is not None:
                    break
            else:
                log(f"gift search: the grid did not change after tapping the tab at x={x}")
            still(context, timeout=1)

    @staticmethod
    def scroll(context, distance):
        """Drag the grid up by distance px (down when negative), in strokes that stay inside it.

        Dragged past the tab's end, the grid springs back after the lift: wait that out.
        """
        page_guard(context, "GiftSearch")  # the tab's tap and fade lie between the last look and this drag
        while abs(distance) > 20:
            step = max(-300, min(distance, 300))
            scroll(context, 430, 590 if step > 0 else 290, 0, -step)
            distance -= step
        time.sleep(0.5)

    @staticmethod
    def icon_scores(context, image, gid, cells):
        """[(score, x, y)] best first: the gift's icon (data/gift_search.json id) matched on each cell, TM_CCORR_NORMED."""
        node = {"recognition": "TemplateMatch", "template": f"GiftSearch/{gid}.png", "threshold": 0.0, "method": 3, "green_mask": True}
        out = []
        for x, y, _ in cells:
            detail = context.run_recognition("GiftIcon", image, {"GiftIcon": {**node, "roi": [x - 40, y - 40, 80, 80]}})
            out.append((detail.best_result.score if detail and detail.best_result else 0.0, x, y))
        return sorted(out, reverse=True)

    @staticmethod
    def tap_and_check(context, image, x, y, name):
        """Tap a cell; True when the panel's new entry is name, else tap it off again (a lookalike icon)."""
        before = GiftSearch.chosen(context, image, [])
        after = tap_then(context, x, y, lambda im: GiftSearch.chosen(context, im, []) != before, timeout=1)
        new = [t for t in GiftSearch.chosen(context, after if after is not None else screen(context), []) if t not in before]
        if new and run_start.match_name(new[0], [name]):
            return True
        if new:
            log(f"gift search: the icon match picked {new[0]}, not {name}: unselected")
            page_guard(context, "GiftSearch")  # the tap above waited up to 1 s
            tap_then(context, x, y, lambda im: GiftSearch.chosen(context, im, []) == before, timeout=1)
        return False


def theme_pack_plan(settings, team):
    """(the team's plan, the data file's packs (name -> floors), its event packs, its title art reads): the default plan or
    the user's (spec 04 section 8)."""
    file = data("theme_packs.yaml")
    ref = team["theme_pack_plan"]
    plan = file["default_plan"] if ref == "default" else next(p for p in settings["theme_pack_plans"] if p["id"] == ref)
    return plan, file["packs"], set(file["event_packs"]), file["title_art"]


@functools.cache
def pack_ids():
    """Pack name -> id, every pack of the data file's `pack_ids`."""
    return data("theme_packs.yaml")["pack_ids"]


def note_pack(name):
    """Note the pack PickThemePack pulled in the run; a run that lost its earlier floors leaves it unknown, a pack the data file
    has no id for (most EXTREME-only packs, an event pack newer than the file) is skipped and the rest stay noted."""
    if "packs" not in RUN:
        return
    ids = pack_ids()
    if name not in ids:
        log(f"pack {name!r} has no id: left out of the run's packs")
        return
    # A re-run (BokGak) shows the original's title: a card whose BokGak line was read is already the copy's name (one id), else the
    # pull may be either: note both (some recipes name only the re-run).
    RUN["packs"] += [i for i in (ids[name], ids.get(f"{name} BokGak")) if i is not None and i not in RUN["packs"]]


def pack_titles(context, image):
    """Cards left to right as (x centre, [text lines top to bottom]); see run_start.pack_cards."""
    return run_start.pack_cards(ocr(context, image, PACK_TITLES))


def refresh_lit(image):
    """Whether the theme pack page's Refresh button is lit: REFRESH_LIT_MIN of its px over REFRESH_BRIGHT (#482)."""
    x, y, w, h = REFRESH_BUTTON
    return bool((image[y:y + h, x:x + w].max(axis=2) > REFRESH_BRIGHT).sum() >= REFRESH_LIT_MIN)


@AgentServer.custom_action("PickThemePack")
class PickThemePack(CustomAction):
    """Set this floor's difficulty, then pull the best pack: highest weight, leftmost first (spec 03 sections 2, 6)."""

    @hands_back
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        run = current_run(context)
        image = screen(context)
        floor = floor_number(text(context, image, [480, 100, 320, 40]))
        if floor is None:
            return True  # page fading in or out: let MirrorHub look again
        if floor != RUN.get("floor"):
            RUN.pop("after_shop", None)
            if floor == 1:
                RUN.pop("floors_hard", None)  # a floor 1 after a later floor is a new run's: no difficulty of the last one stays (#382)
            RUN.pop("resumed", None)  # this floor's map comes up from its theme pack
            TASK.pop("modules", None)  # a run is under way: Claim will take 5, the next one reads the Modules again (#369)
            RUN.update(floor=floor, map_misses=0)  # a new floor's map gets a fresh retry quota (spec 06)
            restart_floor_clock()
            STUCK["ladder"].floor(floor, run["settings"].get("run", {}).get("target_floor", 5))  # floors 6 and 11 refill L2/L3 (#435)
        want = None if run["difficulty"] is None else run_start.hard_wanted(floor, run["difficulty"] == "hard", run["team"]["hard_from_floor"])
        if not self.set_difficulty(context, floor, want):
            return stuck(f"floor {floor} difficulty did not switch to {'HARD' if want else 'NORMAL'}")

        plan, file_packs, event_packs, file_art = theme_pack_plan(run["settings"], run["team"])
        packs, names, title_art = run_start.floor_reads(file_packs, plan["weights"], file_art, floor)  # #387: the floor's packs
        setting = run["settings"]["run"]["theme_pack_refresh"]
        prev = None
        for used in range(10):  # a greyed button or its `0/m` ends it (#319, #482); unread, a refresh that changes nothing does
            settled = still(context, timeout=CARDS_SETTLE, roi=PACK_CARDS, runs=2)
            if settled is None:
                log(f"floor {floor}: the cards still moved after {CARDS_SETTLE:g} s")
            page = page_guard(context, "ThemePack", settled)
            cards = pack_titles(context, page)
            if not cards:
                return stuck("no theme pack titles read")
            ranked = run_start.rank_packs([lines for _, lines in cards], names, plan, title_art,
                                          lambda i, allowed: pack_cover.read_cover(page, cards[i][0], allowed))
            slots = run_start.event_slots(floor, [t for t, _, _ in ranked], event_packs, packs)
            log(f"floor {floor} packs, threshold {plan['threshold']}: "
                + ", ".join(f"{t} ({w}{', event' if e else ''})" for (t, w, _), e in zip(ranked, slots)))
            log(f"floor {floor} card reads: " + ", ".join(f"{t} <- {how}" for t, _, how in ranked))  # #274: which path named each card
            titles = [t for t, _, _ in ranked]
            i, meets = run_start.pick_pack([w for _, w, _ in ranked], slots, plan)
            if not run_start.refresh_wanted(meets, setting, used) or titles == prev:
                break
            if not refresh_lit(page) or seen(context, page, "PackRefreshSpent"):
                log(f"floor {floor}: no free refresh left")
                break
            prev = titles
            # A fixed 3 s (#258): the new hand swings in and stood still 2.71-2.97 s after the tap (the 5 refreshes that
            # dealt one on the 2026-10-29 and 2026-11-08 recordings, tools/tap_waits.py), so the still() above would read
            # it at most 0.3 s sooner.
            tap(context, 1083, 47, wait=3)
        x = cards[i][0]
        log(f"floor {floor}: pull {ranked[i][0]!r} ({ranked[i][1]}{'' if meets else ', below the threshold'})")
        swipe(context, x, 330, x, 650, ms=600, wait=0)
        note_pack(ranked[i][0])
        RUN["fresh_floor"] = True  # find_bus: the new map takes no drag for its first seconds
        # The page fades out slowly; do not let MirrorHub pull twice.
        until(context, lambda im: not has(text(context, im, [480, 100, 320, 40]), "FLOOR"), timeout=9)
        return True

    @staticmethod
    def set_difficulty(context, floor, want):
        def label(image):
            shown = text(context, image, [830, 30, 160, 35])
            return True if has(shown, "HARD") else False if has(shown, "NORMAL") else None

        for _ in range(4):
            hard = label(page_guard(context, "ThemePack"))
            if hard is None:
                until(context, lambda im: label(im) is not None, timeout=1)
                continue
            move = run_start.difficulty_move(floor, hard, want)
            if move is None:
                if want is not None and hard != want:
                    log(f"floor {floor} stays HARD: a run never goes back to NORMAL")
                log(f"floor {floor}: {'HARD' if hard else 'NORMAL'}")
                RUN["floor_hard"] = hard  # the map does not show it; RouteMap's weights need it
                RUN.setdefault("floors_hard", {})[floor] = hard  # what Settle's weekly bonuses count on (#382)
                return True
            # The arrows sit left of HARD, right of NORMAL; switching re-rolls the packs.
            log(f"floor {floor}: switch to {move.upper()}")
            tap_then(context, 965 if move == "hard" else 850, 46, lambda im: label(im) == (move == "hard"), timeout=2.5)
            still(context, timeout=1.5)  # the packs re-roll
        return False
