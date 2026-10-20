import json

from wait_spans import passes, spans


def reco(t, name, score, hit=True):
    result = {"name": name, "box": [0, 0, 1, 1] if hit else None, "detail": {"best": {"score": score}}}
    return f"[2026-10-19 {t}][INF][Px1][Tx1][Recognizer.cpp][L103][MaaNS::TaskNS::Recognizer::recognize] reco [result={json.dumps(result)}] \n"


def hub(t, name, score):
    return [reco(t, "Stuck", 0, hit=False), reco(t, name, score)]


def test_a_span_and_its_longest_still_stretch():
    log = (hub("19:44:00.000", "Loading", 0.91) + hub("19:44:10.000", "Loading", 0.95)  # moving
           + hub("19:44:20.000", "Loading", 0.99) + hub("19:44:50.000", "Loading", 0.99)  # still 30 s
           + hub("19:45:00.000", "Victory", 0.9) + hub("19:45:10.000", "Loading", 0.9))
    out = spans(passes(log), {"Loading"})
    assert [(kind, seconds, n, still) for _, kind, seconds, n, still in out] == [("Loading", 50.0, 4, 30.0), ("Loading", 0.0, 1, 0.0)]
