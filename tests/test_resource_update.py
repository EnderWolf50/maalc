"""The update of data/ from maalc-resource at TaskStart (#771, ADR 0012): what the install holds after a check, and what
the log says. The remote is a folder (tests/fake_resource.py), or an https source answered by a fake urlopen
for the failures only a network has."""

import importlib
import json
import os
import re
import threading
import types
import urllib.error
from pathlib import Path

import pytest

import resource_package as rp
import resource_update as ru
from fake_resource import install, publish, tree

OLD = {"data/a.json": b'{"a": 1}', "data/b.json": b'{"b": 1}', "data/gone.json": b"{}", "image/t.png": b"png-1"}
NEW = {"data/a.json": b'{"a": 2}', "data/b.json": b'{"b": 1}', "data/c/new.json": b'{"c": 1}', "image/t.png": b"png-1"}


@pytest.fixture
def remote(tmp_path):
    return tmp_path / "remote"


@pytest.fixture
def base(tmp_path, remote):
    base = tmp_path / "resource" / "base"
    install(base, OLD, "2026.11.01", [str(remote)])
    return base


class Job:
    def __init__(self, ok):
        self.succeeded = ok

    def wait(self):
        return self


class Tasker:
    """MaaFramework's side of a reload, as far as the update uses it: `resource.clear()` and `post_bundle(path).wait()`.
    `fail` names the calls that fail, by their number (1 = the first clear): a clear that returns False or a job that
    fails; `raises` the calls that raise. `loads` is the bundle's files as each post_bundle found them."""

    def __init__(self, fail=(), raises=()):
        self.fail, self.raises, self.calls, self.loads = set(fail), set(raises), [], []

    @property
    def resource(self):
        return self

    def step(self, name):
        self.calls.append(name)
        n = len(self.calls)
        if n in self.raises:
            raise RuntimeError("the library is gone")
        return n not in self.fail

    def clear(self):
        return self.step("clear")

    def post_bundle(self, path):
        ok = self.step("bundle")
        self.loads.append(local_files(Path(path)))
        return Job(ok)


def run(base, tasker=None):
    lines = []
    ru.update(base, lines.append, tasker or Tasker())
    return "\n".join(lines)


def local_files(base):
    return {k: v for k, v in tree(base).items() if k != "manifest.json"}


def test_a_newer_version_replaces_the_changed_files_adds_the_new_and_removes_the_gone(base, remote):
    publish(remote, NEW, "2026.11.16", client="1.119.0")
    said = run(base)
    assert local_files(base) == {**NEW, "image/t.png": OLD["image/t.png"]}
    manifest = rp.read_manifest(base)
    assert (manifest["version"], manifest["client"]) == ("2026.11.16", "1.119.0")
    assert manifest["sources"] == [str(remote)]  # a remote that lists none leaves the install's own
    assert "2026.11.01" in said and "2026.11.16" in said
    assert not (base.parent / ".update").exists()


def test_an_older_remote_leaves_everything(base, remote):
    publish(remote, NEW, "2026.10.30")
    before = tree(base)
    run(base)
    assert tree(base) == before


def test_the_same_files_under_a_newer_version_change_nothing_but_the_manifest_version(base, remote):
    publish(remote, OLD, "2026.11.16")
    run(base)
    assert local_files(base) == OLD and rp.read_manifest(base)["version"] == "2026.11.16"


def test_the_same_version_with_other_files_takes_the_published_ones(base, remote):
    # a release zip and a publish of one day share a version: the published one wins
    publish(remote, NEW, "2026.11.01")
    run(base)
    assert local_files(base)["data/a.json"] == NEW["data/a.json"]


def test_a_template_version_the_program_does_not_know_skips_image_and_pipeline_only(base, remote):
    # #772: data/ still updates; image/ and pipeline/ keep their files and manifest entries, and nothing is reloaded
    publish(remote, {**NEW, "image/t.png": b"png-2", "pipeline/p.json": b"{}"}, "2026.11.16", template=rp.TEMPLATE + 1)
    before = rp.read_manifest(base)
    tasker = Tasker()
    said = run(base, tasker)
    assert local_files(base) == {**NEW, "image/t.png": b"png-1"}
    manifest = rp.read_manifest(base)
    assert manifest["files"]["image/t.png"] == before["files"]["image/t.png"] and "pipeline/p.json" not in manifest["files"]
    assert (manifest["version"], manifest["template"], manifest["format"]) == ("2026.11.16", before["template"], rp.FORMAT)
    assert f"template {rp.TEMPLATE + 1}" in said and "image/ and pipeline/" in said and "skipped" in said
    assert tasker.calls == []


