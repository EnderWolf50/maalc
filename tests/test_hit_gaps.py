from hit_gaps import events, spans, table


def hit(t, name):
    return f"[2026-10-21 {t}][INF][Px1][Tx1][PipelineTask.cpp][L317][MaaNS::TaskNS::PipelineTask::recognize_list] reco hit [result.name={name}] [result.box=[0,0,1,1]] \n"


def sleep(t, ms):
    return f"[2026-10-21 {t}][DBG][Px1][Tx1][TaskBase.cpp][L215][MaaNS::TaskNS::TaskBase::sleep] {ms}ms \n"


LOG = [
    hit("10:00:00.000", "HubText"),  # the OCR pass that picks screens, not a screen
    hit("10:00:00.100", "Victory"), sleep("10:00:00.100", 200), sleep("10:00:00.400", 500),  # pre_delay, post_delay
    hit("10:00:01.000", "Victory"), sleep("10:00:01.000", 200), sleep("10:00:01.300", 500),
    hit("10:00:01.900", "Loading"), sleep("10:00:01.900", 200),
    hit("10:00:02.500", "Victory"),
]


def test_hits_and_the_sleeps_after_each():
    assert [(name, slept) for _, name, slept in events(LOG)] == [("Victory", 0.7), ("Victory", 0.7), ("Loading", 0.2), ("Victory", 0.0)]


def test_a_span_runs_to_the_next_screen_from_its_first_and_its_last_hit():
    (name, hits, first, last), = spans(events(LOG))[:1]
    assert (name, hits) == ("Victory", 2)
    assert (round(first, 3), round(last, 3)) == (1.8, 0.9)  # 10:00:00.100 and 10:00:01.000 to 10:00:01.900


def test_the_table_names_the_screen_that_follows():
    rows = table(events(LOG), ["Victory"]).splitlines()
    assert rows[2] == "| Victory | 3 | 0.7 | 1 | 1.80, 1.80 | 0.90 | Loading 1 |"
