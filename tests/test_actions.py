"""Custom actions driven offline: a fake Maa context reads nothing on a blank screen."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import DEFAULT, MagicMock

import numpy as np
import pytest

from maa.define import Rect

import actions
import event_actions
import map_actions
import shop_actions
import shop
from settings import gift_tables
from test_settings import DEFAULT_SKILLS
from agent_patch import patch_all


REAL_GUARD = actions.page_guard


SCREENS = Path(__file__).resolve().parent / "screens"


@pytest.fixture
def clock(monkeypatch):
    """A fake clock that time.sleep moves on; returns the list of sleeps."""
    now, sleeps = [1000.0], []

    def sleep(s):
        sleeps.append(s)
        now[0] += s
    monkeypatch.setattr(actions.time, "sleep", sleep)
    monkeypatch.setattr(actions.time, "monotonic", lambda: now[0])
    return sleeps


@pytest.fixture
def context(clock, monkeypatch, tmp_path):
    # The action's page stays up: #118's guard is driven on its own (page_until).
    patch_all(monkeypatch, "ROOT", tmp_path)  # what the agent keeps under logs/ (a Cost miss's crop) stays out of the repo
    patch_all(monkeypatch, "page_guard", lambda context, home, image=None: actions.screen(context) if image is None else image)
    patch_all(monkeypatch, "FEATURE_MATCH", set())  # fakes read every roi in screen coordinates: no cut-outs
    ctx = MagicMock()
    ctx.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = np.zeros((720, 1280, 3), np.uint8)
    ctx.run_recognition.return_value = None  # OCR reads nothing, no node hits
    ctx.tasker.controller.post_shell.return_value.wait.return_value.get.return_value = ""  # focus not read
    ctx.tasker.stopping = False
    actions.RUN.clear()
    actions.RUN.update(settings={}, team={})  # a run plan in memory
    actions.STUCK["flag"] = None
    monkeypatch.setitem(actions.STUCK, "halted", None)  # no account-level stop this launch; a test's own is undone after
    yield ctx
    actions.RUN.clear()
    actions.STUCK["flag"] = None


def screens(context, values):
    """Each screenshot is a 720p image filled with the next value; the last one repeats."""
    images = [np.full((720, 1280, 3), v, np.uint8) for v in values]
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: images.pop(0) if len(images) > 1 else images[0]


class TimedGame:
    """A fake game for the waits that replaced a tap's fixed sleep (#258). `reads` is what each roi (a tuple) reads and
    `level` the screenshot's brightness. A tap at a point of `answers` takes that point's next answer: (lag, reads, level),
    which shows `lag` s after the tap, a list of them, or None for a tap the game loses. A tap sleeps its wait, as
    actions.tap does, so a fixed wait still costs its seconds. The taps are kept in order, their times in `at`, the
    game's start in `t0`."""

    def __init__(self, monkeypatch, context, reads, answers, level=10):
        self.reads, self.level, self.answers, self.taps, self.at, self.due = \
            dict(reads), level, {k: list(v) for k, v in answers.items()}, [], [], []
        self.t0 = actions.time.monotonic()
        patch_all(monkeypatch, "tap", self.tap)
        patch_all(monkeypatch, "text", lambda context, image, roi, only_rec=False: self.now().get(tuple(roi), ""))
        context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = self.shot

    def now(self):
        """The reads at the fake clock's now, every answer due by then shown."""
        t = actions.time.monotonic()
        for due in sorted((d for d in self.due if d[0] <= t), key=lambda d: d[0]):
            self.due.remove(due)
            self.reads.update(due[1])
            self.level = due[2]
        return self.reads

    def shot(self):
        self.now()
        return np.full((720, 1280, 3), self.level, np.uint8)

    def tap(self, context, x, y, wait=1.0):
        self.taps.append((x, y))
        self.at.append(actions.time.monotonic())
        queue = self.answers.get((x, y))
        if queue and (answer := queue.pop(0)) is not None:
            self.shows(*(answer if isinstance(answer, list) else [answer]))
        actions.time.sleep(wait)

    def shows(self, *changes):
        """Each (lag, reads, level) shows lag s from now, with no tap."""
        self.due += [(actions.time.monotonic() + lag, reads, level) for lag, reads, level in changes]


def test_until_returns_the_first_screen_that_shows_the_change(context, clock):
    screens(context, [0, 0, 9, 0])
    image = actions.until(context, lambda im: im[0, 0, 0] == 9, timeout=3)
    assert image[0, 0, 0] == 9
    assert sum(clock) < 1  # polled, not a fixed wait


def test_until_gives_up_after_its_timeout(context, clock):
    screens(context, [0])
    assert actions.until(context, lambda im: False, timeout=2) is None
    assert 2 <= sum(clock) < 2.5


def test_until_waits_its_minimum_before_the_first_look(context, clock):
    screens(context, [9])
    actions.until(context, lambda im: True, timeout=2, least=0.6)
    assert sum(clock) == pytest.approx(0.6)


def test_still_waits_out_a_fade(context, clock):
    screens(context, [0, 40, 80, 120, 120])  # fading in, then still
    image = actions.still(context)
    assert image[0, 0, 0] == 120
    assert context.tasker.controller.post_screencap.call_count == 5


