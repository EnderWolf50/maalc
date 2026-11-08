import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("live_watchdog", Path(__file__).resolve().parent.parent / "tools/live/watchdog.py")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)

ENCODED = "node:delegated-task:command%3Amcp%3Aabc%3Adelegate-task%3Aa"
DECODED = "node:delegated-task:command:mcp:abc:delegate-task:a"
THREAD = "mcp:launch:" + "0f" * 32
STRANDED = "  RUNNING live1 (pid 42) — bot ended 75 min ago, waiting for the agent: python backup.py hold"
CI_RED = json.dumps([{"conclusion": "failure", "headSha": "deadbeef0000"}])
CI_GREEN = json.dumps([{"conclusion": "success", "headSha": "cafebabe0000"}])


def tsv(tmp_path):
    return tmp_path / "agents.tsv"


def test_add_stores_the_id_as_given_and_hints_the_schedule_on_the_first_line(tmp_path):
    out = wd.add(tsv(tmp_path), ENCODED, "live1", "pack-test")
    assert any("switch the watchdog schedule ON" in l for l in out)
    assert f"{ENCODED}\tlive1\tpack-test" in tsv(tmp_path).read_text(encoding="utf-8").splitlines()
    out = wd.add(tsv(tmp_path), "other", "-", "second")
    assert not any("schedule" in l for l in out)


def test_add_twice_with_the_encoded_and_decoded_id_writes_one_line(tmp_path):
    wd.add(tsv(tmp_path), ENCODED, "live1", "a")
    out = wd.add(tsv(tmp_path), DECODED, "live1", "a")
    assert "already in the list" in out[0]
    assert len(wd.load(tsv(tmp_path))) == 1


def test_done_matches_by_label_or_either_id_form_and_hints_off_on_the_last_line(tmp_path):
    wd.add(tsv(tmp_path), ENCODED, "live1", "a")
    wd.add(tsv(tmp_path), "id2", "-", "b")
    assert "schedule" not in "".join(wd.done(tsv(tmp_path), DECODED))
    out = wd.done(tsv(tmp_path), "b")
    assert any("switch the watchdog schedule OFF" in l for l in out)
    assert wd.load(tsv(tmp_path)) == []


def test_done_on_an_unknown_ref_changes_nothing(tmp_path):
    wd.add(tsv(tmp_path), "id1", "-", "a")
    assert "no such line" in wd.done(tsv(tmp_path), "zzz")[0]
    assert len(wd.load(tsv(tmp_path))) == 1


def test_list_prints_lines_and_skips_the_header(tmp_path):
    assert wd.listing(tsv(tmp_path)) == ["(empty)"]
    wd.add(tsv(tmp_path), ENCODED, "live1", "a")
    assert wd.listing(tsv(tmp_path)) == [f"{ENCODED}\tlive1\ta\ttask_status"]


def test_list_names_t3_thread_read_for_a_launched_thread(tmp_path):
    wd.add(tsv(tmp_path), THREAD, "-", "b")
    assert wd.listing(tsv(tmp_path)) == [f"{THREAD}\t-\tb\tt3_thread_read"]


def rows():
    return [wd.Row(ENCODED, "live1", "a")]


def test_a_finished_task_is_reported_once_with_the_done_command():
    events, state = wd.tick(rows(), {DECODED: "completed"}, "", "", {}, "2026103012")
    assert len(events) == 1 and "FINISHED a" in events[0] and "watchdog.py done a" in events[0]
    events, _ = wd.tick(rows(), {DECODED: "completed"}, "", "", state, "2026103013")
    assert events == []


def test_a_task_whose_work_state_is_result_available_is_finished_and_a_working_one_is_not():
    for waiting in ("working", "waiting_for_children"):
        events, _ = wd.tick(rows(), {DECODED: waiting}, "", "", {}, "h")
        assert events == []
    events, _ = wd.tick(rows(), {DECODED: "result_available"}, "", "", {}, "h")
    assert events and events[0].startswith("FINISHED a")


