"""Luxcavation's custom actions: the start and the drive, the Luxcavation home, the EXP pass, the entry with its
consecutive battles, and the result."""

import json
import time

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import luxcavation
import pass_missions
from actions import (ROOT, RUN, TASK, TaskStart, box_centre, end_battle, finish, go_home, log, log_change, ocr_texts,
                     param, screen, seen, shows, stop, tap, tap_then, text, until)
from ocrtext import digits
from settings import SettingsError, load_settings


def module_count(context, image):
    """The Enkephalin Modules the bottom-left panel shows (main window, Drive, Luxcavation, any page with the panel); None
    when the panel is not on the screen or its number does not read (#367).

    The panel's x moves between pages, so the round Module icon is found first (ModuleIcon) and the digits read as one
    line to its right: the dark field ends 78 px after the icon's left edge, its digits right-aligned.
    """
    detail = context.run_recognition("ModuleIcon", image)
    if not detail or not detail.hit:
        return None
    x, y, w, h = detail.best_result.box
    return digits(text(context, image, [x + w + 2, y + 2, 50, h - 4], only_rec=True))


# The Luxcavation tasks (#366, #368): their settings key (custom_action_param of LuxStart) -> name, Modules a battle.
LUX = {"exp": ("EXP Luxcavation", luxcavation.EXP_COST), "thread": ("Thread Luxcavation", luxcavation.THREAD_COST)}


@AgentServer.custom_action("LuxStart")
class LuxStart(TaskStart):
    """A Luxcavation task's entry (#366, #368), its param the settings key ("exp", "thread"): TaskStart, then the team
    luxcavation.<key> names, whose guard turns the battle plays (spec 03 section 8), its mode (#431), count and retries (#367).
    No team picked, or settings that do not load: the stop procedure, before any tap."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not super().run(context, argv):
            return False
        key = json.loads(argv.custom_action_param)
        name, cost = LUX[key]
        try:
            settings = load_settings(ROOT)
        except SettingsError as e:
            return stop(context, str(e))
        opts = settings["luxcavation"][key]
        team = next((t for t in settings["teams"] if t["id"] == opts["team"]), None)
        if team is None:
            return stop(context, f"{name} has no team: pick one in the settings GUI's Daily tab")
        # Not RUN["settings"]: that is a Mirror Dungeon run, which the stop procedure writes to runs.jsonl.
        # lux: this task's battles (spec 03 section 15): mode, daily or count (#431); target, count's wins this run or the
        # day's in daily mode (luxcavation.DAILY); today, those won today as read (plan) and seen, what was read, for the
        # log; fights, the battles this run fights, None until planned; the battles won and the retries used, the last
        # battle's result.
        mode = opts["mode"]
        target = opts["count"] if mode == "count" else luxcavation.DAILY[key]
        RUN.update(team=team, guard=team["guard_turns"],
                   lux={"name": name, "cost": cost, "mode": mode, "target": target, "today": None, "seen": None, "fights": None,
                        "retries": opts["retries"], "modules": None, "won": 0, "retried": 0, "result": None,
                        "consecutive": opts["consecutive"], "size": 1})
        log(f"{name}: team {team['name']!r} (TEAMS #{team['game_team']}), {team['guard_turns']} guard turns, "
            + (f"mode count, {target} wins this run" if mode == "count" else "mode daily")
            + f", {opts['retries']} retries, consecutive {'on' if opts['consecutive'] else 'off'}")
        return True


def modules_now(context, timeout=3):
    """The Modules the panel shows now (module_count), looked for up to timeout s: None when it never reads."""
    found = []
    until(context, lambda image: found.append(module_count(context, image)) or found[-1] is not None, timeout)
    return found[-1]


@AgentServer.custom_action("OpenDrive")
class OpenDrive(CustomAction):
    """NavDrive: the Drive page has the Modules panel (tests/screens/Drive.png), the entry page the next tap opens has
    none. Read the number for PlanRun's gate (#369) before tapping Mirror Dungeons; None when it does not read. Then
    until the entry page's text shows (param {"next": {"roi", "expected"}, "timeout": s}), not a fixed 3 s (#58)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        TASK["modules"] = module_count(context, screen(context))
        p = json.loads(argv.custom_action_param)
        began = time.monotonic()
        image = tap_then(context, *box_centre(argv.box), shows(context, p["next"]["roi"], p["next"]["expected"]),
                         timeout=p["timeout"])
        log_change(argv.node_name, image, began)
        return True


