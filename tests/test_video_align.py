import random

import numpy as np

import video_align as va

STARTED = 1000.0  # wall time of the first frame, as the recorder printed it
FPS = 10
FROZEN = (150.0, 250.0)  # the display slept: the recorder repeated one frame 150 s to 250 s into the video


def drift(pts):
    """The recorder's clock runs behind the log's, from 0.8 s at the start to 1.2 s 400 s in."""
    return 0.8 + 0.4 * pts / 400


def pulses():
    """When Victory was up, in log time: 1.5 s each, at irregular gaps over the whole run."""
    rng, t, out = random.Random(1), STARTED + 3, []
    while t < STARTED + 420:
        out.append((t, t + 1.5))
        t += rng.uniform(6, 30)
    return out


UP = pulses()


def screen(t):
    return any(a <= t <= b for a, b in UP)


def video():
    pts = np.arange(0, 400, 1 / FPS)
    scores = np.array([0.9 if screen(STARTED + p + drift(p)) else 0.1 for p in pts])
    frozen = (pts >= FROZEN[0]) & (pts <= FROZEN[1])
    scores[frozen] = scores[np.flatnonzero(frozen)[0] - 1]  # the last frame before, over and over
    return STARTED + pts, {"Victory": scores}, np.r_[False, frozen[1:]]


def bot_samples():
    t = np.arange(STARTED, STARTED + 420, 0.37)  # one hub pass every 0.37 s, scoring Victory
    return {"Victory": (t, np.array([0.85 if screen(x) else 0.15 for x in t]))}


def test_chunks_follow_the_drift_and_a_freeze_stays_unaligned():
    vt, vs, still = video()
    frozen = va.freezes(vt, still)
    assert [(round(a - STARTED), round(b - STARTED)) for a, b in frozen] == [(150, 250)]
    segs = va.fit(vt, vs, bot_samples(), chunk=50, max_lost=600, frozen=frozen)
    for s in segs:
        mid = (s.v0 + s.v1) / 2 - STARTED
        if FROZEN[0] <= mid <= FROZEN[1]:
            assert s.offset is None
        else:  # the bot scores every 0.37 s, so a pulse edge pins the offset to about half of that
            assert s.offset is not None and abs(s.offset - drift(mid)) <= 0.25, s
    lt = va.log_times(vt, segs, frozen)
    assert np.isnan(lt[(vt - STARTED >= 150) & (vt - STARTED <= 250)]).all()


def test_a_frozen_screen_is_not_counted_as_up():
    vt, vs, still = video()
    frozen = va.freezes(vt, still)
    lt = va.log_times(vt, va.fit(vt, vs, bot_samples(), chunk=50, max_lost=600, frozen=frozen), frozen)
    rows = va.intervals(lt, vs["Victory"], 0.6, hub=[], hits=[])
    assert max(r["up_s"] for r in rows) <= 1.6  # every pulse is 1.5 s; none stretches through the freeze


def test_a_chunk_with_nothing_to_fit_takes_the_nearest_offset():
    vt, vs, _ = video()
    vs = {"Victory": np.where(vt - STARTED < 100, vs["Victory"], 0.1)}  # no screen after 100 s
    segs = va.fit(vt, vs, bot_samples(), chunk=50, max_lost=600)
    assert all(s.offset is not None for s in segs)
    assert segs[-1].offset == segs[1].offset and segs[-1].corr == -1.0


def test_holes_are_jumps_in_the_pts():
    vt = np.r_[np.arange(0, 10, 0.1), np.arange(15, 20, 0.1)]
    assert [(round(a, 1), round(b, 1)) for a, b in va.holes(vt)] == [(9.9, 15.0)]


def test_a_refresh_between_still_frames_does_not_end_a_freeze():
    vt = np.arange(0, 30, 0.1)
    still = np.ones(len(vt), bool)
    for k in (0, 80, 160):
        still[k:k + 5] = False  # the recorder refreshed its frame every 8 s, five changed frames at a time
    assert [(round(a, 1), round(b, 1)) for a, b in va.freezes(vt, still)] == [(0.5, 29.9)]