def test_a_template_the_program_knows_is_swapped_and_the_bundle_reloaded_once_on_the_new_files(base, remote):
    publish(remote, {**NEW, "image/t.png": b"png-2", "pipeline/p.json": b"{}"}, "2026.11.16")
    tasker = Tasker()
    said = run(base, tasker)
    assert tasker.calls == ["clear", "bundle"]  # the bundle is read after it is cleared, and the load is waited for
    assert tasker.loads == [{**NEW, "image/t.png": b"png-2", "pipeline/p.json": b"{}"}]  # the swapped files, not the old
    assert rp.read_manifest(base)["template"] == rp.TEMPLATE
    assert "2026.11.01 -> 2026.11.16" in said and "reloaded" in said


def test_a_change_of_data_only_reloads_nothing(base, remote):
    publish(remote, {**NEW, "image/t.png": b"png-1"}, "2026.11.16")
    tasker = Tasker()
    run(base, tasker)
    assert tasker.calls == []


@pytest.mark.parametrize("files, fields, reloaded", [
    ({**NEW, "image/t.png": b"png-2"}, {}, True),
    ({**NEW, "image/t.png": b"png-1"}, {}, False),  # data/ only
    ({**NEW, "image/t.png": b"png-2"}, {"template": rp.TEMPLATE + 1}, False),  # image/ skipped
])
def test_the_update_says_whether_it_reloaded_the_bundle(base, remote, files, fields, reloaded):
    # #779: TaskStart then takes the task's entry node, which the client's options override, from the reloaded bundle
    publish(remote, files, "2026.11.16", **fields)
    assert ru.update(base, lambda line: None, Tasker()) is reloaded


def test_a_refused_clear_leaves_the_bundle_loaded_so_the_old_files_are_not_loaded_again(base, remote):
    # clear() refused (a load is still running): the resource was not touched, the files go back and nothing is reloaded
    publish(remote, {**NEW, "image/t.png": b"png-2", "pipeline/p.json": b"{}"}, "2026.11.16")
    tasker = Tasker(fail=[1])
    before = tree(base)
    said = run(base, tasker)
    assert tree(base) == before and tasker.calls == ["clear"]
    assert "still loaded" in said and "could not be reloaded" not in said


@pytest.mark.parametrize("fault, calls", [
    (dict(fail=[2]), ["clear", "bundle", "clear", "bundle"]),  # the new bundle does not load
    (dict(raises=[2]), ["clear", "bundle", "clear", "bundle"]),
])
def test_a_reload_that_fails_puts_the_previous_files_back_and_loads_them_again(base, remote, fault, calls):
    tasker = Tasker(**fault)
    publish(remote, {**NEW, "image/t.png": b"png-2", "pipeline/p.json": b"{}"}, "2026.11.16")
    before = tree(base)
    said = run(base, tasker)
    assert tree(base) == before  # every part, data/ too: the version is one
    assert tasker.calls == calls
    assert tasker.loads[-1] == local_files(base)  # the second load is of the old files
    assert "reload" in said and "previous" in said and "2026.11.16" in said
    assert not (base.parent / ".update").exists()


def test_a_rolled_back_update_is_not_logged_as_done_when_a_cache_will_not_clear(base, remote, monkeypatch):
    publish(remote, {**NEW, "image/t.png": b"png-2"}, "2026.11.16")
    monkeypatch.setattr(ru, "clear_data_caches", lambda: 1 / 0)
    before = tree(base)
    said = run(base, Tasker(fail=[2]))
    assert tree(base) == before and "2026.11.01 -> 2026.11.16" not in said and "could not all be cleared" in said


def test_a_reload_that_fails_twice_says_so_and_the_task_goes_on(base, remote):
    publish(remote, {**NEW, "image/t.png": b"png-2"}, "2026.11.16")
    before = tree(base)
    said = run(base, Tasker(fail=[2, 4]))
    assert tree(base) == before and "could not" in said


@pytest.mark.parametrize("fault, reason", [
    (lambda r: (r / "2026.11.16" / "data" / "a.json").write_bytes(b'{"a": 9}'), "sha256"),
    (lambda r: (r / "2026.11.16" / "data" / "a.json").write_bytes(b'{"a"'), "interrupted"),
    (lambda r: (r / "2026.11.16" / "data" / "a.json").unlink(), "data/a.json"),
    (lambda r: (r / "main" / "manifest.json").write_text("{", encoding="utf-8"), "manifest"),
])
def test_a_download_that_fails_keeps_the_files_and_says_why(base, remote, fault, reason):
    publish(remote, NEW, "2026.11.16")
    fault(remote)
    before = tree(base)
    said = run(base)
    assert tree(base) == before
    assert reason in said and "kept the current files" in said
    assert not (base.parent / ".update").exists()


