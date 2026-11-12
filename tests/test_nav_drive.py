"""NavDrive (#58): the Drive page's Mirror Dungeons card, tapped until the entry page's text shows instead of a fixed 3 s.

The real GoToMirrorEntry in a child process (daily_child.py), under a small hub that ends on the entry page, on a model
of the game: Drive.png, and EntryNewRun.png some screenshots after the card's tap. The child runs every node's
post_delay at 0 (#480), so a hub that does not wait in the action looks at Drive again and taps the card twice.
"""

import json
import threading

from daily_child import bind, game_class, inside, load, result, run_child, run_task, screen

CARD = (340, 240, 240, 140)  # NavDrive's roi: the card is tapped at the middle of the box found in it
SCREENS = {"drive": "Drive.png", "entry": "EntryNewRun.png"}
LIMIT = 8  # s: a scenario still going by then is stopped (each JumpBack gives the hub a new timeout)


def child():
    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) for name, png in SCREENS.items()}

        def set(self, lag, taken=True):
            """lag: screenshots the entry page takes to show after the card's tap; taken: the tap opens it at all."""
            self.screen, self.clicks, self.keys, self.lag, self.taken, self.left = "drive", [], [], lag, taken, None

        def screencap(self):
            if self.left is not None:
                self.left -= 1
                if self.left < 0:
                    self.screen, self.left = "entry", None
            return self.images[self.screen]

        def on_tap(self, x, y):
            if self.screen == "drive" and self.taken and inside(CARD, x, y) and self.left is None:
                self.left = self.lag
            return True

    game = Game()
    tasker = bind(resource, game)
    entry = load_entry()
    override = {"DriveHub": {"rate_limit": 0, "next": ["EntryUp", "[JumpBack]GoToMirrorEntry"]},
                "EntryUp": {"recognition": "OCR", "roi": entry["roi"], "expected": entry["expected"]}}
    out = {"error": None}
    for scenario, model in {"late": (4,), "at_once": (0,), "never": (0, False)}.items():
        game.set(*model)
        actions.LOG.clear()
        timer = threading.Timer(LIMIT, tasker.post_stop)
        timer.start()
        detail = run_task(tasker, scenario, "DriveHub", override)
        timer.cancel()
        out[scenario] = {**result(detail, game, actions), "log": list(actions.LOG)}
    print(json.dumps(out))


def load_entry():
    from test_pipeline import load_nodes

    return load_nodes("mirror_dungeon.json")["MirrorEntryNewRun"]


def drive_lines(o):
    return [line for line in o["log"] if "NavDrive:" in line]


def test_an_entry_page_that_comes_late_gets_one_tap():
    # #58: NavDrive slept 3 s after its tap whatever came; without the sleep the hub tapped the card again.
    o = run_child(__file__)["late"]
    assert o["succeeded"] and o["nodes"][-1] == "EntryUp" and len(o["clicks"]) == 1, json.dumps(o)
    assert len(drive_lines(o)) == 1 and "screen changed after" in drive_lines(o)[0], json.dumps(o)


def test_the_entry_page_shown_at_once_ends_the_wait_at_once():
    o = run_child(__file__)["at_once"]
    assert o["succeeded"] and len(o["clicks"]) == 1, json.dumps(o)
    assert drive_lines(o) and float(drive_lines(o)[0].split("after ")[1].split(" s")[0]) < 1, json.dumps(o)


def test_a_card_whose_tap_opens_nothing_is_tapped_again_after_the_old_3_s():
    from test_pipeline import load_nodes

    timeout = load_nodes("navigation.json")["NavDrive"]["custom_action_param"]["timeout"]
    o = run_child(__file__)["never"]
    assert "EntryUp" not in o["nodes"] and len(o["clicks"]) >= 2, json.dumps(o)  # stopped at LIMIT
    assert drive_lines(o) and all(f"no change after {timeout}." in line for line in drive_lines(o)), json.dumps(o)


def test_the_entry_text_navdrive_waits_for_is_the_entry_nodes():
    # The three entry-page nodes read the same roi; NavDrive's pattern is theirs, so any of them ends its wait.
    from test_pipeline import load_nodes

    nodes = load_nodes("mirror_dungeon.json")
    nxt = load_nodes("navigation.json")["NavDrive"]["custom_action_param"]["next"]
    entry = ("MirrorEntryNewRun", "MirrorEntryPaused", "MirrorEntryUnclaimed")
    assert {tuple(nodes[n]["roi"]) for n in entry} == {tuple(nxt["roi"])}
    assert set(nxt["expected"].split("|")) == {nodes[n]["expected"] for n in entry}


if __name__ == "__main__":
    child()
