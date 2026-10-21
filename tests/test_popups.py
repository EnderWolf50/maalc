import re

from test_pipeline import load_nodes


def test_the_main_window_popups_click_their_close_button_only():
    # #85: the Mailbox's Close sits next to Claim All, the menu's Return above Quit Game.
    nodes = load_nodes()
    for name, button in [("Mailbox", "Close"), ("SettingsMenu", "Return")]:
        node = nodes[name]
        clicked = node["all_of"][node["box_index"]]["expected"]
        assert node["action"] == "Click" and re.search(clicked, button) and not re.search(clicked, "Claim All")


def test_the_help_pager_is_looked_at_before_the_entry_page_under_it():
    hub = load_nodes()["MirrorHub"]["next"]
    assert hub.index("[JumpBack]HelpPager") < hub.index("[JumpBack]HubText")


def test_a_popup_over_the_mailbox_is_answered_before_the_mailbox():
    # live #84: the server error and the network popup came up over the Mailbox, which still reads under them.
    entries = load_nodes()["HubText"]["custom_recognition_param"]["entries"]
    assert entries.index("RetryPopup") < entries.index("PopupButton") < entries.index("Mailbox")