def test_a_source_that_cannot_be_reached_keeps_the_files_and_says_why(base, tmp_path):
    before = tree(base)
    said = run(base)  # the fixture's remote folder does not exist
    assert tree(base) == before and "kept the current files" in said and "remote" in said


def test_the_next_source_is_tried_when_the_first_fails(base, remote, tmp_path):
    publish(remote, NEW, "2026.11.16")
    manifest = rp.read_manifest(base)
    manifest["sources"] = [str(tmp_path / "nowhere"), str(remote)]
    (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run(base)
    assert local_files(base)["data/a.json"] == NEW["data/a.json"]


def test_a_format_the_program_does_not_know_is_skipped_and_logged(base, remote):
    publish(remote, NEW, "2026.11.16", format=rp.FORMAT + 1)
    before = tree(base)
    said = run(base)
    assert tree(base) == before  # the template part, which it applies, has nothing to change: the version stays too
    assert f"format {rp.FORMAT + 1}" in said and "skipped" in said


@pytest.mark.parametrize("path", ["data/../image/t.png", "data//x.json", "/data/x.json", "data\\x.json", "model/ocr/x.bin",
                                  "data/C:/x.json", "other/x.json", "data/A.JSON", "data/x.", "data/x /y.json"])
def test_a_path_outside_the_package_is_refused(base, remote, path):
    manifest = publish(remote, NEW, "2026.11.16")
    manifest["files"][path] = {"size": 1, "sha256": "0" * 64}  # only the manifest names it: not every system could hold the file
    (remote / "main" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = tree(base)
    said = run(base)
    assert tree(base) == before and path in said


@pytest.mark.parametrize("sources", [[], None])
def test_no_sources_or_no_manifest_turns_updates_off(base, remote, sources):
    publish(remote, NEW, "2026.11.16")
    if sources is None:
        (base / "manifest.json").unlink()
    else:
        manifest = rp.read_manifest(base)
        (base / "manifest.json").write_text(json.dumps({**manifest, "sources": sources}), encoding="utf-8")
    before = tree(base)
    said = run(base)
    assert tree(base) == before and "skipped" in said


def test_a_swap_that_fails_midway_puts_the_old_files_back(base, remote, monkeypatch):
    publish(remote, NEW, "2026.11.16")
    before = tree(base)
    real, calls = os.replace, []

    def replace(src, dst, *a):
        calls.append(dst)
        if len(calls) == 3:  # a file Windows holds
            raise PermissionError("held")
        return real(src, dst, *a)

    monkeypatch.setattr(os, "replace", replace)
    said = run(base)
    monkeypatch.undo()
    assert tree(base) == before and "kept the current files" in said


class Crash(BaseException):
    """The process ends: nothing runs after it, so no rollback."""


def replaces_until(monkeypatch, crash_at=None):
    """Count os.replace calls; the one numbered crash_at raises Crash. Returns the counter."""
    real, count = os.replace, {"n": 0}

    def replace(src, dst, *a):
        count["n"] += 1
        if count["n"] == crash_at:
            raise Crash
        return real(src, dst, *a)

    monkeypatch.setattr(os, "replace", replace)
    return count


def test_a_crash_at_any_point_of_the_swap_converges_on_the_next_run(base, remote, monkeypatch):
    publish(remote, NEW, "2026.11.16")
    expected = {**NEW, "image/t.png": OLD["image/t.png"]}
    count = replaces_until(monkeypatch)
    run(base)
    monkeypatch.undo()
    assert count["n"] >= 4
    for crash_at in range(1, count["n"] + 1):
        install(base, OLD, "2026.11.01", [str(remote)])
        for stale in set(local_files(base)) - set(OLD):
            (base / stale).unlink()
        replaces_until(monkeypatch, crash_at)
        with pytest.raises(Crash):
            ru.update(base, lambda line: None, Tasker())
        monkeypatch.undo()
        # the agent imports these at start: a crash must never leave one missing, whatever the next run does
        assert (base / "data" / "a.json").is_file() and (base / "data" / "b.json").is_file() and (base / "manifest.json").is_file()
        run(base)
        assert local_files(base) == expected, f"crash at replace #{crash_at}"
        assert rp.read_manifest(base)["version"] == "2026.11.16"
        assert not (base.parent / ".update").exists()


def test_a_staging_folder_a_crash_left_is_deleted(base, remote):
    publish(remote, NEW, "2026.11.16")
    left = base.parent / ".update" / "2026.11.16" / "data"
    left.mkdir(parents=True)
    (left / "a.json").write_bytes(b"half")
    run(base)
    assert not (base.parent / ".update").exists() and local_files(base)["data/a.json"] == NEW["data/a.json"]


URL = "https://maalc-resource.test/repo"


class Answer:
    """What urlopen returns: a body that ends early (`cut`) or fails midway (`reset`)."""

    def __init__(self, data, cut=False, reset=False):
        self.data, self.cut, self.reset = data, cut, reset

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n):
        if self.reset:
            raise ConnectionResetError("reset by peer")
        return self.data[: len(self.data) // 2] if self.cut else self.data[:n]


@pytest.fixture
def network(base, remote, monkeypatch):
    """urlopen answers from the remote folder as an https source; `trouble` says what goes wrong for which path."""
    manifest = rp.read_manifest(base)
    manifest["sources"] = [URL]
    (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    state = types.SimpleNamespace(trouble={}, release=threading.Event(), seen=[])

    def urlopen(request, timeout):
        rel = request.full_url.removeprefix(URL + "/")
        state.seen.append((rel, timeout))
        kind = next((v for k, v in state.trouble.items() if rel.endswith(k)), None)
        if kind == "stall":
            state.release.wait(10)  # the caller has given up long before
        if kind == "refuse":
            raise urllib.error.URLError(ConnectionRefusedError("refused"))
        if kind == "404":
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        return Answer((remote / rel).read_bytes(), cut=kind == "cut", reset=kind == "reset")

    monkeypatch.setattr(ru.urllib.request, "urlopen", urlopen)
    yield state
    state.release.set()


def test_the_files_come_over_https_too(base, remote, network):
    publish(remote, NEW, "2026.11.16")
    run(base)
    assert local_files(base)["data/a.json"] == NEW["data/a.json"]
    # the timeout is a deadline minus the clock, so it is 60 only up to float rounding
    assert network.seen[0][0] == "main/manifest.json" and ("2026.11.16/data/a.json", pytest.approx(60)) in network.seen


@pytest.mark.parametrize("trouble, reason", [
    ({"main/manifest.json": "stall"}, "timed out"),
    ({"main/manifest.json": "refuse"}, "cannot connect"),
    ({"main/manifest.json": "404"}, "HTTP 404"),
    ({"data/a.json": "cut"}, "interrupted"),
    ({"data/a.json": "reset"}, "interrupted"),
    ({"data/a.json": "stall"}, "timed out"),
    ({"data/c/new.json": "404"}, "HTTP 404"),
])
def test_a_network_failure_keeps_the_files_and_says_why(base, remote, network, monkeypatch, trouble, reason):
    publish(remote, NEW, "2026.11.16")
    network.trouble.update(trouble)
    monkeypatch.setattr(ru, "CHECK_SECONDS", 0.3)
    monkeypatch.setattr(ru, "DOWNLOAD_SECONDS", 0.3)
    before = tree(base)
    said = run(base)
    assert tree(base) == before and reason in said and "kept the current files" in said
    assert not (base.parent / ".update").exists()


def cache_decorated_functions():
    """module.function of every functools cache in agent/ that data/ can reach."""
    found = []
    for path in sorted(Path(ru.__file__).parent.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^@(?:functools\.)?(?:lru_)?cache(?:\([^)]*\))?\ndef (\w+)", text, re.M):
            found.append(f"{path.stem}.{m.group(1)}")
    return found


def test_every_cache_in_agent_is_cleared_with_the_data_or_named_as_not_on_it():
    # a new @cache that reads data/ must join ru.DATA_CACHES, or say here that it does not
    not_data = {"run_start._compact", "run_start._keywords"}
    assert set(cache_decorated_functions()) == set(ru.DATA_CACHES) | not_data


def test_every_function_that_rebuilds_a_table_made_at_import_exists():
    # a rename of one is a silent miss at the next update, so the names DERIVED lists are resolved here
    for name in ru.DERIVED:
        module, _, function = name.partition(".")
        assert callable(getattr(importlib.import_module(module), function)), name


def test_a_remote_that_lists_a_mirror_teaches_it_to_an_install_that_updates(base, remote, tmp_path):
    mirror = str(tmp_path / "mirror")
    publish(remote, NEW, "2026.11.16", sources=[str(remote), mirror])  # ADR 0012: an old zip learns a mirror at its next update
    run(base)
    assert rp.read_manifest(base)["sources"] == [str(remote), mirror]


def test_an_install_with_no_source_stays_off_whatever_the_remote_lists(tmp_path, remote):
    base = tmp_path / "dev" / "base"
    install(base, OLD, "2026.11.01", [])
    publish(remote, NEW, "2026.11.16", sources=[str(remote)])
    before = tree(base)
    run(base)
    assert tree(base) == before