def test_still_wants_its_runs_of_alike_screenshots_in_a_row(context, clock):
    # #246: a swinging card looks alike 0.1 s either side of its turn, so one alike pair is not still yet.
    screens(context, [0, 40, 40, 80, 80, 80])
    assert actions.still(context, runs=2)[0, 0, 0] == 80


def event_text(context, choices_from=None, red_from=None, red_to=float("inf"), label_to=float("inf"), skip_to=0, misread=()):
    """Event text running on: screenshot n (1 = Event.run's own, its still() taking two) shows the Choices from
    choices_from on, the lit button from red_from on until red_to and the button's label until label_to (SKIP until
    skip_to, then Continue, read "Contnue" on the screenshots in misread); returns the rois OCR read, in order."""
    shots, reads = [], []

    def screencap():
        shots.append(1)
        n = max(1, len(shots) - 1)
        image = np.zeros((720, 1280, 3), np.uint8)
        image[0, 0, 0] = n
        if red_from and red_from <= n < red_to:
            image[640:650, 1080:1180] = (0, 0, 200)
        return image
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = screencap

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        reads.append(roi)
        if roi == tuple(event_actions.CHOICES_HEADER) and choices_from and image[0, 0, 0] >= choices_from:
            return SimpleNamespace(all_results=[SimpleNamespace(text="Choices", box=(700, 110, 100, 30))])
        if roi == tuple(event_actions.EVENT_BUTTON_LABEL) and image[0, 0, 0] < label_to:
            label = "SKIP" if image[0, 0, 0] < skip_to else "Contnue" if image[0, 0, 0] in misread else "Continue"
            return SimpleNamespace(all_results=[SimpleNamespace(text=label, box=(1065, 625, 140, 40))])
        return None
    context.run_recognition.side_effect = run_recognition
    return reads


def corner_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == event_actions.EVENT_NEUTRAL]


def button_taps(context):
    return [c for c in context.tasker.controller.post_click.call_args_list if c.args == event_actions.EVENT_BUTTON]


def map_world(context, nodes, links, bus_x, width=1800):
    """A map wider than the screen, the bus at (bus_x, BUS_HOME's y) on screen; drags move the screen over it.

    nodes: {(column, row): marks}, column 1 next to the bus; links: ((column, row), (column, row)) pairs.
    The bus's chevrons lead to the first column's nodes; a tap on anything but Enter opens a node panel.
    The bus stands on a node already entered (no tap on it first, #88). Returns the screen's offsets after each drag.
    """
    actions.RUN["map_entered"] = True
    bx, by = 446, map_actions.BUS_HOME[1]  # on the map; the screen starts at 446 - bus_x

    def at(column, row):
        return bx + map_actions.SLOT[0] + (column - 1) * 255, by + map_actions.SLOT[1] + {"up": -213, "mid": 0, "down": 213}[row]
    world = np.random.default_rng(2).integers(0, 30, size=(720, width, 3)).astype(np.uint8)
    for a, b in links:
        (x0, y0), (x1, y1) = at(*a), at(*b)
        for t in np.linspace(0, 1, 600):
            x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
            world[y - 2:y + 3, x - 2:x + 3] = 200
    off, start, offsets = [bx - bus_x], [], []  # the screen's left edge on the map; where the touch went down

    def down(x, y):
        start[:] = [x, off[0]]
        return MagicMock()

    def move(x, y):
        off[0] = min(max(0, start[1] + start[0] - x), width - 1280)
        return MagicMock()

    def up():
        offsets.append(off[0])
        return MagicMock()
    ctl = context.tasker.controller
    ctl.post_touch_down.side_effect, ctl.post_touch_move.side_effect, ctl.post_touch_up.side_effect = down, move, up
    ctl.post_screencap.return_value.wait.return_value.get.side_effect = lambda: world[:, off[0]:off[0] + 1280].copy()
    marks = {(at(c, r)[0], at(c, r)[1], m) for (c, r), ms in nodes.items() for m in ms}

    def run_recognition(name, image, override=None):
        if name == "MapBus":
            return SimpleNamespace(hit=True, box=[bx - off[0], by, 45, 75])
        if name in ("MapLinkUp", "MapLinkMid", "MapLinkDown"):
            return SimpleNamespace(hit=True) if (1, name[7:].lower()) in nodes else None
        if name == "MapNodePanel":
            taps = ctl.post_click.call_args_list
            return SimpleNamespace(hit=True) if taps and taps[-1].args != map_actions.ENTER else None
        if name in map_actions.MARKS:
            mark, (ox, oy, _, _) = map_actions.MARKS[name]
            x, y = override[name]["roi"][:2]
            return SimpleNamespace(hit=True, box=[x, y, 26, 24]) if (x - ox + off[0], y - oy, mark) in marks else None
        return None
    context.run_recognition.side_effect = run_recognition
    return offsets


def hits(context, *shown):
    """The nodes in shown hit on every screen; the others miss."""
    context.run_recognition.side_effect = lambda name, image, override=None: (
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name in shown else None)


def reads(context, texts):
    """OCR reads texts[roi] (a list of (text, box)) in that roi, nothing elsewhere; no other node hits."""
    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in texts.get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition


