"""tools/live/hold.py: the state a hold keeps beside its ticket. What `queue.py status` makes of it, and `queue.py
pause` and `resume`, are in test_live_queue.py; the hold that writes it in test_live_backup.py."""
from live import hold as hl
from live import queue as lq


def test_a_state_reads_back_as_written_and_a_file_cut_short_as_none(tmp_path):
    ticket = tmp_path / "1-2-t.ticket"
    state = hl.State(tmp_path / "t/done", tmp_path / "t/bot*.log", 1500)
    hl.publish(hl.state_path(ticket), state)
    assert hl.state_path(ticket).name == "1-2-t.hold.json" and hl.read_state(ticket) == state
    assert sorted(p.name for p in tmp_path.iterdir()) == ["1-2-t.hold.json"]  # written aside, then put in place
    hl.publish(hl.state_path(ticket), hl.State(tmp_path / "t/done"))
    assert hl.read_state(ticket) == hl.State(tmp_path / "t/done", None, None)  # no guard, the wait not started or over
    hl.state_path(ticket).write_text('{"done": "x", ', encoding="utf-8")  # a write cut short
    assert hl.read_state(ticket) is None
    hl.part(hl.state_path(ticket)).write_text("{", encoding="utf-8")  # one a crash left aside
    hl.withdraw(hl.state_path(ticket))
    assert list(tmp_path.iterdir()) == [] and hl.read_state(ticket) is None
    assert hl.note(None) == "" and hl.stranded(None) is None


def test_a_state_that_cannot_be_written_leaves_the_hold_running(tmp_path):
    # a hand-cleared queue folder takes the ticket's folder with it; the hold must go on to its verify
    gone = tmp_path / "cleared" / "1-2-t.hold.json"
    hl.publish(gone, hl.State(tmp_path / "done", deadline=1500))
    hl.withdraw(gone)
    assert not gone.parent.exists()


def test_a_hold_outside_a_queue_has_no_state_file(tmp_path, monkeypatch):
    monkeypatch.delenv(lq.TICKET_ENV, raising=False)
    assert hl.own_state_path() is None
    hl.publish(None, hl.State(tmp_path / "done"))  # nothing to write, and no error
    hl.withdraw(None)
    monkeypatch.setenv(lq.TICKET_ENV, str(tmp_path / "1-2-t.ticket"))
    assert hl.own_state_path() == tmp_path / "1-2-t.hold.json"
