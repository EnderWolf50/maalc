import json
from datetime import datetime, timedelta

from turn_start import report, rows, turns

T0 = datetime(2026, 11, 8, 10, 0, 0)
BOX = "[rect=[984,531,40,29]]"
WIN_RATE = (1004, 545)  # inside the BattleTurn box
PORTRAIT = (362, 665)  # a guard turn's first tap


def head(s, level="DBG", where="X.cpp][L1][MaaNS::X"):
    return f"[{(T0 + timedelta(seconds=s)).isoformat(' ', 'milliseconds')}][{level}][Px1][Tx1][{where}]"


def hit(s, name):
    return head(s, "INF", "PipelineTask.cpp][L317][MaaNS::TaskNS::PipelineTask::recognize_list") + f" reco hit [result.name={name}] [result.box=[0,0,1,1]] \n"


def enter(s, action, node):
    run = "CustomAction.cpp][L15][MaaNS::TaskNS::CustomAction::run"
    return [head(s, where=run) + f" [context.task_id()=1] [node_name={node}] [session.action=true] [param.name={action}] [param.custom_param=null] {BOX} | enter \n",
            head(s, where="CustomAction.cpp][L36][MaaNS::TaskNS::CustomAction::run") + f" [node_name={node}] [param.name={action}] [ret=true] \n"]


def leave(s):
    return head(s, "TRC", "CustomAction.cpp][L15][MaaNS::TaskNS::CustomAction::run") + " | leave, 1ms \n"


def agent(s, handler, req="{}"):
    where = f"AgentClient.cpp][L1][MaaNS::AgentNS::ClientNS::AgentClient::handle_{handler}"
    return [head(s, where=where) + f" [req={req}] | enter \n", head(s, "TRC", where) + " | leave, 0ms \n"]


def cap(s):
    return agent(s, "controller_post_screencap")


def touch(s, kind, x=0, y=0):
    return agent(s, f"controller_post_{kind}", json.dumps({"x": x, "y": y}, separators=(",", ":")))


def look(s, entry, found, text=None, ms=4):
    """An agent run_recognition of entry, hit or missed; text: what an OCR read."""
    where = "AgentClient.cpp][L598][MaaNS::AgentNS::ClientNS::AgentClient::handle_context_run_recognition"
    detail = {"all": [{"box": [55, 57, 45, 30], "text": text}] if text else []}
    details = {"action_details": None, "focus": None, "name": entry, "reco_details": {"detail": detail, "name": entry}}
    event = "Succeeded" if found else "Failed"
    return [head(s, where=where) + f' [req={{"entry":"{entry}","pipeline_override":{{}}}}] | enter \n',
            head(s, "INF", "Utils/EventDispatcher.hpp][L65][MaaNS::EventDispatcher::notify")
            + f" !!!OnEventNotify!!! [handle=true] [msg=Node.RecognitionNode.{event}] [details={json.dumps(details, separators=(',', ':'))}] \n",
            head(s + ms / 1000, "TRC", where) + f" | leave, {ms}ms \n"]


def hold(s, looks):
    """hold_turn from s: a finger on the corner, one look every 0.3 s, (entry, hit) each; lifted 0.05 s after the last."""
    lines = touch(s, "touch_down", 1, 1)
    for i, (entry, found) in enumerate(looks, 1):
        lines += look(s + 0.3 * i, entry, found)
    return lines + touch(s + 0.3 * len(looks) + 0.05, "touch_up"), s + 0.3 * len(looks) + 0.06


def play_turn(s, number, caps=2, first=WIN_RATE, looks=(("BattlePause", True), ("BattleTurn", True))):
    """The hub sees BattleTurn at s, PlayTurn: still() with caps screenshots 0.22 s apart, the turn number OCR
    (0.04 s), the first tap 0.06 s later, START, the turn seen playing, a hold of looks. Its lines, and its end."""
    lines = [hit(s, "BattleTurn"), *enter(s + 0.2, "PlayTurn", "BattleTurn")]
    for i in range(caps):
        lines += cap(s + 0.2 + 0.22 * i)
    read = s + 0.2 + 0.22 * (caps - 1) + 0.02
    lines += look(read, "ReadText", True, number, ms=40)
    lines += touch(read + 0.1, "click", *first) + touch(read + 0.3, "click", 920, 571)
    lines += look(read + 0.5, "BattleTurn", True) + look(read + 0.8, "BattlePause", True)  # START: not started yet, then playing
    held, end = hold(read + 0.9, looks)
    return lines + held + [leave(end)], end


def hold_turn(s, looks):
    """The hub sees BattlePause at s, HoldTurn holds."""
    held, end = hold(s, looks)
    return [hit(s, "BattlePause"), *enter(s, "HoldTurn", "BattlePause"), *held, leave(end)], end


def battle():
    """Formation, Loading, then turn 1 (still() took 3 screenshots); turn 2 after the hold of turn 1 saw BattleTurn;
    turn 3 after a HoldTurn (turn 2's hold timed out on BattlePause); turn 3 again, a guard turn, after a hold that
    saw neither; a still() that timed out (PlayTurn hands back); a new battle's turn 1."""
    lines = [*enter(1, "Formation", "Formation"), leave(2), hit(3, "Loading"), hit(5, "BattleHUD")]
    one, end = play_turn(10, "1", caps=3)
    two, end = play_turn(end + 0.27, "2", looks=[("BattlePause", True)] * 3)
    held, end = hold_turn(end + 0.1, [("BattlePause", True), ("BattlePause", False), ("BattleTurn", True)])
    three, end = play_turn(end + 0.07, "3", looks=[("BattlePause", True), ("BattlePause", False)])
    again, end = play_turn(end + 0.27, "3", first=PORTRAIT)
    lines += one + two + held + three + again
    lines += [hit(end + 0.27, "BattleTurn"), *enter(end + 0.47, "PlayTurn", "BattleTurn"), *cap(end + 0.47), leave(end + 1.5)]
    lines += [*enter(end + 2, "Victory", "Victory"), leave(end + 2.1), hit(end + 5, "Loading")]
    new, end = play_turn(end + 10, "1")
    return lines + new