def owned_gifts(context, cells=shop_actions.FUSE_CELLS):
    """Screenshots whose cells hold a gift (a textured square); the rest stay flat."""
    image = np.zeros((720, 1280, 3), np.uint8)
    for x, y in cells:
        image[y - 30:y + 30, x - 30:x + 30] = np.random.default_rng(0).integers(0, 255, (60, 60, 3), np.uint8)
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.return_value = image


def cells_read(monkeypatch, *readings):
    """read_cells reads the first cells of any grid as readings [(keyword[, tier[, gift id]])], tier 2 and no id
    by default (test_shop_cells checks the reading itself on live captures)."""
    grid_read(monkeypatch, list(readings))


def grid_read(monkeypatch, readings):
    """cells_read over the list readings as it is at each read: fuse_page's, which a fusion changes."""
    places = {}

    def read_cells(context, image, cells, page):
        # A grid's cells that read unknown are read again (read_clear): the same cells, a subset of the first read's.
        if not all(c in places for c in cells):
            places.clear()
            places.update({c: j for j, c in enumerate(cells)})
        return [{"i": i, "x": x, "y": y, "tier": t[0] if t else 2, "keyword": k,
                 "id": t[1] if len(t) > 1 else None, "score": 0.9 if len(t) > 1 else 0.0}
                for i, (x, y) in enumerate(cells) if places[(x, y)] < len(readings)
                for k, *t in [readings[places[(x, y)]]]]
    patch_all(monkeypatch, "read_cells", read_cells)


FUSE_PAGE = {tuple(shop_actions.DIALOG_TITLE): [("Fuse E.G.O Gift", (500, 100, 200, 40))],
             tuple(shop_actions.KEYWORD_LABELS): [("Burn", (300, 400, 60, 20))],
             tuple(shop_actions.FUSE_LIST): [("E.G.O Gifts Owned", (635, 216, 161, 24))]}  # at its place: nothing over it


# The fuse page whose fusions go through: its dialog counts 3/3, its GET! shows (fuse_page: once a fusion is confirmed).
FUSING = FUSE_PAGE | {tuple(shop_actions.FUSE_CONFIRM): [("Selected E.G.O Gifts 3/3", (330, 175, 320, 30))],
                      tuple(actions.GET_TITLE): [("E.G.O Gift GET!", (560, 165, 160, 30))]}


def after_last(tapped, at):
    """The taps of `tapped` after the last one at `at`; all of them when none was."""
    return tapped[max((k + 1 for k, t in enumerate(tapped) if t == at), default=0):]


def in_slots(tapped, ignored=()):
    """The cells (FUSE_CELLS) whose gift is in the fuse page's slots after the taps `tapped`: each tapped an odd number of
    times since the last fusion confirmed (the dialog's Confirm empties the slots), a cell in ignored never."""
    since = after_last(tapped, shop_actions.FUSE_DIALOG_CONFIRM)
    return {c for c in shop_actions.FUSE_CELLS if c not in ignored and since.count(c) % 2}


def fuse_slots(context, monkeypatch, slots=3, ignored=()):
    """The fuse page's read-back (shop.fuse_slots, placed, picked; test_shop checks them on live captures) as the
    game would show it: a tap on a cell puts its gift in or takes it out, but not on a cell in ignored (in_slots)."""
    monkeypatch.setattr(shop, "fuse_slots", lambda image: slots)
    monkeypatch.setattr(shop, "placed", lambda image, n: len(in_slots(taps(context), ignored)))
    monkeypatch.setattr(shop, "picked", lambda image, x, y, bottom=720: (x, y) in in_slots(taps(context), ignored))


def fuse_page(context, monkeypatch, *readings, slots=3, ignored=()):
    """fuse_slots over a grid whose first cells hold readings (cells_read), changed by a fusion as the game does (#378):
    the dialog's Confirm takes the gifts in out of the grid, the rest moving up a cell each (the fused gift is left out:
    an unknown gift stays out of every fusion), and the GET! popup OCR reads shows from that Confirm until its own is
    tapped. Call it after reads()."""
    fuse_slots(context, monkeypatch, slots, ignored)
    grid = list(readings)
    grid_read(monkeypatch, grid)

    def click(x, y):
        if (x, y) == shop_actions.FUSE_DIALOG_CONFIRM:  # recorded already: the slots as they were before it
            gone = {shop_actions.FUSE_CELLS.index(c) for c in in_slots(taps(context)[:-1], ignored)}
            grid[:] = [r for k, r in enumerate(grid) if k not in gone]
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click
    shown = context.run_recognition.side_effect

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        tapped = taps(context)
        if roi == tuple(actions.GET_TITLE) and (shop_actions.FUSE_DIALOG_CONFIRM not in tapped
                                                 or actions.GET_CONFIRM in after_last(tapped, shop_actions.FUSE_DIALOG_CONFIRM)):
            return None
        return shown(name, image, override)
    context.run_recognition.side_effect = run_recognition


ORDER = ["Burn", "Bleed", "Tremor", "Rupture", "Sinking", "Poise", "Charge", "Slash", "Pierce", "Blunt", "Keywordless"]


