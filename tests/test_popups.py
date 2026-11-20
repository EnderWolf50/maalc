import re

from test_pipeline import hub_entries, load_nodes


def test_the_main_window_popups_click_their_close_button_only():
    # #85: the Mailbox's Close sits next to Claim All, the menu's Return above Quit Game.
    nodes = load_nodes()
    for name, button in [("Mailbox", "Close"), ("SettingsMenu", "Return")]:
        node = nodes[name]
        clicked = node["all_of"][node["box_index"]]["expected"]
        assert node.get("custom_action") == "DismissShot" and re.search(clicked, button) and not re.search(clicked, "Claim All")


def test_connecting_is_looked_at_again_at_the_pace_of_the_hub_that_saw_it():
    # #258: CONNECTING has nothing to press; each hit slept 1.2 s (pre 200 ms, post 1000 ms), so the screen after it was
    # seen up to 1.2 s late (live logs: 1.27-2.42 s from the last hit to the next screen, 266 spans). A hit skips the
    # hub's rate_limit (Loading, 0 / 0 ms, hit again every 0.15-0.32 s on 2026-10-29), so 0 would shoot the screen as
    # fast as a pass runs: the post_delay is the hub's own pace instead.
    nodes = load_nodes()
    connecting = nodes["Connecting"]
    hubs = {n: d.get("rate_limit") for n, d in nodes.items() if any(x.endswith("]Connecting") or x == "Connecting" for x in d.get("next", []))}
    assert len(hubs) >= 6 and connecting.get("pre_delay") == 0
    assert set(hubs.values()) == {connecting["post_delay"]}, hubs
    # GoHome waits on CONNECTING in a node of its own (#540), at the same pace.
    assert nodes["HomeConnecting"]["rate_limit"] == connecting["post_delay"]


def test_the_help_pager_is_looked_at_before_the_entry_page_under_it():
    hub = load_nodes()["MirrorHub"]["next"]
    assert hub.index("[JumpBack]HelpPager") < hub.index("[JumpBack]HubText")


def test_the_hidden_battle_window_is_skipped_before_every_page_and_never_entered():
    # #850: the window covers the page under it (map or the floor change), so it sits with the popups, ahead of the
    # first page. DismissShot taps the box of its first part (no box_index), the Skip it read; nothing reads an option
    # there. A read of both buttons as one box is no Skip: its centre could be Enter's.
    nodes = load_nodes()
    hub = hub_entries(nodes, "HubText")
    assert hub.index("HiddenBattle") < hub.index("ProgressPanel")
    node = nodes["HiddenBattle"]
    assert (node["recognition"], node.get("box_index", 0), node["custom_action"]) == ("And", 0, "DismissShot")
    tapped, title = node["all_of"]
    assert re.search(tapped["expected"], "Skip") and re.search(tapped["expected"], "XSkip")  # an icon read as a letter
    assert not any(re.search(tapped["expected"], t) for t in ("Enter", "Skip Enter", "Enter Skip"))
    assert re.search(title["expected"], "Dimension Reversal Zone - COGNITION ERROR WARNING")
    assert "custom_action_param" not in node


def test_a_popup_over_the_mailbox_is_answered_before_the_mailbox():
    # live #84: the server error and the network popup came up over the Mailbox, which still reads under them.
    entries = hub_entries(load_nodes(), "HubText")
    assert entries.index("RetryPopup") < entries.index("PopupButton") < entries.index("Mailbox")