def test_a_failed_task_is_resumed_once_per_hour():
    events, state = wd.tick(rows(), {DECODED: "failed"}, "", "", {}, "2026103012")
    assert "resume-a-2026103012" in events[0] and "queue.py resume --task live1" in events[0]
    assert wd.tick(rows(), {DECODED: "failed"}, "", "", state, "2026103012")[0] == []
    assert len(wd.tick(rows(), {DECODED: "failed"}, "", "", state, "2026103013")[0]) == 1


def test_a_cancelled_task_is_reported_once_as_cancelled_and_never_told_to_resume():
    for spelling in ("cancelled", "canceled"):
        events, state = wd.tick(rows(), {DECODED: spelling}, "", "", {}, "2026103012")
        assert len(events) == 1 and events[0].startswith("CANCELLED a")
        assert "resume-a" not in events[0] and "t3_thread_send" not in events[0]
        assert wd.tick(rows(), {DECODED: spelling}, "", "", state, "2026103013")[0] == []


def test_a_stranded_holder_of_a_cancelled_task_or_rolled_back_thread_is_not_told_to_resume():
    queue = "RUNNING live1 (pid 5) — bot ended 90 min ago, waiting for the agent\n"
    for row, status in ((wd.Row(ENCODED, "live1", "a"), "cancelled"), (wd.Row(THREAD, "live1", "b"), "rolled_back")):
        events, _ = wd.tick([row], {row.key(): status}, queue, "", {}, "h")
        stranded = [e for e in events if e.startswith("STRANDED")]
        assert len(stranded) == 1 and "resume" not in stranded[0].replace("not resume", "")


def test_a_running_task_and_a_missing_state_are_silent():
    assert wd.tick(rows(), {DECODED: "running"}, "", "", {}, "h")[0] == []
    assert wd.tick(rows(), {}, "", "", {}, "h")[0] == []


def threads():
    return [wd.Row(THREAD, "-", "b")]


def test_a_running_thread_is_silent():
    for working in ("preparing", "queued", "starting", "running"):
        assert wd.tick(threads(), {THREAD: working}, "", "", {}, "h")[0] == []


def test_a_completed_thread_that_reported_is_finished_once():
    events, state = wd.tick(threads(), {THREAD: "completed"}, "", "", {}, "h", reported_ids=[THREAD])
    assert len(events) == 1 and "FINISHED b" in events[0] and "watchdog.py done b" in events[0]
    assert wd.tick(threads(), {THREAD: "completed"}, "", "", state, "h", reported_ids=[THREAD])[0] == []


def test_a_finished_thread_stays_finished_when_a_later_tick_misses_its_reported_flag():
    _, state = wd.tick(threads(), {THREAD: "completed"}, "", "", {}, "h", [THREAD])
    assert wd.tick(threads(), {THREAD: "completed"}, "", "", state, "h")[0] == []


def test_a_stranded_holder_of_an_ended_thread_says_to_answer_its_question_not_to_resume():
    row = wd.Row(THREAD, "live1", "b")
    events, _ = wd.tick([row], {row.key(): "completed"}, STRANDED, "", {}, "h")
    stranded = [e for e in events if e.startswith("STRANDED")]
    assert len(stranded) == 1 and "answer it first" in stranded[0] and "tell b to resume" not in stranded[0]


def test_a_completed_thread_that_did_not_report_is_ended_once_until_it_runs_again():
    events, state = wd.tick(threads(), {THREAD: "completed"}, "", "", {}, "h")
    assert len(events) == 1 and events[0].startswith("ENDED b (completed)")
    assert "t3_thread_read" in events[0] and "watchdog.py done b" in events[0]
    events, state = wd.tick(threads(), {THREAD: "completed"}, "", "", state, "h")
    assert events == []
    events, state = wd.tick(threads(), {THREAD: "running"}, "", "", state, "h")
    assert events == []
    events, _ = wd.tick(threads(), {THREAD: "completed"}, "", "", state, "h")
    assert len(events) == 1 and events[0].startswith("ENDED b")