def test_chunks_before_the_first_offset_are_fitted_around_it():
    vt, vs, _ = video()
    bot = bot_samples()
    bt, bs = bot["Victory"]
    early = bt < STARTED + 100  # the bot logged no scores in the first 100 s: nothing to anchor on there
    segs = va.fit(vt, vs, {"Victory": (bt[~early], bs[~early])}, chunk=50, max_lost=600)
    assert segs[0].offset is not None and segs[0].corr == -1.0  # nothing to fit: the anchor's offset
    vs2 = {"Victory": vs["Victory"].copy()}
    vs2["Victory"][(vt - STARTED < 50)] = 1 - vs2["Victory"][(vt - STARTED < 50)]  # a screen that fits nothing
    segs = va.fit(vt, vs2, bot, chunk=50, max_lost=600)
    assert segs[0].offset is None and segs[0].corr < 0.8 and segs[1].offset is not None


def test_parse_log_sorts_the_bot_samples():
    lines = [LOG[1].replace("00.200", "00.900"), LOG[1]]
    _, _, bot = va.parse_log(lines, ["Victory"], "MirrorHub")
    assert list(np.diff(bot["Victory"][0]) > 0) == [True]


def test_intervals_merge_frames_by_the_gap_given():
    lt = np.arange(0, 3, 0.5)  # 2 frames a second
    assert len(va.intervals(lt, np.full(6, 0.9), 0.6, hub=[], hits=[])) == 6
    assert len(va.intervals(lt, np.full(6, 0.9), 0.6, hub=[], hits=[], gap=0.75)) == 1


def test_a_still_screen_the_bot_also_saw_still_is_not_a_freeze():
    vt = np.arange(0, 60, 0.1)
    still = (vt > 10) & (vt < 25) | (vt > 30) & (vt < 50)
    bt = np.arange(0, 60, 0.5)
    bs = np.where((bt > 10) & (bt < 25), 0.9, np.where(bt > 30, np.sin(bt), 0.1))  # stuck on Loading, then changing
    bs[(bt > 20) & (bt < 25)] = np.linspace(0.9, 0.1, 9)  # the Loading fades out at the end of the still stretch
    assert [(round(a), round(b)) for a, b in va.freezes(vt, still, {"Loading": (bt, bs)})] == [(30, 50)]


def test_intervals_count_hub_passes_and_the_first_hit():
    lt = np.arange(0, 10, 0.1)
    scores = np.where((lt >= 2) & (lt <= 3.5), 0.9, 0.1)
    rows = va.intervals(lt, scores, 0.6, hub=[1.0, 2.2, 2.9, 3.3, 5.0], hits=[3.0])
    assert rows == [{"up_at": 2.0, "up_s": 1.5, "hub_passes_while_up": 3, "passes_until_hit": 2,
                     "recognized": True, "hit_after_s": 1.0}]


def test_unaligned_frames_end_an_interval():
    lt = np.array([0.0, 0.1, np.nan, 0.3, 0.4])
    rows = va.intervals(lt, np.full(5, 0.9), 0.6, hub=[], hits=[])
    assert [(r["up_at"], r["up_s"]) for r in rows] == [(0.0, 0.1), (0.3, 0.1)]


LOG = [
    "[2026-10-19 21:14:00.100][DBG][Px1][Tx1][Recognizer.cpp][L1][MaaNS::TaskNS::PipelineTask::recognize_list] [cur_node_=MirrorHub] | enter\n",
    '[2026-10-19 21:14:00.200][DBG][Px1][Tx1][TemplateMatcher.cpp][L1][MaaNS::VisionNS::TemplateMatcher::analyze] Victory [all_results_=[{"box":[1,2,3,4],"score":0.912000}]]\n',
    '[2026-10-19 21:14:00.300][INF][Px1][Tx1][Utils/EventDispatcher.hpp][L65][x] [msg=Node.Recognition.Succeeded] [details={"focus":null,"name":"Victory","reco_details":{}}]\n',
    "no stamp on this line\n",
]


def test_parse_log_reads_hub_passes_hits_and_scores():
    hub, hits, bot = va.parse_log(LOG, ["Victory"], "MirrorHub")
    t0 = va.stamp("2026-10-19 21:14:00.100")
    assert [round(t - t0, 3) for t in hub] == [0.0]
    assert [round(t - t0, 3) for t in hits["Victory"]] == [0.2]
    assert [round(t - t0, 3) for t in bot["Victory"][0]] == [0.1] and list(bot["Victory"][1]) == [0.912]
