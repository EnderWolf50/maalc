"""Mirror Dungeons started on a Luxcavation page (acceptance 5, K3): the main window first (GoHome), not 60 s of nothing
known and the recovery's back key.

The real MirrorDungeon task in a child process (daily_child.py) on a model of the game: Luxcavation's back key goes to
Drive, Drive's Window tab to the main window. The way on from there (GoToMirrorEntry) is off, and MirrorHub times out
after 3 s with no recovery: what is tested is how the task gets to the main window.
"""

import json
import time

from daily_child import bind, game_class, inside, load, result, run_child, screen

WINDOW_TAB = (790, 608, 70, 64)
SCREENS = {"lux": "LuxThread.png", "drive": "Drive.png", "main": "MainWindow.png"}


def child():
    actions, resource = load()

    class Game(game_class()):
        images = {name: screen(png) for name, png in SCREENS.items()}
        screen, clicks, keys = "lux", [], []

        def on_tap(self, x, y):
            if self.screen == "drive" and inside(WINDOW_TAB, x, y):
                self.screen = "main"
            return True

        def on_key(self, keycode):
            if keycode == 4 and self.screen == "lux":
                self.screen = "drive"
            return True

    game = Game()
    tasker = bind(resource, game)
    override = {"MirrorHub": {"timeout": 3000, "on_error": []}, "GoToMirrorEntry": {"enabled": False}}
    began = time.monotonic()
    out = {"error": None, **result(tasker.post_task("MirrorDungeon", override).wait().get(), game, actions),
           "seconds": time.monotonic() - began}
    print(json.dumps(out))


def test_mirror_dungeon_started_on_a_luxcavation_page_goes_to_the_main_window_first():
    o = run_child(__file__)
    assert "MirrorFromLux" in o["nodes"] and o["screen"] == "main", o
    assert o["keys"] == [4] and len(o["clicks"]) == 1 and inside(WINDOW_TAB, *o["clicks"][0]), o
    assert o["seconds"] < 30, o  # not MirrorHub's 60 s of nothing known


if __name__ == "__main__":
    child()