def wants(*ids, order=("Burn", "Bleed"), keep=(), condition="any"):
    """A gift list wanting ids, bought in this order (all under the first keyword of `order` that lists them), keeping `keep`;
    everything else it drops. Fusions (ids the shop does not sell) are wanted, not bought."""
    gorder = {k: [] for k in ORDER}
    for i in ids:
        for g in gift_tables()[0]:
            if g["id"] == i:
                gorder[g["keyword"]].append(i)
    return {"order": [*order, *(k for k in ORDER if k not in order)], "want": list(ids), "keep": list(keep), "gorder": gorder,
            "fusion_condition": condition}


def replacing(*entries):
    """A team's skill_replacement listing entries (test_shop.skill_entry), else the settings' default: no sinner listed, so
    the shop taps no replacement slot (#455)."""
    return {**json.loads(json.dumps(DEFAULT_SKILLS)), "sinners": list(entries)}


def shop_team(team):
    """The team Shop.sell and Shop.fuse get (run_team's): its list drops everything, fusing under `fusion_condition`, unless
    `list` says (then its own condition counts); no skill replacement unless `skill_replacement` says."""
    team = dict(team)
    condition = team.pop("fusion_condition", None) or "any"
    return {"keyword": "Burn", "reserve_cost": 0, "list": wants(condition=condition), "skill_replacement": replacing(), **team}


UNLISTED = 800000  # a cell given no id reads as UNLISTED + its place: an id no gift list mentions


def with_ids(readings):
    """readings (keyword, tier, id) all, tier 2 by default: a cell given no id gets one no list mentions, so the list drops it;
    a cell whose badge is unread (keyword None) has none, as read_cells gives it; an id given as None stays None (unknown)."""
    def one(n, k, tier=2, gift_id=...):
        return (k, tier, (None if k is None else UNLISTED + n) if gift_id is ... else gift_id)
    return [one(n, *r) for n, r in enumerate(readings)]


def buying(list_, **team):
    """A team that plays gift list `list_` (run_team puts it in the team), reserve 0, no shop refresh, no skill replacement."""
    return shop_team({"list": list_, "shop_refresh_keyword": 0, "shop_refresh_normal": 0, **team})


def sale_taps(context, monkeypatch, team, prices, *readings, slots=None):
    """Shop.sell with 100 Cost and a 180 wanted, readings (cells_read) priced prices on the grid: the cells it tapped.
    A cell tapped is picked: the Cost previews a sale (#174), read as 100 followed by more digits."""
    lines = [(str(p), (x - 3, y + 37, 26, 20)) for p, (x, y) in zip(prices, shop_actions.SELL_CELLS)]
    clicks = context.tasker.controller.post_click.call_args_list
    texts = {tuple(shop_actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))], tuple(shop_actions.SELL_GRID): lines}
    reads(context, texts)
    shown = context.run_recognition.side_effect

    def run_recognition(name, image, override=None):
        picked = any(c.args in shop_actions.SELL_CELLS for c in clicks)
        texts[tuple(shop_actions.SELL_COST)] = [("100190" if picked else "100", (980, 90, 60, 30))]
        return shown(name, image, override)
    context.run_recognition.side_effect = run_recognition
    cells_read(monkeypatch, *with_ids(readings))
    shop_actions.Shop.sell(context, shop_team(team), {"wanted": 180, "sold": False, **({"slots": slots} if slots else {})})
    return [c.args for c in context.tasker.controller.post_click.call_args_list if c.args in shop_actions.SELL_CELLS]


def live_shop(context, reads_now):
    """A game that reacts to taps: each tap changes the screen, and OCR reads reads_now(taps)[roi]."""
    taps = []

    def click(x, y):
        taps.append((x, y))
        return MagicMock()
    context.tasker.controller.post_click.side_effect = click
    context.tasker.controller.post_screencap.return_value.wait.return_value.get.side_effect = \
        lambda: np.full((720, 1280, 3), len(taps) * 20 % 256, np.uint8)

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        results = [SimpleNamespace(text=t, box=b) for t, b in reads_now(taps).get(roi, [])]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None
    context.run_recognition.side_effect = run_recognition
    return taps


def sell_page(confirmed):
    """The sell page of #174: 51 Cost, cell 0 a Bleed gift for 95; a picked cell previews the Cost as 51146.
    Sell asks to confirm; confirmed(taps) says whether the sale went through."""
    def reads_now(taps):
        sold = confirmed(taps)
        picked = shop_actions.SELL_CELLS[0] in taps and not sold
        asked = taps[-1:] == [shop_actions.PAGE_OK]
        return {tuple(shop_actions.DIALOG_TITLE): [("Sell E.G.O Gift", (500, 90, 200, 40))],
                tuple(shop_actions.SELL_COST): [("146" if sold else "51146" if picked else "51", (980, 90, 60, 30))],
                tuple(shop_actions.SELL_GRID): [] if sold else [("95", (680, 295, 26, 20))],
                tuple(actions.DIALOG_TEXT): [("Sell [Today's Expression] for 95 Cost?", (460, 330, 360, 25))] if asked else []}
    return reads_now


SELLER = shop_team({})


NO_GOSSYPIUM = {"keyword": "Bleed", "reserve_cost": 0, "allow_white_gossypium": False,
                "list": wants(9020, 9005, order=("Bleed",))}


