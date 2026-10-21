import json
import re
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent / "assets/resource/base/pipeline"


def load(name):
    text = (PIPELINE / name).read_text(encoding="utf-8")
    return json.loads("\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//")))


def test_the_main_window_popups_click_their_close_button_only():
    # #85: the Mailbox's Close sits next to Claim All, the menu's Return above Quit Game.
    popups = load("popups.json")
    for name, button in [("Mailbox", "Close"), ("SettingsMenu", "Return")]:
        node = popups[name]
        clicked = node["all_of"][node["box_index"]]["expected"]
        assert node["action"] == "Click" and re.search(clicked, button) and not re.search(clicked, "Claim All")


def test_the_help_pager_is_looked_at_before_the_entry_page_under_it():
    hub = load("mirror_dungeon.json")["MirrorHub"]["next"]
    assert hub.index("[JumpBack]HelpPager") < hub.index("[JumpBack]HubText")
