"""tools/publish_resource.py (#770): the version a publish gets, when nothing is published, and the publish itself into a
repository (a local bare one stands in for maalc-resource)."""

import json
import subprocess

import pytest

import publish_resource as pub
import resource_package as rp

DAY = "2026.11.16"
FILES = {"data/a.json": {"size": 2, "sha256": "aa"}, "image/b.png": {"size": 3, "sha256": "bb"}}


def test_the_first_publish_of_a_day_is_the_date():
    assert pub.next_version(["2026.11.15", "2026.11.14.2"], DAY) == "2026.11.16"
    assert pub.next_version([], DAY) == "2026.11.16"


def test_later_publishes_of_the_day_count_up_from_two():
    assert pub.next_version(["2026.11.16"], DAY) == "2026.11.16.2"
    assert pub.next_version(["2026.11.16", "2026.11.16.2"], DAY) == "2026.11.16.3"


def test_the_counter_compares_as_a_number_not_as_text():
    tags = ["2026.11.16"] + [f"2026.11.16.{n}" for n in range(2, 10)]
    assert pub.next_version(tags, DAY) == "2026.11.16.10"
    assert pub.next_version([*tags, "2026.11.16.10"], DAY) == "2026.11.16.11"


def test_tags_that_are_not_versions_are_ignored():
    assert pub.next_version(["v1.2", "latest", "2026.11.16-rc", "2026.11.16"], DAY) == "2026.11.16.2"
    assert pub.latest_tag(["v1.2", "latest"]) is None


def test_the_latest_tag_is_the_highest_version():
    assert pub.latest_tag(["2026.11.16.2", "2026.11.16", "2026.11.9", "2026.10.30.3"]) == "2026.11.16.2"


def test_a_tag_dated_after_today_stops_the_publish_instead_of_numbering_backwards():
    with pytest.raises(SystemExit, match="2026.11.17"):
        pub.next_version(["2026.11.17"], DAY)


def test_same_files_publish_nothing():
    assert not pub.should_publish(dict(FILES), dict(FILES))


@pytest.mark.parametrize("change", [
    lambda f: f.pop("image/b.png"),
    lambda f: f.update({"data/new.json": {"size": 1, "sha256": "cc"}}),
    lambda f: f.update({"data/a.json": {"size": 2, "sha256": "zz"}}),
    lambda f: f.update({"data/a.json": {"size": 9, "sha256": "aa"}}),
])
def test_any_changed_added_or_removed_file_publishes(change):
    new = json.loads(json.dumps(FILES))
    change(new)
    assert pub.should_publish(FILES, new)


def test_nothing_published_yet_publishes():
    assert pub.should_publish(None, FILES)


# --- the publish itself, against a local bare repository


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_base(root, **overrides):
    files = {"data/client.json": b'{"client": "1.118.1"}', "data/a.json": b"{}", "image/x.png": b"png",
             "pipeline/p.json": b"{}", "model/ocr/det.onnx": b"model", **overrides}
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if data is None:
            path.unlink()
        else:
            path.write_bytes(data)
    return root


@pytest.fixture
def setup(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "--bare", "-b", "main", str(remote))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "LICENSE").write_text("license", encoding="utf-8")
    (repo / "NOTICE.md").write_text("notice", encoding="utf-8")
    return remote, repo, make_base(tmp_path / "base"), tmp_path / "work"


def publish(setup, day=DAY, **kw):
    remote, repo, base, work = setup
    return pub.publish(base, work, str(remote), day, sources=["https://example.test/r"], repo=repo, **kw)


def published(remote, ref):
    """The files of `ref` in the bare repository."""
    return git("-C", str(remote), "ls-tree", "-r", "--name-only", ref).splitlines()