def gift_page(context, monkeypatch, names, slots=1):
    """A gift choice page with a Bleed card per name, Select 0/`slots`."""
    taps = []
    patch_all(monkeypatch, "tap", lambda context, x, y, wait=1.0: taps.append((x, y)))

    def ocr(context, image, roi, only_rec=False):
        if roi == event_actions.GIFT_CARDS:
            return [r for i, n in enumerate(names) for r in
                    [("Acquire E.G.O Gift", (200 + 300 * i, 160, 150, 20)), (n, (210 + 300 * i, 250, 150, 20)),
                     ("Inflict Bleed", (210 + 300 * i, 300, 150, 20))]]
        picked = any(y == 300 for _, y in taps)
        selected = event_actions.GIFT_SELECT in taps
        if roi == event_actions.GIFT_COUNT:
            return [(f"Select {min(slots, sum(y == 300 for _, y in taps))}/{slots}", (1080, 565, 100, 30))]
        if roi == event_actions.REFUSE_GIFT and not (selected and picked):
            return [("Refuse Gift", (900, 570, 100, 25))]
        return []
    patch_all(monkeypatch, "ocr", ocr)
    actions.RUN.update(settings={"trial_risk_overrides": []}, team={**NO_GOSSYPIUM})
    return taps


def picked(taps):
    return [x for x, y in taps if y == 300]


@pytest.mark.parametrize("visit, before, held", [({"owned": [9249]}, [9001], [9249]), ({"bought": [9249]}, [9001], [9001, 9249]), (None, [9001], [9001])])
def test_a_shop_visit_that_ends_leaves_the_run_holding_what_it_counted_as_owned(visit, before, held):
    actions.RUN["owned"] = before
    if visit is not None:
        actions.RUN["shop"] = visit
    actions.leave_shop()
    assert actions.RUN["owned"] == held and "shop" not in actions.RUN


def fusion_taps(context, monkeypatch, team, *readings, slots=3, ignored=(), confirm=3):
    """Shop.fuse on readings (with_ids) of fuse_page; (its result, how often each cell was tapped, whether Fuse was
    pressed). The confirm dialog reads "confirm/slots"."""
    reads(context, FUSING | {tuple(shop_actions.FUSE_CONFIRM): [(f"Selected E.G.O Gifts {confirm}/{slots}", (330, 175, 320, 30))]})
    fuse_page(context, monkeypatch, *with_ids(readings), slots=slots, ignored=ignored)
    fused = shop_actions.Shop.fuse(context, shop_team(team), {})
    taps = [c.args for c in context.tasker.controller.post_click.call_args_list]
    return fused, [taps.count(c) for c in shop_actions.FUSE_CELLS[:len(readings)]], shop_actions.PAGE_OK in taps


def lost_tap_fuse_page(context, monkeypatch):
    """A fuse page of three materials whose second one's tap puts nothing in."""
    reads(context, FUSE_PAGE)
    fuse_slots(context, monkeypatch, ignored=[shop_actions.FUSE_CELLS[1]])
    cells_read(monkeypatch, *with_ids([("Bleed",), ("Tremor",), ("Pierce",)]))


def test_recover_waits_out_a_download_without_climbing(context, clock, monkeypatch, tmp_path):
    # MirrorHub's own 60 s timeout lands in Recover while the download shows nothing it knows.
    patch_all(monkeypatch, "ROOT", tmp_path)
    actions.STUCK["watch"].reset()
    actions.STUCK["watch"].hold(actions.time.monotonic(), 1800)
    before = dict(actions.STUCK["ladder"].counts)
    assert actions.Recover().run(context, None)
    assert actions.STUCK["ladder"].counts == before
    context.run_task.assert_not_called()
    actions.STUCK["watch"].reset()


def test_recover_keeps_the_screen_when_the_hub_recognised_nothing(context, clock, monkeypatch, tmp_path):
    patch_all(monkeypatch, "ROOT", tmp_path)
    actions.STUCK["flag"] = None
    actions.STUCK["watch"].reset()
    actions.Recover().run(context, None)
    assert len(list((tmp_path / "logs" / "unknown").glob("*.png"))) == 1
    actions.STUCK["ladder"].__init__()