def ms(turn):
    return [round(x) for x in turn.segments()]


def test_a_turn_from_its_hit_to_its_first_tap():
    found, left, _ = turns([battle()])
    first = found[0]
    assert ms(first) == [760, 200, 460, 40, 60]  # still() took 3 screenshots: 0.22 s more
    assert (first.caps, first.number, first.win_rate, first.before, first.pause_age, first.turn_age) == (3, "1", True, "Formation", None, None)
    assert ms(found[1]) == [540, 200, 240, 40, 60]
    assert [t.number for t in found] == ["1", "2", "3", "3", "1"]
    assert left == {"PlayTurn ended before its ReadText or touch": 1}


def test_after_the_previous_turns_hold_saw_the_next_turn():
    t = turns([battle()])[0][1]
    assert (t.before, round(t.gap, 3)) == ("PlayTurn", 0.27)
    assert (round(t.pause_age, 3), round(t.turn_age, 3)) == (0.63, 0.33)  # the hold's BattlePause and BattleTurn looks


def test_after_a_hold_timed_out_the_hub_saw_battlepause_and_held_again():
    three = turns([battle()])[0][2]
    # the HoldTurn's own looks, not the hub's BattlePause hit 0.3 s before them nor turn 2's hold
    assert (three.before, round(three.gap, 3), round(three.pause_age, 3), round(three.turn_age, 3)) == ("HoldTurn", 0.07, 0.73, 0.13)


def test_the_same_turn_number_again_is_a_repeat_but_not_in_the_next_battle():
    found = turns([battle()])[0]
    assert [t.again for t in found] == [False, False, False, True, False]
    assert len({t.battle for t in found}) == 2
    assert found[3].win_rate is False  # a portrait first
    assert (round(found[3].pause_age, 3), found[3].turn_age) == (0.63, None)  # press_start's BattleTurn look is no hold's
    assert found[4].pause_age is None  # the BattlePause looks of the battle before


def test_a_log_cut_inside_a_turn_is_left_out_and_a_repeated_log_head_is_skipped():
    lines = battle()
    start, cut = lines.index(hit(10, "BattleTurn")), lines.index(next(x for x in lines if "post_click" in x))
    found, left, skipped = turns([lines[:cut], lines[start:]])  # the first log ends before turn 1's first tap
    assert left["log or process ended in it"] == 1
    assert skipped == [0, cut - start]
    assert [t.number for t in found] == ["2", "3", "3", "1"]  # the second log starts after its repeated lines


def process_start(s):
    return head(s, where="Logger") + " MAA Process Start \n"


def test_a_bot_stopped_inside_an_action_does_not_hide_the_next_process_logging_to_the_same_file():
    # live 2026-11-08: the bot was stopped inside RouteMap and started again, MaaFramework logging on in the same file
    lines = [*enter(1, "Formation", "Formation"), leave(2), hit(3, "Loading")]
    one, end = play_turn(10, "1")
    lines += one + enter(end + 1, "RouteMap", "MirrorMap")
    lines += [process_start(end + 30), *enter(end + 31, "Formation", "Formation"), leave(end + 32), hit(end + 33, "Loading")]
    again, _ = play_turn(end + 40, "1")
    found, left, _ = turns([lines + again])
    assert [(t.number, t.before, t.again) for t in found] == [("1", "Formation", False), ("1", "Formation", False)]
    assert len({t.battle for t in found}) == 2
    assert left == {}


def test_a_turn_its_process_stopped_in_is_left_out():
    one, _ = play_turn(10, "1")
    cut = next(i for i, x in enumerate(one) if "post_click" in x)  # before its first tap
    lines = [*enter(1, "Formation", "Formation"), leave(2), hit(3, "Loading"), *one[:cut], process_start(20)]
    lines += [*enter(21, "Formation", "Formation"), leave(22), hit(23, "Loading")]
    two, _ = play_turn(30, "1")
    found, left, _ = turns([lines + two])
    assert left == {"log or process ended in it": 1}
    assert [(t.number, ms(t)) for t in found] == [("1", [540, 200, 240, 40, 60])]  # the second process's whole turn


def test_the_report_rows_and_summary():
    found, left, skipped = turns([battle()])
    out = report(found, left, skipped).splitlines()
    assert out[0] == "5 turns; left out: PlayTurn ended before its ReadText or touch 1"
    assert "| HoldTurn | 1 | 540 | 200 | 240 | 40 | 60 | 2: 1 | 0 | 1: 0.73 / 0.73 / 0.73 / 0.73 | 1: 0.13 / 0.13 / 0.13 / 0.13 | 0.07 |" in out
    assert "| PlayTurn | 2 | 540 | 200 | 240 | 40 | 60 | 2: 2 | 1 | 2: 0.63 / 0.63 / 0.63 / 0.63 | 1: 0.33 / 0.33 / 0.33 / 0.33 | 0.27 |" in out
    assert rows(found)[3] == "| 11-08 10:00:12.490 | 2 |  | PlayTurn | 0.27 | 0.63 | 0.33 | 2 | Win Rate | 540 | 200 | 240 | 40 | 60 |"
