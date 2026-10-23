from action_gaps import hits, table


def hit(t, name):
    return f"[2026-10-22 {t}][INF][Px1][Tx1][PipelineTask.cpp][L317][MaaNS::TaskNS::PipelineTask::recognize_list] reco hit [result.name={name}] [result.box=[0,0,1,1]] \n"


def sleep(t, ms):
    return f"[2026-10-22 {t}][DBG][Px1][Tx1][TaskBase.cpp][L215][MaaNS::TaskNS::TaskBase::sleep] {ms}ms \n"


def start(t, name):
    return f'[2026-10-22 {t}][INF][Px1][Tx1][Utils/EventDispatcher.hpp][L65][MaaNS::EventDispatcher::notify] !!!OnEventNotify!!! [handle=true] [msg=Node.Action.Starting] [details={{"action_id":1,"name":"{name}","task_id":2}}] \n'


def ran(t, name):
    return f"[2026-10-22 {t}][DBG][Px1][Tx1][CustomAction.cpp][L36][MaaNS::TaskNS::CustomAction::run] [node_name={name}] [param.name=RouteMap] [session.action=true] [ret=true] \n"


LOG = [
    hit("10:00:00.000", "MirrorMap"), sleep("10:00:00.000", 200), start("10:00:00.200", "MirrorMap"),
    ran("10:00:03.200", "MirrorMap"), sleep("10:00:03.200", 200),  # 3 s action, 200 ms after it
    hit("10:00:03.700", "Event"), sleep("10:00:03.700", 200), start("10:00:03.900", "Event"), ran("10:00:04.400", "Event"), sleep("10:00:04.400", 200),
    hit("10:00:04.900", "MirrorMap"), sleep("10:00:04.900", 200), start("10:00:05.100", "MirrorMap"), ran("10:00:05.300", "MirrorMap"),  # 0.2 s: handed back
]


def test_a_hit_with_its_sleeps_and_its_action():
    first = hits(LOG)[0]
    assert (first["name"], first["pre"], first["post"], round(first["end"] - first["start"], 3)) == ("MirrorMap", 0.2, 0.2, 3.0)


def test_the_table_counts_short_actions_and_names_what_follows():
    rows = table(hits(LOG), ["MirrorMap"]).splitlines()
    assert rows[2] == "| MirrorMap | 2 | 0.20 | 1.60 | 0.10 | 0.50 | 1 | Event 1 |"
