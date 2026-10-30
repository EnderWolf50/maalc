"""tools/live/preflight.py: the screen verdicts on the pipeline's own fixtures, the recording and run-plan checks on fake files."""
import importlib.util
import re
from pathlib import Path

import pytest

from test_pipeline import load_nodes

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("preflight", REPO / "tools/live/preflight.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


def config_cases() -> dict[str, list[str]]:
    """image -> the nodes maatools.config.mts expects to hit on it."""
    text = "\n".join(l for l in (REPO / "maatools.config.mts").read_text(encoding="utf-8").splitlines() if not l.strip().startswith("//"))
    return {m[1]: re.findall(r"'(\w+)'", m[2]) for m in re.finditer(r"\['([\w.]+\.png)', \[(.*?)\]\]", text)}


def test_every_screen_node_is_a_pipeline_node():
    assert set(pf.SCREENS) <= set(load_nodes())


@pytest.mark.parametrize("image, verdict", [
    ("MainWindow.png", "ok"),
    ("MainWindowLater.png", "ok"),
    ("TitleDownload.png", "accept"),
    ("UserAgreement.png", "accept"),
    ("UpdateDialog.synthetic.png", "accept"),
    ("ResumeDialog.png", "stop"),
    ("EntryPaused.png", "stop"),
    ("TitleClientOutdated.png", "stop"),
    ("Drive.png", "stop"),
    ("TeamSelect.png", "stop"),
])
def test_the_verdict_on_a_live_capture_follows_the_nodes_the_config_expects_to_hit(image, verdict):
    hits = config_cases()[image]
    probe_order = [n for n in pf.SCREENS if n in hits]  # the probe tries SCREENS in order; the first hit names the screen
    assert pf.classify(pf.first_hit(probe_order))[0] == verdict


def test_a_screen_no_known_node_reads_is_a_stop_with_a_reason():
    verdict, reason = pf.classify(None)
    assert verdict == "stop" and "screenshot" in reason


def test_the_probe_tries_dialogs_before_the_main_screen_and_switches_every_action_off():
    o = pf.probe_override()
    assert o[pf.PROBE]["next"] == list(pf.SCREENS) and list(pf.SCREENS).index("UpdateDialog") < list(pf.SCREENS).index("HomeReached")
    assert all(o[n]["action"] == "DoNothing" and o[n]["next"] == [] for n in pf.SCREENS)


def test_screen_exits_nonzero_only_on_stop(tmp_path):
    said = []
    assert pf.screen(tmp_path, 1, None, say=said.append, see=lambda *a: "HomeReached") == 0
    assert pf.screen(tmp_path, 1, None, say=said.append, see=lambda *a: "UpdateDialog") == 0 and said[-1].startswith("accept")
    assert pf.screen(tmp_path, 1, None, say=said.append, see=lambda *a: "ResumeDialog") == 1 and said[-1].startswith("stop")


def test_a_recording_that_stops_growing_is_reported(tmp_path):
    said = []
    assert pf.recording_grows(tmp_path, 1, say=said.append, sleep=lambda s: None) == 1 and "did not start" in said[-1]
    rec = tmp_path / "rec_1.mp4"
    rec.write_bytes(b"x" * 10)
    assert pf.recording_grows(tmp_path, 1, say=said.append, sleep=lambda s: rec.write_bytes(b"x" * 99)) == 0
    assert pf.recording_grows(tmp_path, 1, say=said.append, sleep=lambda s: None) == 1 and "asleep" in said[-1]


def test_a_recording_in_progress_is_an_mkv(tmp_path):
    # screenrec writes rec_<profile>_<date>_<time>.mkv while it records and remuxes it to .mp4 only at stop
    said = []
    (tmp_path / "rec_old_20261029_100000.mp4").write_bytes(b"x" * 500)
    rec = tmp_path / "rec_preflight_20261030_043630.mkv"
    rec.write_bytes(b"x" * 10)
    assert pf.recording_grows(tmp_path, 1, say=said.append, sleep=lambda s: rec.write_bytes(b"x" * 99)) == 0, said


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def plan(tmp_path, text, within=60):
    log, said, clock = tmp_path / "run.log", [], Clock()
    log.write_text(text, encoding="utf-8")
    return pf.plan_line(log, within, say=said.append, clock=clock.now, sleep=clock.sleep), said, clock


def test_the_run_plan_line_passes(tmp_path):
    code, said, _ = plan(tmp_path, "10:00:01.000 [maalc] new run: normal, team 'A' (TEAMS #1), weekly bonuses left 3, time limit 20 min a floor\n")
    assert code == 0 and said[-1].startswith("ok:")


def test_a_leftover_run_without_a_plan_stops_at_once(tmp_path):
    code, said, clock = plan(tmp_path, "10:00:01.000 [maalc] no run plan in memory: assuming team 'A', difficulty unknown, no guard turns\n")
    assert code == 1 and clock.t == 0 and "leftover run" in said[-1]


OLD_RUN = ("10:00:00.000 [run] child pid 1\n"
           "10:00:02.000 [maalc] new run: normal, team 'A' (TEAMS #1), weekly bonuses left 3, time limit 20 min a floor\n")
PLAN = "[maalc] new run: hard, team 'A' (TEAMS #1), weekly bonuses left 3, time limit 20 min a floor\n"


def test_a_plan_line_of_an_earlier_bot_run_in_the_same_log_is_not_this_runs(tmp_path):
    code, said, clock = plan(tmp_path, OLD_RUN + "11:00:00.000 [run] child pid 2\n11:00:01.000 [maalc] stuck: something\n")
    assert code == 1 and clock.t >= 60 and "no line matching" in said[-1]
    code, said, _ = plan(tmp_path, OLD_RUN + "11:00:00.000 [run] child pid 2\n11:00:01.000 [maalc] no run plan in memory: x\n")
    assert code == 1 and "no run plan" in said[-1]


def test_an_earlier_runs_no_plan_line_does_not_stop_a_planned_run(tmp_path):
    old = "10:00:00.000 [run] child pid 1\n10:00:02.000 [maalc] no run plan in memory: x\n"
    assert plan(tmp_path, old + "11:00:00.000 [run] child pid 2\n11:00:01.000 " + PLAN)[0] == 0


def test_only_the_plan_line_counts_not_the_other_new_run_lines(tmp_path):
    code, _, clock = plan(tmp_path, "10:00:01.000 [maalc] new run: the Modules were not read on the way here\n10:00:02.000 [maalc] new run: Modules 12 >= 5\n")
    assert code == 1 and clock.t >= 60


def test_screen_makes_the_folder_of_its_shot(tmp_path):
    shot = tmp_path / "new-topic" / "00-start.png"
    seen = []
    pf.screen(tmp_path, 1, shot, say=lambda *_: None, see=lambda root, port, s: seen.append(s.parent.is_dir()) or "HomeReached")
    assert seen == [True]


def test_no_plan_line_in_time_stops_after_the_wait(tmp_path):
    code, said, clock = plan(tmp_path, "10:00:01.000 [maalc] stuck: something\n", within=60)
    assert code == 1 and clock.t >= 60 and "no line matching" in said[-1]