def test_an_interrupted_or_failed_thread_is_told_to_resume_once_per_hour_even_after_running():
    for status in ("interrupted", "failed"):
        events, state = wd.tick(threads(), {THREAD: status}, "", "", {}, "2026103012")
        assert len(events) == 1 and events[0].startswith(f"FAILED b ({status})")
        assert "resume-b-2026103012" in events[0] and "queue.py resume --task b" in events[0]
        _, state = wd.tick(threads(), {THREAD: "running"}, "", "", state, "2026103012")
        assert wd.tick(threads(), {THREAD: status}, "", "", state, "2026103012")[0] == []
        assert len(wd.tick(threads(), {THREAD: status}, "", "", state, "2026103013")[0]) == 1


def test_a_cancelled_or_rolled_back_thread_is_reported_as_cancelled():
    for status in ("cancelled", "rolled_back"):
        events, _ = wd.tick(threads(), {THREAD: status}, "", "", {}, "h")
        assert len(events) == 1 and events[0].startswith("CANCELLED b")


def test_a_holder_stranded_over_an_hour_is_reported_once_and_a_short_one_is_not():
    events, state = wd.tick([wd.Row("i", "live1", "a")], {}, STRANDED, "", {}, "h")
    assert "STRANDED holder live1" in events[0] and "tell a to resume" in events[0]
    assert wd.tick(rows(), {}, STRANDED, "", state, "h")[0] == []
    short = STRANDED.replace("75 min", "20 min")
    assert wd.tick(rows(), {}, short, "", {}, "h")[0] == []


def test_a_stranded_holder_nobody_owns_goes_to_the_user():
    events, _ = wd.tick([], {}, STRANDED, "", {}, "h")
    assert "report it to the user" in events[0]


def test_main_red_is_reported_once_and_green_only_after_a_red_report():
    assert wd.tick([], {}, "", CI_GREEN, {}, "h")[0] == []
    events, state = wd.tick([], {}, "", CI_RED, {}, "h")
    assert "MAIN RED at deadbeef" in events[0]
    assert wd.tick([], {}, "", CI_RED, state, "h")[0] == []
    events, state = wd.tick([], {}, "", CI_GREEN, state, "h")
    assert "MAIN GREEN again" in events[0]
    assert wd.tick([], {}, "", CI_GREEN, state, "h")[0] == []


def test_an_unreadable_ci_answer_is_silent():
    assert wd.tick([], {}, "", "not json", {}, "h")[0] == []
    assert wd.tick([], {}, "", "", {}, "h")[0] == []


def test_a_task_or_thread_that_left_the_list_can_be_reported_again():
    for listed, statuses in ((rows(), {DECODED: "completed"}), (threads(), {THREAD: "completed"})):
        _, state = wd.tick(listed, statuses, "", "", {}, "h")
        _, state = wd.tick([], {}, "", "", state, "h")
        assert wd.tick(listed, statuses, "", "", state, "h")[0]


def test_parse_statuses_decodes_the_id():
    assert wd.parse_statuses([f"{ENCODED}=completed"]) == {DECODED: "completed"}


def test_cli_tick_prints_news_once_then_nothing_new(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wd, "queue_status", lambda: "")
    monkeypatch.setattr(wd, "main_ci", lambda: CI_RED)
    base = ["--dir", str(tmp_path)]
    wd.main(base + ["add", ENCODED, "live1", "a"])
    capsys.readouterr()
    wd.main(base + ["tick", "--status", f"{ENCODED}=completed"])
    first = capsys.readouterr().out
    assert "FINISHED a" in first and "MAIN RED" in first
    wd.main(base + ["tick", "--status", f"{ENCODED}=completed"])
    assert capsys.readouterr().out.strip() == "NOTHING NEW"
    assert (tmp_path / "agents.state.json").exists()


def test_cli_tick_reads_a_reported_thread_as_finished(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wd, "queue_status", lambda: "")
    monkeypatch.setattr(wd, "main_ci", lambda: "")
    base = ["--dir", str(tmp_path)]
    wd.main(base + ["add", THREAD, "-", "b"])
    capsys.readouterr()
    wd.main(base + ["tick", "--status", f"{THREAD}=completed", "--reported", THREAD])
    assert capsys.readouterr().out.startswith("FINISHED b")


def test_the_sh_helper_returns_empty_for_a_failing_command():
    assert wd.sh(["python", "-c", "import sys; sys.exit(3)"]) == ""
    assert wd.sh(["python", "-c", "print('x')"]).strip() == "x"