# The run's opening (#115): every wait is a look at the next page, never a fixed delay.
def page(context, rules):
    """OCR reads rules[roi] there and nothing elsewhere. A rule is a text, [(text, box)], or f(clicks, looks) -> either or None."""
    clicks = context.tasker.controller.post_click
    shots = context.tasker.controller.post_screencap.return_value.wait.return_value.get

    def run_recognition(name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        rule = rules.get(roi)
        rule = rule(clicks.call_count, shots.call_count) if callable(rule) else rule
        if not rule:
            return None
        results = [SimpleNamespace(text=rule, box=roi)] if isinstance(rule, str) else [SimpleNamespace(text=t, box=b) for t, b in rule]
        return SimpleNamespace(all_results=results, hit=True, best_result=None)
    context.run_recognition.side_effect = run_recognition


def argv(param=None, node="Node"):
    return SimpleNamespace(custom_action_param=json.dumps(param), node_name=node, box=[0, 0, 1, 1])


def no_fixed_wait(clock):
    assert max(clock, default=0) <= 0.25, clock  # only until()'s 0.2 s looks


def taps(context):
    return [c.args for c in context.tasker.controller.post_click.call_args_list]


def test_tap_until_taps_the_target_and_waits_for_the_page_that_follows(context, clock):
    page(context, {(10, 20, 30, 40): lambda clicks, looks: "Next Page" if looks >= 3 else None})
    param = {"target": [100, 200, 40, 20], "next": {"roi": [10, 20, 30, 40], "expected": "^Next"}}
    assert actions.TapUntil().run(context, argv(param))
    assert taps(context) == [(120, 210)]
    assert context.tasker.controller.post_screencap.call_count == 3
    no_fixed_wait(clock)


def test_tap_until_takes_any_of_several_next_pages(context, clock):
    page(context, {(1, 1, 10, 10): "Resume"})
    param = {"target": [100, 200, 40, 20], "next": [{"roi": [10, 20, 30, 40], "expected": "^TEAMS$"}, {"roi": [1, 1, 10, 10], "expected": "Resume"}]}
    assert actions.TapUntil().run(context, argv(param))
    no_fixed_wait(clock)
    assert sum(clock) == 0


def test_tap_until_gives_up_after_its_timeout_and_leaves_the_page_to_the_hub(context, clock):
    page(context, {})
    param = {"target": [100, 200, 40, 20], "next": {"roi": [10, 20, 30, 40], "expected": "Next"}, "timeout": 2}
    assert actions.TapUntil().run(context, argv(param))
    assert 2 <= sum(clock) < 2.5


CLOSING = {"roi": [600, 440, 80, 35], "expected": "^Continue$"}


def test_tap_until_gone_waits_for_the_text_the_tap_closes_to_go(context, clock):
    # #254: a dialog fades out for a while with its text still readable; the hub would press it again.
    page(context, {(600, 440, 80, 35): lambda clicks, looks: "Continue" if looks < 4 else None})
    param = {"target": [600, 440, 80, 35], "gone": CLOSING}
    assert actions.TapUntil().run(context, argv(param))
    assert taps(context) == [(640, 457)]
    assert context.tasker.controller.post_screencap.call_count == 4  # one before the tap, then until()'s looks
    no_fixed_wait(clock)


def test_tap_until_gone_counts_the_next_popup_in_the_same_place_as_gone(context, clock):
    # ClaimPopup: Rewards Acquired is followed by Pass Level Up in the same roi, both matching the node's expected.
    roi, both = [500, 225, 280, 50], "Rewards Acquired|Pass Level Up"
    page(context, {tuple(roi): lambda clicks, looks: "Rewards Acquired" if looks < 3 else "Pass Level Up"})
    assert actions.TapUntil().run(context, argv({"target": [575, 455, 130, 35], "gone": {"roi": roi, "expected": both}}))
    assert context.tasker.controller.post_screencap.call_count == 3
    no_fixed_wait(clock)


def test_tap_until_gone_has_nothing_to_wait_for_when_the_text_is_already_gone(context, clock):
    page(context, {})
    assert actions.TapUntil().run(context, argv({"target": [600, 440, 80, 35], "gone": CLOSING}))
    assert taps(context) == [(640, 457)]
    assert context.tasker.controller.post_screencap.call_count == 2  # the look before the tap, the one after it
    assert sum(clock) == 0


def test_tap_until_gone_gives_up_after_its_timeout(context, clock):
    page(context, {(600, 440, 80, 35): "Continue"})
    assert actions.TapUntil().run(context, argv({"target": [600, 440, 80, 35], "gone": CLOSING, "timeout": 2}))
    assert 2 <= sum(clock) < 2.5


def test_tap_until_left_taps_the_nodes_box_and_waits_until_the_node_misses(context, clock):
    # A template node's page (the unlit Window tab, a Luxcavation tab): the node's own recognition missing is the page
    # left; the hub would tap it again before that.
    page(context, {(): lambda clicks, looks: "hit" if not clicks or looks < 4 else None})  # the node, no roi override
    run = SimpleNamespace(custom_action_param=json.dumps({"left": True}), node_name="HomeWindowTab", box=[800, 620, 50, 40])
    assert actions.TapUntil().run(context, run)
    assert taps(context) == [(825, 640)]
    assert context.run_recognition.call_args.args[0] == "HomeWindowTab"
    assert "HomeWindowTab: screen changed after" in actions.LOG[-1]
    no_fixed_wait(clock)


def test_tap_until_logs_how_long_the_screen_took(context, clock):
    # #254: the live run reads the wait from the log; the fixed delay it replaces was never measured.
    page(context, {(600, 440, 80, 35): lambda clicks, looks: "Continue" if looks < 4 else None})
    actions.TapUntil().run(context, argv({"target": [600, 440, 80, 35], "gone": CLOSING}, node="ProgressPanel"))
    assert "ProgressPanel: screen changed after 0.4 s" in actions.LOG[-1]


def listed(*first):
    """Settings with a team on gift list "g" whose order starts with first, the other keywords after them."""
    order = [*first, *(k for k in ORDER if k not in first)]
    team = {"id": "a", "name": "t", "enabled": True, "usage": "any", "game_team": 1, "guard_turns": 0, "hard_from_floor": 1, "gift_list": "g",
            "skill_replacement": replacing()}
    return {"run": {}, "teams": [team], "gift_lists": [{"id": "g", "name": "G", "order": order}]}


@pytest.mark.parametrize(("first", "main"), [(("Bleed",), "Bleed"), (("Keywordless", "Pierce"), "Pierce"), ((), "Burn")])
def test_the_main_keyword_is_the_first_keyword_of_the_teams_list(first, main):
    # #305: the team has no keyword of its own; Keywordless is never the main one.
    settings = listed(*first)
    assert actions.run_team(settings, settings["teams"][0])["keyword"] == main


def test_the_default_list_makes_burn_the_main_keyword():
    team = {"gift_list": "default"}
    assert actions.run_team({"gift_lists": []}, team)["keyword"] == "Burn"


def check_page(context, odds=()):
    """The skill-check page: `Choose a character`, and the odds caption (x -> text) over each portrait."""
    texts = {tuple(event_actions.CHECK_PROMPT): [("Choose a character", (860, 300, 200, 30))]}
    for x, t in odds:
        texts[(x - 38, 605, 76, 24)] = [(t, (x - 30, 608, 60, 20))]
    reads(context, texts)


def event_portrait_taps(context):
    return [c.args[0] for c in context.tasker.controller.post_click.call_args_list if c.args[1] == event_actions.EVENT_PORTRAIT_Y]


class Choices:
    """An event's choice page: option cards 130 px tall, 18 apart from y 170, in the list's view y 165-512;
    more than fit show a scrollbar and scroll() moves them. options are (text, hint); OCR reads a line only
    where it shows whole. tapped: the option each tap hit, None when its card was not whole in view.
    The card a drag lifts over lights up (live #196): an orange glow under its bottom edge, 13 px in all."""

    def __init__(self, context, monkeypatch, options, story=(), offset=0, scrollbar=True):
        self.options, self.story, self.offset, self.drags, self.tapped = options, story, offset, [], []
        self.lit = None  # y the last drag lifted at
        self.end = max(0, 170 + 148 * len(options) - 18 - 508)
        self.scrollbar = scrollbar and self.end > 0
        ctl = context.tasker.controller
        ctl.post_screencap.return_value.wait.return_value.get.side_effect = self.render
        ctl.post_click.side_effect = self.click
        context.run_recognition.side_effect = self.read
        patch_all(monkeypatch, "scroll", self.scroll)

    def scroll(self, context, x, y, dx, dy):
        assert 690 < x < 1165 and 165 < y < 512 and 165 < y + dy < 512  # on the list
        self.drags.append(dy)
        self.offset = min(max(self.offset - dy, 0), self.end)
        self.lit = y + dy

    def tops(self):
        return [170 + 148 * k - self.offset for k in range(len(self.options))]

    def click(self, x, y):
        if 690 < x < 1165:
            whole = [k for k, t in enumerate(self.tops()) if 165 <= t and t + 130 <= 512 and t < y < t + 130]
            self.tapped.append(self.options[whole[0]][0] if whole else None)
        return DEFAULT

    def render(self):
        image = np.zeros((720, 1280, 3), np.uint8)
        for t in self.tops():
            image[max(t, 165):max(min(t + 130, 512), 165), 700:1160] = (20, 30, 60)  # red-brown: open
            glow = 10 if self.lit is not None and t < self.lit < t + 130 else 0
            for y in [*range(t, t + 9), *range(t + 127, t + 130 + glow)]:  # top edge double, bottom edge single
                if 165 <= y < 512:
                    image[y, 690:1165] = 200
        if self.scrollbar:
            image[170:505, 1203:1213] = (26, 41, 60)
        return image

    def read(self, name, image, override=None):
        roi = tuple((override or {}).get(name, {}).get("roi", ()))
        lines = []
        if roi == tuple(event_actions.CHOICES_HEADER):
            lines = [("Choices", (700, 110, 100, 30))]
        elif roi == tuple(event_actions.EVENT_STORY):
            lines = [(t, (80, 340 + 30 * i, 400, 20)) for i, t in enumerate(self.story)]
        elif roi == tuple(event_actions.CHOICE_ROWS):
            for t, (text, hint) in zip(self.tops(), self.options):
                lines += [(s, (733, y, 300, 20)) for s, y in ((text, t + 30), (hint, t + 60)) if s and 165 <= y and y + 20 <= 512]
        results = [SimpleNamespace(text=t, box=b) for t, b in lines]
        return SimpleNamespace(all_results=results, hit=True, best_result=None) if results else None


DOLL = ["In this cramped room, you find a wooden doll, standing.", "Are the talismans filling the room for a wish?",
        "Does this wooden doll wish for anything?"]  # 901013's story, as the box ends it


SCROLLED = [(f"Option {k}.", "") for k in range(5)]


TABLE = [{"key": "doesthiswoodendollwishforanything",
          "options": [{"text": t, "hint": h, "kind": "other"} for t, h in SCROLLED]}]


def gesture(context, clock):
    """Record the touch events with the fake clock's time: [(kind, (x, y), t)]."""
    events = []
    ctl = context.tasker.controller
    for kind in ("down", "move", "up"):
        def record(*a, kind=kind):
            events.append((kind, a[:2], sum(clock)))
            return DEFAULT
        getattr(ctl, f"post_touch_{kind}").side_effect = record
    return events


def test_a_scroll_stops_dead_where_it_was_sent(context, clock):
    # #114 (live 2026-10-18): the game eats the first move (its drag threshold) and flings the content on with
    # what speed the finger still had at the lift, decaying while the finger rests: 0.55 s still after 20 px moves
    # 10 ms apart left at most 1 px over 126 drags; resting after the threshold move keeps the next one whole.
    events = gesture(context, clock)
    actions.scroll(context, 430, 590, 0, -300)
    moves = [(xy, t) for kind, xy, t in events if kind == "move"]
    assert moves[0][0] == (430, 580)  # 10 px: what the threshold eats
    assert moves[-1][0] == (430, 280)  # then the 300 px asked for
    assert moves[1][1] - moves[0][1] >= 0.05
    assert events[-1][0] == "up" and events[-1][2] - moves[-1][1] >= 0.55
    assert events[-1][2] - events[0][2] < 0.9  # live: 0.77 s for 300 px, 1.25 s before


# #118: an action checks its page before each tap and hands a changed screen back to MirrorHub.
@pytest.fixture
def guarded(monkeypatch):
    patch_all(monkeypatch, "page_guard", REAL_GUARD)


def page_until(context, node, clicks):
    """MirrorHub's node for the page hits until `clicks` taps went out, then the page is gone (left by hand)."""
    inner = context.run_recognition.side_effect

    def run_recognition(name, image, override=None):
        if name == node and override is None:
            return SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if context.tasker.controller.post_click.call_count < clicks else None
        return inner(name, image, override) if inner else None
    context.run_recognition.side_effect = run_recognition


def test_the_guard_passes_the_page_and_waits_out_a_moment_without_its_anchor(context, clock, guarded):
    shown = iter([None, None, True])
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True) if name == "Shop" and next(shown, True) else None
    assert actions.page_guard(context, "Shop") is not None
    assert sum(clock) < 1