def test_the_first_publish_pushes_one_package_with_license_notice_manifest_and_a_tag(setup):
    remote, *_ = setup
    assert publish(setup) == DAY
    assert published(remote, "main") == ["LICENSE", "NOTICE.md", "data/a.json", "data/client.json", "image/x.png",
                                         "manifest.json", "pipeline/p.json"]  # no model/
    assert git("-C", str(remote), "tag") == DAY
    assert git("-C", str(remote), "rev-parse", f"{DAY}^{{commit}}") == git("-C", str(remote), "rev-parse", "main")
    assert git("-C", str(remote), "rev-list", "--count", "main") == "1"
    manifest = json.loads(git("-C", str(remote), "show", "main:manifest.json"))
    assert manifest["version"] == DAY and manifest["client"] == "1.118.1" and manifest["sources"] == ["https://example.test/r"]
    assert rp.check_manifest(manifest)


def test_the_manifest_hashes_match_the_published_files(setup, tmp_path):
    remote, *_ = setup
    publish(setup)
    check = tmp_path / "check"
    git("clone", "--branch", DAY, str(remote), str(check))
    manifest = rp.read_manifest(check)
    assert sorted(manifest["files"]) == ["data/a.json", "data/client.json", "image/x.png", "pipeline/p.json"]
    for name, entry in manifest["files"].items():
        assert rp.sha256_file(check / name) == entry["sha256"] and (check / name).stat().st_size == entry["size"]


def test_an_unchanged_package_publishes_nothing(setup):
    remote, *_ = setup
    publish(setup)
    assert publish(setup, day="2026.11.17") is None
    assert git("-C", str(remote), "tag") == DAY
    assert git("-C", str(remote), "rev-list", "--count", "main") == "1"


def test_a_changed_file_the_same_day_is_the_second_version_in_one_more_commit(setup):
    remote, _, base, _ = setup
    publish(setup)
    make_base(base, **{"data/a.json": b'{"new": 1}'})
    assert publish(setup) == "2026.11.16.2"
    assert git("-C", str(remote), "tag", "--sort=version:refname").splitlines() == [DAY, "2026.11.16.2"]
    assert git("-C", str(remote), "rev-list", "--count", "main") == "2"


def test_main_holds_exactly_one_package_so_a_removed_file_is_gone(setup):
    remote, _, base, _ = setup
    publish(setup)
    make_base(base, **{"image/x.png": None})
    publish(setup, day="2026.11.17")
    assert "image/x.png" not in published(remote, "main")
    assert "image/x.png" in published(remote, DAY)  # the old tag still serves the old package


def test_a_stray_file_in_the_remote_is_not_carried_over(setup, tmp_path):
    remote, *_ = setup
    publish(setup)
    other = tmp_path / "other"
    git("clone", str(remote), str(other))
    (other / "stray.txt").write_text("x", encoding="utf-8")
    git("-C", str(other), "add", ".")
    git("-C", str(other), "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-m", "stray")
    git("-C", str(other), "push", "origin", "main")
    make_base(setup[2], **{"data/a.json": b"[]"})
    publish(setup, day="2026.11.17")
    assert "stray.txt" not in published(remote, "main")


def test_a_rerun_in_a_used_work_folder_still_works(setup):
    publish(setup)
    make_base(setup[2], **{"data/a.json": b"[]"})
    assert publish(setup, day="2026.11.17") == "2026.11.17"


def test_a_changed_license_or_notice_publishes_a_new_version(setup):
    remote, repo, *_ = setup
    publish(setup)
    (repo / "NOTICE.md").write_text("notice, corrected", encoding="utf-8")
    assert publish(setup) == "2026.11.16.2"
    assert git("-C", str(remote), "show", "main:NOTICE.md") == "notice, corrected"


def test_a_changed_source_list_or_format_publishes_though_no_file_changed(setup):
    publish(setup)
    remote, repo, base, work = setup
    assert pub.publish(base, work, str(remote), DAY, sources=["https://example.test/other"], repo=repo) == "2026.11.16.2"


def test_the_workflow_runs_on_every_path_the_package_is_built_from():
    import yaml

    from install import repo as root

    flow = yaml.safe_load((root / ".github/workflows/publish-resource.yml").read_text(encoding="utf-8"))
    paths = flow[True]["push"]["paths"]  # PyYAML reads the key `on` as True
    for part in rp.PARTS:
        assert f"assets/resource/base/{part}/**" in paths
    for name in pub.EXTRA:
        assert name in paths
    assert flow["concurrency"]["cancel-in-progress"] is False and "workflow_dispatch" in flow[True]
