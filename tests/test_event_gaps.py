import actions
from event_gaps import BUTTON, CORNER, OPTION_X, TAKE, presses, read, soon, table


def click(t, x, y):
    return (f'[2026-11-08 {t}][DBG][Px1][Tx1][AgentClient.cpp][L2005][MaaNS::AgentNS::ClientNS::AgentClient::handle_controller_post_click] '
            f'[req={{"_ControllerPostClickReverseRequest":1,"contact":0,"controller_id":"0","pressure":1,"x":{x},"y":{y}}}] [ipc_addr_=ipc://x.sock] | enter \n')


def start(t):
    return (f"[2026-11-08 {t}][DBG][Px1][Tx1][CustomAction.cpp][L15][MaaNS::TaskNS::CustomAction::run] [context.task_id()=200000001] "
            "[node_name=Event] [session.action=true] [param.name=Event] | enter \n")


def end(t):
    return f"[2026-11-08 {t}][DBG][Px1][Tx1][CustomAction.cpp][L36][MaaNS::TaskNS::CustomAction::run] [node_name=Event] [param.name=Event] [ret=true] \n"


def connecting(t, box="[1040,48,186,46]"):
    return (f'[2026-11-08 {t}][INF][Px1][Tx1][Recognizer.cpp][L103][MaaNS::TaskNS::Recognizer::recognize] reco [result={{"algorithm":"TemplateMatch",'
            f'"box":{box},"detail":{{}},"name":"Connecting","reco_id":1}}] \n')


OPTION = (OPTION_X, 400)


def test_the_taps_it_tells_apart_are_the_agents():
    assert (CORNER, BUTTON, OPTION_X, TAKE) == (actions.EVENT_NEUTRAL, actions.EVENT_BUTTON, actions.CHOICE_X, actions.EVENT_TAKE)


def groups(lines):
    return [(r["group"], round(r["total"], 3), r["connecting"], r["hub"] and round(r["hub"], 3)) for r in presses(read(lines))]


def test_an_option_handed_back_through_connecting_is_split_at_the_hand_back():
    lines = [start("10:00:00.000"), click("10:00:00.100", *OPTION), end("10:00:00.400"), connecting("10:00:00.500"),
             start("10:00:01.000"), click("10:00:01.300", *BUTTON), end("10:00:01.400")]
    assert groups(lines) == [("option", 1.2, True, 0.6)]


def test_a_press_after_text_in_the_same_call_is_a_corner_one_not_handed_back():
    lines = [start("10:00:00.000"), click("10:00:00.150", *CORNER), click("10:00:00.300", *CORNER),
             click("10:00:00.400", *BUTTON), end("10:00:01.000")]
    assert groups(lines) == [("corner", 0.1, False, None)]


def test_an_option_counts_from_its_own_tap_through_the_corner_taps_after_it():
    lines = [start("10:00:00.000"), click("10:00:00.100", *OPTION), click("10:00:00.600", *CORNER),
             connecting("10:00:00.700", box="null"), click("10:00:00.800", *BUTTON), click("10:00:00.950", *CORNER),
             click("10:00:01.050", *BUTTON), end("10:00:02.000")]
    assert groups(lines) == [("option", 0.7, False, None), ("corner", 0.1, False, None)]


def test_taps_outside_an_event_call_and_back_to_back_presses_are_in_no_group():
    lines = [click("10:00:00.000", *OPTION), start("10:00:00.100"), click("10:00:00.200", *BUTTON),
             click("10:00:00.300", *BUTTON), end("10:00:00.400"), click("10:00:00.500", *BUTTON)]
    assert groups(lines) == []


def test_the_table_has_a_row_per_group_seen_and_the_longest_call():
    lines = [start("10:00:00.000"), click("10:00:00.150", *CORNER), click("10:00:00.400", *BUTTON), end("10:00:01.000")]
    rows = table(presses(log := read(lines)), log).splitlines()
    assert rows[2] == "| corner | 1 | 0.25 | 0.25-0.25 | 0 | - | - | - |"
    assert rows[-2:] == ["Event calls: 1; most corner taps in one call: 1", "presses under 1.5 s after the press before: 0"]


def test_a_press_soon_after_the_one_before_is_flagged_for_the_recording():
    # #557's acceptance: one lit button pressed twice shows only as two presses close together.
    lines = [start("10:00:00.000"), click("10:00:00.100", *BUTTON), click("10:00:00.250", *CORNER),
             click("10:00:01.500", *BUTTON), click("10:00:01.650", *CORNER), click("10:00:03.100", *BUTTON), end("10:00:04.000")]
    assert len(soon(read(lines))) == 1
