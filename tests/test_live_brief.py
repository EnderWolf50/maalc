import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("live_brief", Path(__file__).resolve().parent.parent / "tools/live/brief.py")
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)

LIVE = ["live", "--task", "t1", "--difficulty", "normal", "--exp-count", "1", "--thread-count", "3",
        "--weekly-bonus", "none", "--recording", "yes"]


def run(tmp_path, args):
    return brief.main(["--scratch", str(tmp_path), *args])


def test_live_brief_states_every_setting_from_the_arguments(tmp_path):
    assert run(tmp_path, LIVE) == 0
    text = (tmp_path / "t1" / "brief.md").read_text(encoding="utf-8")
    assert "docs/agents/subagent-preamble.md" in text
    assert "maalc-live-test" in text and "screen-record" in text
    assert "| difficulty | normal |" in text
    assert "| weekly bonus use | none |" in text
    assert "| recording | yes |" in text and "--height 720" in text
    assert "kept on from the start of the run to its end" in text and "recording.md" in text  # no stall rule (2026-11-05)
    assert "queue.py detach" in text and "Report" in text
    assert "## Goal" in text


def test_a_different_count_is_never_inherited_from_an_earlier_brief(tmp_path):
    run(tmp_path, LIVE)
    run(tmp_path, ["live", "--task", "t2", "--difficulty", "hard", "--exp-count", "2", "--thread-count", "5",
                   "--thread-mode", "count", "--weekly-bonus", "hard", "--recording", "no", "--force"])
    text = (tmp_path / "t2" / "brief.md").read_text(encoding="utf-8")
    assert "luxcavation.exp.count=2" in text and "| EXP Luxcavation count | 2, not used:" in text
    assert "| Thread Luxcavation count | 5 |" in text and "--set luxcavation.thread.mode=count --set luxcavation.thread.count=5" in text
    assert "| weekly bonus use | hard |" in text
    assert "| recording | no |" in text and "screenrec.py start" not in text and "Do not record" in text


def settings_of(tmp_path, *extra):
    run(tmp_path, [*LIVE, *extra])
    return (tmp_path / "t1" / "brief.md").read_text(encoding="utf-8")


def test_count_mode_states_its_count_and_sets_mode_and_count(tmp_path):
    text = settings_of(tmp_path, "--exp-mode", "count", "--exp-count", "2")
    assert "| EXP Luxcavation mode | count |" in text and "| EXP Luxcavation count | 2 |" in text
    assert "--set luxcavation.exp.mode=count --set luxcavation.exp.count=2" in text


def test_daily_mode_marks_its_count_unused_and_says_what_it_fights(tmp_path):
    text = settings_of(tmp_path, "--thread-mode", "daily", "--exp-mode", "daily")
    assert "| Thread Luxcavation mode | daily |" in text and "| EXP Luxcavation mode | daily |" in text
    thread = next(line for line in text.splitlines() if line.startswith("| Thread Luxcavation count |"))
    exp = next(line for line in text.splitlines() if line.startswith("| EXP Luxcavation count |"))
    assert thread.startswith("| Thread Luxcavation count | 3, not used: daily mode") and "Daily Bonuses" in thread
    assert exp.startswith("| EXP Luxcavation count | 1, not used: daily mode") and "Clear EXP Luxcavation" in exp
    assert "--set luxcavation.thread.mode=daily --set luxcavation.thread.count=3" in text


def test_the_mode_defaults_to_daily_as_the_schema_does(tmp_path):
    text = settings_of(tmp_path)
    assert "--set luxcavation.exp.mode=daily" in text and "--set luxcavation.thread.mode=daily" in text


def test_a_mode_outside_the_schema_is_not_an_option(tmp_path):
    assert run(tmp_path, [*LIVE, "--exp-mode", "count"]) == 0
    with pytest.raises(SystemExit):
        run(tmp_path, [*LIVE, "--exp-mode", "today"])


def test_the_run_settings_are_required(tmp_path):
    with pytest.raises(SystemExit):
        run(tmp_path, ["live", "--task", "t1", "--difficulty", "normal"])


def test_a_weekly_bonus_on_normal_is_not_an_option(tmp_path):
    with pytest.raises(SystemExit):
        run(tmp_path, [*LIVE[:-4], "--weekly-bonus", "normal", "--recording", "yes"])


def test_an_existing_brief_is_kept_without_force(tmp_path):
    run(tmp_path, LIVE)
    path = tmp_path / "t1" / "brief.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nmy goal text\n", encoding="utf-8")
    assert run(tmp_path, LIVE) == 1
    assert "my goal text" in path.read_text(encoding="utf-8")


def test_no_literal_backslash_n_and_no_unfilled_placeholder(tmp_path):
    run(tmp_path, LIVE)
    text = (tmp_path / "t1" / "brief.md").read_text(encoding="utf-8")
    assert "\\n" not in text and "{" not in text


def test_local_rules_file_is_appended_when_it_exists(tmp_path):
    rules = tmp_path / "rules.md"
    rules.write_text("Never do X on this machine.\n", encoding="utf-8")
    run(tmp_path, ["--rules", str(rules), *LIVE])
    assert "Never do X on this machine." in (tmp_path / "t1" / "brief.md").read_text(encoding="utf-8")
    run(tmp_path, ["--rules", str(tmp_path / "missing.md"), *LIVE[:2], "t3", *LIVE[3:]])
    assert "Machine-local rules" not in (tmp_path / "t3" / "brief.md").read_text(encoding="utf-8")


def test_code_brief_has_no_emulator_section(tmp_path):
    assert run(tmp_path, ["code", "--task", "c1"]) == 0
    text = (tmp_path / "c1" / "brief.md").read_text(encoding="utf-8")
    assert "maalc-live-test" not in text and "tdd" in text and "bench" in text
    assert "not run live" in text
