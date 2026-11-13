"""The daily tasks' custom actions: Assemble Modules, Charge Enkephalin, the mail and the pass."""

import time

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

import lunacy
import pass_missions
from actions import (ROOT, TASK, TaskStart, back, done, finish, log, node_results, ocr_texts, screen, seen, stop, tap,
                     tap_then)
from ocrtext import fractions as text_fractions
from settings import SettingsError, load_settings


@AgentServer.custom_action("MailDone")
class MailDone(CustomAction):
    """ClaimMail's end, on the empty Mailbox: the main window, then done with what this run did (live-2 G3: a box emptied
    by Claim All said "no mail to claim")."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return finish(context, "mail claimed" if context.get_hit_count("MailClaimAll") else "no mail to claim")


AgentServer.custom_recognition("PassClaimable")(pass_missions.PassClaimable)
PASS_CLAIMS = ("PassDailyClaim", "PassWeeklyClaim", "PassSeasonalClaim", "PassSeasonalEndClaim")  # a hit taps one row


@AgentServer.custom_action("PassFinish")
class PassFinish(CustomAction):
    """ClaimPassMissions' last step: the main window (GoHome), then done with the rows tapped this run (live-1 F6: a run
    with nothing to claim said "pass missions claimed")."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        n = sum(context.get_hit_count(node) for node in PASS_CLAIMS)
        return finish(context, f"pass missions: {n} row(s) claimed" if n else "pass missions: nothing to claim")


# Assemble Enkephalin Modules (#370, pipeline/assemble_modules.json).
MODULE_COST = 20  # Enkephalin per module
ENK_BAR = (440, 640)  # the resource panel's Enkephalin bar: opens the Charge Enkephalin window
ASSEMBLE_MAX = (805, 328)  # the Modules tab's >> (the most)
MODULES_TAB = (505, 226)  # the Charge Enkephalin window's Modules tab (live 720p, 2026-10-26)
PANEL_CONFIRM, PANEL_CANCEL = (760, 534), (520, 534)  # the Charge Enkephalin window's Confirm and Cancel, on every tab
ASSEMBLE_TRIES = 3  # reads, taps of >> and Confirms the task spends before it gives up


def fractions(results):
    """Every "n / cap" of OCR results [(text, box)], left to right, as (n, cap)."""
    return [f for t, _ in sorted(results, key=lambda r: r[1][0]) for f in text_fractions(t)]


def read_fractions(context, image, node):
    return fractions(node_results(context, image, node))


def panel_read(context, image):
    """The window's Enkephalin before and after, [(n, cap), (n, cap)], each read on its own side of the arrow; [] unless
    both read."""
    before, after = read_fractions(context, image, "AssembleBefore"), read_fractions(context, image, "AssembleAfter")
    return before[:1] + after[-1:] if before and after else []


def cancel_stop(context, reason):
    """The stop procedure, its evidence the window itself (live-3 H1), then Cancel closes the window; False."""
    stop(context, reason)
    tap(context, *PANEL_CANCEL, wait=0.5)
    return False


def on_modules_tab(context, image):
    """The Modules tab's own prompt ("Would you like to assemble Enkephalin Modules?") is up. The Use Lunacy tab shows the
    Enkephalin before and after as well, so the two "n / cap" alone do not tell the tabs apart: a Confirm there spends
    Lunacy."""
    detail = context.run_recognition("AssemblePrompt", image)
    return bool(detail and detail.hit)


def too_many(context, image):
    detail = context.run_recognition("AssembleTooMany", image)
    return bool(detail and detail.hit)


def open_enkephalin(context):
    """The Enkephalin bar, then until the Charge Enkephalin window shows (3 s at most): the hub's next look at the main
    window would tap the bar again (#362, instead of a fixed 1.5 s)."""
    tap_then(context, *ENK_BAR, lambda im: seen(context, im, "EnkephalinWindow") is not None, timeout=3)