def test_the_guard_gives_the_page_up_after_a_second(context, clock, guarded):
    with pytest.raises(actions.PageGone):
        actions.page_guard(context, "Shop")
    assert 1 <= sum(clock) < 1.5


def test_the_guard_takes_a_fresh_screenshot_showing_the_page_without_another(context, guarded):
    page_until(context, "Event", 1)
    image = np.zeros((720, 1280, 3), np.uint8)
    assert actions.page_guard(context, "Event", image=image) is image
    assert context.tasker.controller.post_screencap.call_count == 0


def test_a_feature_match_hit_comes_back_in_screen_coordinates():
    # #156: the node runs on a cut-out around its roi; its box is put back where it is on the screen.
    ctx, calls = MagicMock(), []

    def recognise(node, image, override):
        calls.append((image.shape, override[node]["roi"]))
        return SimpleNamespace(hit=True, box=Rect(10, 20, 30, 40))
    ctx.run_recognition.side_effect = recognise
    hit = actions.seen(ctx, np.zeros((720, 1280, 3), np.uint8), "MapNodeEvent", [500, 300, 120, 120])
    (h, w, _), roi = calls[0]
    assert w < 1280 and h < 720 and roi[2:] == [120, 120]  # a cut-out, the roi's size kept
    dx, dy = 500 - roi[0], 300 - roi[1]
    assert dx % actions.FEATURE_ALIGN == 0 and dy % actions.FEATURE_ALIGN == 0
    assert tuple(hit.box) == (10 + dx, 20 + dy, 30, 40)


