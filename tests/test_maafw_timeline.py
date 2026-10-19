import maafw_timeline as mt


def succ(t, node):
    return f'[2026-10-17 14:00:{t}][INF][Px1][Tx1][Utils/EventDispatcher.hpp][L65][x] [msg=Node.PipelineNode.Succeeded] [details={{"focus":null,"name":"Entry","node_details":{{"name":"{node}"}},"node_id":1}}]\n'


def ca(t, node=None):
    tail = (
        f"[context.task_id()=1] [node_name={node}] [param.name=TapUntil]"
        if node
        else "| leave, 1ms"
    )
    return f"[2026-10-17 14:00:{t}][DBG][Px1][Tx1][CustomAction.cpp][L15][MaaNS::TaskNS::CustomAction::run] {tail}\n"


def agent(t):
    return f"[2026-10-17 14:00:{t}][DBG][Px1][Tx1][AgentClient.cpp][L598][MaaNS::AgentClient::handle_context_run_recognition] x\n"


LOG = [
    succ("00.000", "Hub"),
    ca("01.000", "Shop"),
    agent("01.100"),
    agent("01.150"),  # 0.1 s to the first call, then a 2 s sleep
    agent("03.150"),
    agent("03.200"),
    ca("02.000", "Inner"),
    ca("02.100"),  # a nested action is part of the outer one
    ca("03.500"),
    succ("04.000", "Shop"),
    succ("05.000", "Hub"),
]


def test_steps_actions_and_fixed_waits():
    s = mt.steps(*mt.parse(LOG))
    assert [x[0] for x in s] == ["Shop", "Hub"]
    _, a, b, act, fixed = s[0]
    assert round(b - a, 3) == 4.0 and round(act, 3) == 2.5
    assert round(fixed, 3) == 2.3  # 01.150 -> 03.150 and 03.200 -> 03.500
    assert s[1][3] == 0.0  # no action for that Hub step


def test_window_and_table():
    s = mt.steps(*mt.parse(LOG))
    groups = mt.windows(s, [], ("Shop", "Shop"))
    assert len(groups) == 1 and [x[0] for x in groups[0]] == ["Shop"]
    out = mt.table(groups)
    assert "Shop" in out and "1 run(s)" in out


def test_the_ret_line_after_an_action_is_not_an_enter():
    ret = "[2026-10-17 14:00:03.400][DBG][Px1][Tx1][CustomAction.cpp][L36][MaaNS::TaskNS::CustomAction::run] [node_name=Shop] [ret=true]\n"
    s = mt.steps(*mt.parse([*LOG[:-3], ret, *LOG[-3:]]))
    assert round(s[0][3], 3) == 2.5