@AgentServer.custom_action("AssembleMain")
class AssembleMain(CustomAction):
    """The main window, reached by GoHome or already there: the task's one way out and its way in. With the Enkephalin
    under a module's cost, or the game's refusal seen, it is done; after a Confirm the bar must read lower than before
    it; else the bar opens the window."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        a = TASK.setdefault("assemble", {"reads": 0, "confirms": 0})
        read = read_fractions(context, screen(context), "EnkephalinBar")
        if not read:
            a["reads"] += 1
            return True if a["reads"] < ASSEMBLE_TRIES else stop(context, "the Enkephalin bar could not be read")
        a["reads"], n = 0, read[0][0]
        if a.get("end"):
            return done(a["end"])
        if "before" in a:
            if n < a["before"]:
                return done(f"Enkephalin {a['before']} -> {n}, assembled")
            time.sleep(1)  # the bar counts down; read it again before judging
            a["checks"] = a.get("checks", 0) + 1
            return True if a["checks"] < ASSEMBLE_TRIES else stop(context, f"Enkephalin still {n} after Confirm")
        if n < MODULE_COST:
            return done(f"Enkephalin {n} < {MODULE_COST}, nothing to assemble")
        log(f"assemble: Enkephalin {n}, opening the window")
        open_enkephalin(context)
        return True


@AgentServer.custom_action("AssemblePanel")
class AssemblePanel(CustomAction):
    """The Charge Enkephalin window: its Modules tab first (the window opens on the tab it was left on, #362 D7), then on
    it (its prompt and the Enkephalin before and after read), >> for the most modules, Confirm. Only the tab, >>, Confirm
    and Cancel are tapped. Not on the Modules tab, or a number that stops reading after >>: the stop procedure, then
    Cancel, never Confirm (Use Lunacy's Confirm spends Lunacy). The game's refusal ends the task; a window over a task
    already decided is cancelled.

    Confirm leaves the window open (live-1 F1, tests/screens/EnkephalinAssembled.png): a "Module Assembled 134 > 135"
    toast, the Enkephalin down, "Insufficient Enkephalin." where the prompt was and Confirm greyed. The drop read there
    decides the task and Cancel closes the window; the prompt back with nothing changed is a Confirm that did not take."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        a = TASK.setdefault("assemble", {"reads": 0, "confirms": 0})
        image = screen(context)
        if self.refused(context, a, image):
            return True
        if a.get("end"):
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        if "before" in a and (step := self.after_confirm(context, a, image)) is not None:
            return step
        tap(context, *MODULES_TAB, wait=0.7)
        image = screen(context)
        read = panel_read(context, image) if on_modules_tab(context, image) else []
        if not read:  # not the Modules tab, or not up yet
            a["reads"] += 1
            if a["reads"] < ASSEMBLE_TRIES:
                return True
            return cancel_stop(context, "the Charge Enkephalin window shows no Modules tab")
        a["reads"] = 0
        before, after = read[0][0], read[-1][0]
        if before < MODULE_COST:
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        for _ in range(ASSEMBLE_TRIES):  # >> goes to the most the Enkephalin allows; ask again until nothing changes
            if after < MODULE_COST:
                break
            tap(context, *ASSEMBLE_MAX, wait=0.5)
            image = screen(context)
            if self.refused(context, a, image):
                return True
            again = panel_read(context, image) if on_modules_tab(context, image) else []
            if not again:
                return cancel_stop(context, "the Modules tab did not read after >>: Confirm not pressed")
            if again[-1][0] == after:
                break
            after = again[-1][0]
        a["confirms"] += 1
        if a["confirms"] > ASSEMBLE_TRIES:
            return cancel_stop(context, f"Confirm did not take: Enkephalin still {before}")
        log(f"assemble: Enkephalin {before} -> {after}, Confirm")
        a["before"] = before
        tap(context, *PANEL_CONFIRM, wait=0.5)
        return True

    @staticmethod
    def refused(context, a, image):
        """Whether the game's refusal (too many Modules in storage) shows: it ends the task and back closes it."""
        if not too_many(context, image):
            return False
        a["end"] = "too many Enkephalin Modules in storage"
        back(context)
        return True

    @staticmethod
    def after_confirm(context, a, image):
        """The window after a Confirm (a["before"] set), what run() returns: the drop read sets a["end"] and Cancel closes
        the window (True); nothing read yet is looked at again (True) up to ASSEMBLE_TRIES times, then the stop procedure
        (False). None: the prompt shows again with the Enkephalin unchanged, a Confirm that did not take, for run() to
        press again."""
        read = panel_read(context, image)
        if read and read[0][0] < a["before"]:
            a["end"] = f"Enkephalin {a['before']} -> {read[0][0]}, assembled"
            log(f"assemble: {a['end']}")
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        if on_modules_tab(context, image):
            return None
        a["checks"] = a.get("checks", 0) + 1
        if a["checks"] < ASSEMBLE_TRIES:
            return True
        return cancel_stop(context, f"Enkephalin still {a['before']} after Confirm")


# Lunacy for Enkephalin (#373, pipeline/charge_enkephalin.json): the Charge Enkephalin window's Use Lunacy tab.
LUNACY_TAB = (639, 226)  # the Use Lunacy tab (live 720p, 2026-10-26); Confirm and Cancel are taken to sit where the Modules tab's do
CHARGE_TRIES = 3  # reads of the prompt and price, and Cancels over a decided task, the task spends before it gives up


@AgentServer.custom_action("ChargeStart")
class ChargeStart(TaskStart):
    """ChargeEnkephalin's entry: TaskStart, then charge_enkephalin.count, the day's target Daily Count (#429). 0, the
    default, ends the task at once, a success, before GoHome or any tap: the window is never opened, so the Use Lunacy
    tab is never touched."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        if not super().run(context, argv):
            return False
        try:
            count = load_settings(ROOT)["charge_enkephalin"]["count"]
        except SettingsError as e:
            return stop(context, str(e))
        TASK["charge"] = {"count": count, "reads": 0, "opened": 0, "charged": 0}
        return done("charge_enkephalin.count is 0: Lunacy left alone") if count == 0 else True


@AgentServer.custom_action("ChargeMain")
class ChargeMain(CustomAction):
    """The main window: the task's one way out and its way in. Done once the panel decided so; else the Enkephalin bar
    opens the window (once per charge and one more for the price that ends it, never more than the table has)."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        c = TASK["charge"]
        if c.get("end"):
            return done(c["end"])
        c["opened"] += 1
        if c["opened"] > lunacy.DAILY_MAX + 1:
            return stop(context, f"the Charge Enkephalin window opened {c['opened'] - 1} times, more than a day has charges")
        open_enkephalin(context)
        return True


@AgentServer.custom_action("ChargePanel")
class ChargePanel(CustomAction):
    """The Charge Enkephalin window: its Use Lunacy tab (it opens on Modules), which shows the price, the Daily Count and
    the Recharge prompt (live 2026-10-27). The price must be the table's at the Daily Count, and the count one up after
    each Confirm (lunacy.check); else Cancel, and the task ends (a success at the day's target, a failure when the
    screen is not what it should be). Use Boxes has the same prompt and no Daily Count: never confirmed. A tab that
    does not read before this run's first Confirm is not known to be short of the target: Cancel, a success with
    nothing charged (#429); after a Confirm it is the stop procedure. Only the tab, Confirm and Cancel are tapped."""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        c = TASK["charge"]
        if c.get("end"):  # a window over a task already decided; exempt from the same-screen watchdog, so bounded here
            c["cancels"] = c.get("cancels", 0) + 1
            if c["cancels"] > CHARGE_TRIES:
                return stop(context, f"the Charge Enkephalin window stayed open after {CHARGE_TRIES} more Cancels")
            tap(context, *PANEL_CANCEL, wait=0.5)
            return True
        tap(context, *LUNACY_TAB, wait=0.7)
        image = screen(context)
        prompt = context.run_recognition("ChargePrompt", image)
        price, used = None, None
        if prompt and prompt.hit:
            price = lunacy.read_price(ocr_texts(context, image, "ChargePrice"))
            used = lunacy.read_count(ocr_texts(context, image, "ChargeCount"))
        if used is None or (price is None and used < c["count"]):  # at the target the price is not needed
            c["reads"] += 1
            if c["reads"] < CHARGE_TRIES:
                return True
            tap(context, *PANEL_CANCEL, wait=0.5)
            unread = "the Use Lunacy tab's " + ("prompt and Daily Count" if used is None else f"price (Daily Count {used}/{lunacy.DAILY_MAX})")
            if c["charged"] == 0:
                c["end"] = f"{unread} did not read, target {c['count']}: nothing charged"
                log(f"charge: {c['end']}")
                return True
            return stop(context, f"{unread} could not be read after a Confirm")
        c["reads"] = 0
        verdict, why = lunacy.check(price, used, c["charged"], c["count"], c.get("expected"))
        log(f"charge: {why}")
        if verdict == lunacy.CHARGE:
            c["charged"] += 1
            c["expected"] = used + 1  # a Daily Count that stays is a Confirm that did nothing
            tap(context, *PANEL_CONFIRM, wait=1.0)
            return True
        tap(context, *PANEL_CANCEL, wait=0.5)
        if verdict == lunacy.DONE:
            c["end"] = why
            return True
        return stop(context, why)