def test_feature_match_lists_every_feature_match_node_of_the_pipeline():
    from test_pipeline import load_nodes, recognition
    assert actions.FEATURE_MATCH == {n for n, spec in load_nodes().items() if recognition(spec)[0] == "FeatureMatch"}


def moved(context):
    """Taps, drags and swipes sent to the device."""
    ctl = context.tasker.controller
    return ctl.post_click.call_count + ctl.post_touch_down.call_count + ctl.post_swipe.call_count


def test_a_global_popup_over_the_page_hands_it_back(context, guarded):
    # A popup reads through to the page under it (maatools: the title's nodes hit under RetryCountdown.png);
    # MirrorHub answers the popup before any page, so the guard does too.
    context.run_recognition.side_effect = lambda name, image, override=None: \
        SimpleNamespace(hit=True, box=[0, 0, 1, 1]) if name in ("Shop", "RetryPopup") else None
    with pytest.raises(actions.PageGone):
        actions.page_guard(context, "Shop")


def test_hands_back_leaves_the_runtime_cache_of_a_long_task_alone():
    """G1: a clear_cache drops the runner ids of the tasks queued after this one, so their wait() returns at once. The
    MaaFramework fork (MAAFW_FIX in tools/install.py) keeps only a task's last 200 node details itself (MaaXYZ/MaaFramework#1578)."""
    class Act:
        @actions.hands_back
        def run(self, context, argv):
            if argv.gone:
                raise actions.PageGone("the map")
            return True

    context = MagicMock()
    for gone in (False, True):
        assert Act().run(context, SimpleNamespace(task_detail=SimpleNamespace(node_id_list=list(range(5000))), gone=gone))
    context.tasker.clear_cache.assert_not_called()