@AgentServer.custom_action("LuxHome")
class LuxHome(CustomAction):
    """A Luxcavation task's step after LuxStart (EXP in daily mode: after the pass page): the main window, then the Modules
    the panel shows (#367). A panel that does not read stops the task: nothing is known to be safe to spend. Count mode
    plans the task here, as does the param {"plan": true} (EXP, whose battles won today were read on the pass page);
    Thread in daily mode plans on the Thread tab, where its Daily Bonuses show (LuxEnter)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not go_home(context):
            return False
        lux = RUN["lux"]
        lux["modules"] = modules_now(context)
        if lux["modules"] is None:
            return stop(context, f"{lux['name']}: the Modules number did not read on the main window")
        log(f"{lux['name']}: Modules {lux['modules']} on the main window")
        if lux["mode"] == "count" or (param(argv.custom_action_param) or {}).get("plan"):
            over = plan(context, lux["today"], lux["seen"])
            return True if over is None else over
        return True


def plan(context, today, seen):
    """The battles this run fights (luxcavation.fights): count mode, the target; daily mode (#429), the day's target less
    `today`, the battles won today as read (None: it did not read), `seen` what was read, for the log. Nothing read or
    nothing left: the main window and done, nothing fought; else the Modules must cover the battles at the hardest
    stage's cost (spec 03 section 15), or the task is skipped the same way. None: RUN["lux"]["fights"] is set and the
    battles go on; else what the action returns."""
    lux = RUN["lux"]
    fights = luxcavation.fights(lux["mode"], lux["target"], today)
    if fights is None:
        return finish(context, f"{lux['name']}: {seen}: nothing fought")
    lux["today"] = today
    head = (f"{lux['name']}: count mode, {fights} this run" if lux["mode"] == "count"
            else f"{lux['name']}: {seen} ({today} won today), {lux['target']} a day")
    if fights == 0:
        return finish(context, f"{head}: nothing to fight")
    need = luxcavation.needed(lux["cost"], fights)
    if luxcavation.decide(lux["modules"], lux["cost"], fights, 0, 0, lux["retries"]) == luxcavation.SKIP:
        return finish(context, f"{head}: Modules {lux['modules']} < {need} needed for {fights}, skipped")
    lux["fights"] = fights
    log(f"{head}: Modules {lux['modules']} >= {need} needed, fight {fights}")
    return None


@AgentServer.custom_action("ExpPassRead")
class ExpPassRead(CustomAction):
    """The pass page's Daily tab (ExpPassHub): its Clear EXP Luxcavation row, found by its text (PassExpRow) and read
    by its look (pass_missions.row_done): done is 1 won today, under way 0 (#429). The rows may still slide in, so it
    looks for up to 3 s; never found, or the param {"lost": true} (60 s with no pass page), is no read. Nothing is
    tapped."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        lux = RUN["lux"]
        found = []
        lost = (param(argv.custom_action_param) or {}).get("lost")
        if not lost:
            def row(image):
                detail = context.run_recognition("PassExpRow", image)
                if detail and detail.hit:
                    x, y, w, h = detail.best_result.box
                    found.append(pass_missions.row_done(image, pass_missions.nearest_row(y + h // 2)))
                return bool(found)
            until(context, row, timeout=3)
        if found:
            lux["today"] = int(found[-1])
            lux["seen"] = f"the pass's Clear EXP Luxcavation row {'done' if found[-1] else 'under way'}"
        elif lost:
            lux["seen"] = "the pass page was not reached in 60 s"
        else:
            lux["seen"] = "the pass's Clear EXP Luxcavation row did not read"
        log(f"{lux['name']}: {lux['seen']}")
        return True


def battle_over(context):
    """A Luxcavation battle was entered (RUN["entered"]) and the page it started from shows again: count its result
    (LuxResult sets it) and say what next (luxcavation.decide, #367). None: the next battle, or the same one again after a
    defeat; else what the action returns: True once the main window is reached and the task done, False from the stop
    procedure."""
    lux = RUN["lux"]
    RUN.pop("entered")
    result, lux["result"] = lux["result"], None
    if result is None:
        return stop(context, f"{lux['name']}: back on the page with no results page seen")
    step = luxcavation.decide(lux["modules"], lux["cost"], lux["fights"], lux["won"], lux["retried"], lux["retries"], result,
                              lux["size"])
    lux["won"] += lux["size"] * (result == "win")
    # Each battle has its own retries, as the mirror's wipe retries: a win starts the next battle at 0 (review S6).
    lux["retried"] = 0 if result == "win" else lux["retried"] + (step == luxcavation.RETRY)
    log(f"{lux['name']}: {result}, {lux['won']} of {lux['fights']} won, {lux['retried']} of {lux['retries']} retries of this battle used: {step}")
    if step == luxcavation.FINISH:
        return finish(context, f"{lux['name']}: {lux['won']} won")
    if step == luxcavation.STOP:
        return stop(context, f"{lux['name']}: defeated with the {lux['retries']} retries used up")
    RUN["guard"] = RUN["team"]["guard_turns"]  # each battle guards its first turns (2026-10-27)
    return None


# The Consecutive Battle box of each page that has one (live 2026-10-27, 1280x720): the title's OCR roi (short of its arrow,
# which the OCR reads as a 7), a narrower roi on its "x N", the title to tap (opens and closes the row), and the row's y with
# the x of 1<<, -, +, >>10. The EXP and Thread boxes sit on their card, whose place changes (the EXP tab's rightmost open stage
# is the middle card where the 10th is locked): theirs are given for the card whose Enter has the centre in ENTER_AT, and
# move by how far the Enter in use is from it. Level Select's box does not move.
CONSECUTIVE = {
    "exp": ([990, 240, 205, 30], [1135, 240, 50, 28], (1110, 254), 286, {"one": 1008, "minus": 1038, "plus": 1179, "ten": 1209}),
    "thread": ([250, 212, 230, 28], [400, 212, 50, 28], (370, 226), 259, {"one": 272, "minus": 305, "plus": 436, "ten": 469}),
    "level": ([510, 170, 225, 26], [680, 170, 45, 26], (640, 183), 217, {"one": 530, "minus": 563, "plus": 716, "ten": 749}),
}
ENTER_AT = {"exp": (1079, 479), "thread": (372, 481)}  # the centre of LuxExpEnter on stage 9 at the right, of LuxThreadEnter


def consecutive_box(box, enter=None):
    """CONSECUTIVE[box] for the card whose Enter has its centre at `enter` (x, y): the rois, the title tap, the row's y and
    the buttons' xs moved by its distance from ENTER_AT. `enter` None (Level Select), or a page of no card: as given."""
    title, digit, (title_x, title_y), row_y, buttons = CONSECUTIVE[box]
    if box not in ENTER_AT or enter is None:
        return title, digit, (title_x, title_y), row_y, buttons
    dx, dy = enter[0] - ENTER_AT[box][0], enter[1] - ENTER_AT[box][1]
    return ([title[0] + dx, title[1] + dy, *title[2:]], [digit[0] + dx, digit[1] + dy, *digit[2:]], (title_x + dx, title_y + dy),
            row_y + dy, {name: x + dx for name, x in buttons.items()})


def consecutive_now(context, image, box, enter=None):
    """The N of the Consecutive Battle title on `box`'s page (1-10), None when it does not read: the narrow roi on its "x N"
    first, which reads the yellow 4 the whole title's detection misses (Level Select, live 2026-10-27), then the title.
    `enter`: the centre of the Enter the card's box is above (consecutive_box)."""
    title, digit = consecutive_box(box, enter)[:2]
    return (luxcavation.parse_consecutive(text(context, image, digit, only_rec=True))
            or luxcavation.parse_consecutive(text(context, image, title)))


def set_consecutive(context, box, target, enter=None):
    """Set the Consecutive Battle of `box`'s page (the card of the Enter at `enter`) to `target` and read it back: the N it
    shows at the end, None when it never read. The game resets it to 1 on leaving Luxcavation and after a result, so each
    entry sets it (live 2026-10-28)."""
    _, _, (title_x, title_y), row_y, buttons = consecutive_box(box, enter)
    shown = []
    until(context, lambda im: shown.append(consecutive_now(context, im, box, enter)) or shown[-1] is not None, timeout=3)
    if shown[-1] is None:
        log(f"Consecutive Battle ({box}): does not read, wants x{target}")
        return None
    log(f"Consecutive Battle ({box}): shows x{shown[-1]}, wants x{target}")
    if shown[-1] == target:
        return target
    tap(context, title_x, title_y, wait=0.5)  # open the row
    keys = luxcavation.presses(shown[-1], target)
    log(f"Consecutive Battle ({box}): pressed {', '.join(keys)}")
    for name in keys:
        tap(context, buttons[name], row_y, wait=0.3)
    tap(context, title_x, title_y, wait=0.5)  # close it again
    shown.clear()
    until(context, lambda im: shown.append(consecutive_now(context, im, box, enter)) or shown[-1] == target, timeout=3)
    log(f"Consecutive Battle ({box}): {'does not read' if shown[-1] is None else f'shows x{shown[-1]}'} after closing the row"
        + ("" if shown[-1] == target else f", wanted x{target}"))
    return shown[-1]


@AgentServer.custom_action("LuxEnter")
class LuxEnter(CustomAction):
    """An Enter of a Luxcavation page (the node's box): the EXP tab's rightmost open stage (LuxExpEnter), the Thread
    tab's open card (LuxThreadEnter), the bottom row of the card's Level Select, its hardest level (LuxThreadLevel). Tap
    it until the page goes. The param {"opens_battle": false} marks the card's Enter, which opens the Level Select, not
    the battle (#368). Back on the page a battle started from: the battle is over (battle_over). Where the task fights
    consecutively, the param's "box" names the page's Consecutive Battle (CONSECUTIVE): it is set to the wins left, up
    to 10, before the tap (#375); one that will not read or set stops the task, so no battle starts at the wrong count.
    A task not planned yet (Thread's first look at its card, in daily mode) reads the tab's Daily Bonuses and plans first
    (#429): n left of 3 is 3 - n won today."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if RUN.get("entered"):
            over = battle_over(context)
            if over is not None:
                return over
        opts = param(argv.custom_action_param) or {}
        lux = RUN["lux"]
        if lux["fights"] is None:  # Thread in daily mode only: count mode was planned in LuxHome
            n = luxcavation.read_bonuses(ocr_texts(context, screen(context), "ThreadBonuses"))
            shown = "Daily Bonuses did not read" if n is None else f"Daily Bonuses {n}/{luxcavation.DAILY_BONUSES}"
            over = plan(context, None if n is None else luxcavation.DAILY_BONUSES - n, shown)
            if over is not None:
                return over
        cx, cy = box_centre(argv.box)
        if lux["consecutive"]:
            want = lux["size"] = luxcavation.batch(lux["fights"], lux["won"], True)
            got = set_consecutive(context, opts["box"], want, (cx, cy))
            if got != want:
                return stop(context, f"{lux['name']}: Consecutive Battle {'did not read' if got is None else f'shows x{got}'}, wanted x{want}")
        if tap_then(context, cx, cy, lambda im: seen(context, im, argv.node_name) is None, timeout=3) is not None:
            RUN["entered"] = opts.get("opens_battle", True)
            RUN["team_picked"] = False
            log(f"{RUN['lux']['name']}: {argv.node_name} at ({cx}, {cy})")
        return True


LUX_CONFIRM = (1125, 570)  # the results page's Confirm (live 2026-10-27)


@AgentServer.custom_action("LuxResult")
class LuxResult(CustomAction):
    """The results page after a Luxcavation battle (live-1 F2, pipeline LuxResult): its Victory or Defeat is the result of
    the battle entered (RUN["entered"]), kept for battle_over; then Confirm until the page goes. Neither word read yet:
    the page is still fading in, and the hub looks again. A defeat (by hand, Give Up: no confirm dialog) takes no
    Module and no Daily Bonus (live 2026-10-27)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        image = screen(context)
        result = "win" if seen(context, image, "LuxWon") else "lose" if seen(context, image, "LuxLost") else None
        if result is None:
            return True
        end_battle()
        if RUN.get("entered") and RUN["lux"]["result"] is None:
            RUN["lux"]["result"] = result
            log(f"{RUN['lux']['name']}: results page, {'Victory' if result == 'win' else 'Defeat'}")
        tap_then(context, *LUX_CONFIRM, lambda im: seen(context, im, "LuxResult") is None, timeout=4)
        return True
