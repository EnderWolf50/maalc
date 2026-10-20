import maafw_timeline as mt

PREFIX = "[2026-10-17 14:00:{t}][DBG][Px1][Tx1]"


def succeeded(t, node):
    details = f'{{"focus":null,"name":"Entry","node_details":{{"name":"{node}"}},"node_id":1}}'
    return (
        PREFIX.format(t=t)
        + f"[Utils/EventDispatcher.hpp][L65][x] [msg=Node.PipelineNode.Succeeded] [details={details}]\n"
    )


def action_enter(t, node):
    return (
        PREFIX.format(t=t)
        + f"[CustomAction.cpp][L15][MaaNS::TaskNS::CustomAction::run] [context.task_id()=1] [node_name={node}] [param.name=TapUntil]\n"
    )


def action_leave(t):
    return (
        PREFIX.format(t=t)
        + "[CustomAction.cpp][L15][MaaNS::TaskNS::CustomAction::run] | leave, 1ms\n"
    )


def agent_call(enter, leave):
    where = (
        "[AgentClient.cpp][L598][MaaNS::AgentClient::handle_context_run_recognition]"
    )
    return [
        PREFIX.format(t=enter) + where + ' [req={"entry":"ReadText"}]\n',
        PREFIX.format(t=leave) + where + " | leave, 1ms\n",
    ]


LOG = [
    succeeded("00.000", "Hub"),
    action_enter("01.000", "Shop"),
    *agent_call("01.100", "01.150"),  # 0.1 s after the start: under the 0.2 s gap
    *agent_call(
        "03.150", "03.650"
    ),  # a 2 s sleep before it; the 0.5 s call itself is not a wait
    action_enter("03.700", "Inner"),  # a nested action is part of the outer one
    action_leave("03.750"),
    action_leave("04.000"),  # 0.35 s after the last call
    succeeded("04.500", "Shop"),
    succeeded("05.000", "Hub"),
]


def test_steps_actions_and_fixed_waits():
    s = mt.steps(*mt.parse(LOG))
    assert [x.node for x in s] == ["Shop", "Hub"]
    assert round(s[0].end - s[0].start, 3) == 4.5 and round(s[0].action, 3) == 3.0
    assert round(s[0].fixed, 3) == 2.35  # 01.150 -> 03.150 and 03.650 -> 04.000
    assert s[1].action == 0.0  # no action for that Hub step


def test_the_ret_line_after_an_action_is_not_an_enter():
    ret = (
        PREFIX.format(t="03.990")
        + "[CustomAction.cpp][L36][MaaNS::TaskNS::CustomAction::run] [node_name=Shop] [ret=true]\n"
    )
    s = mt.steps(*mt.parse([*LOG[:-3], ret, *LOG[-3:]]))
    assert round(s[0].action, 3) == 3.0


def test_window_range_and_table():
    s = mt.steps(*mt.parse(LOG))
    groups = mt.windows(s, [], ("Shop", "Shop"))
    assert len(groups) == 1 and [x.node for x in groups[0]] == ["Shop"]
    assert (
        mt.windows(s, [], ("Shop", "Never")) == []
    )  # a window that never closes is left out
    cut = mt.windows(s, [(s[0].start + 1, s[1].end)], None)
    assert [x.node for x in cut[0]] == [
        "Hub"
    ]  # the step cut by the range edge is left out
    out = mt.table(groups)
    assert "Shop" in out and "1 run(s)" in out
