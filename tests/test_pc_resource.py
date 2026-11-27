"""The PC resource layer (#944, ADR 0017): assets/resource/pc, loaded after base on a PC run only (runner/layers.py), and
loaded again after a hot update's reload (agent/resource_update.py; the reload itself is tested in test_task_chain.py).

The loads run MaaFramework's own Resource. The pytest process holds MaaFramework in AgentServer mode, so they run in a
child process: this file run as a script, as test_task_chain.py does.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"  # laid out as an install's <root>: resource/base, resource/pc
LAYER = ASSETS / "resource" / "pc"
STEAM = "the game has an update: update it in Steam, then start the bot again"

if __name__ != "__main__":
    import build_resource_package as brp
    import reasons
    import resource_update
    from test_pipeline import load_nodes
    from install import mirror_repo, write_resource_manifest
    from test_pc import ONE, Desk, game, pc_world
    from test_runner import TWO, Run, World

    from runner import layers


def child():
    """Print what three Resources hold: base alone (main's load), and the bundles of an emulator run and of a PC run."""
    from maa.resource import Resource

    sys.path.insert(0, str(ROOT))
    from runner import layers

    out = {}
    for name, bundles in (("main", [ASSETS / "resource" / "base"]), ("emulator", layers.bundles(ASSETS, "emulator")),
                          ("pc", layers.bundles(ASSETS, "pc"))):
        resource = Resource()
        loaded = [resource.post_bundle(str(b)).wait().succeeded for b in bundles]
        out[name] = {"loaded": loaded, "nodes": {n: resource.get_node_data(n) for n in sorted(resource.node_list)}}
    print(json.dumps(out))


@pytest.fixture(scope="module")
def loads():
    done = subprocess.run([sys.executable, __file__], capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def templates(bundles):
    """The template images the bundles hold, by their path under image/."""
    return sorted(p.relative_to(b / "image").as_posix() for b in bundles if (b / "image").is_dir()
                  for p in (b / "image").rglob("*") if p.is_file())


def test_an_emulator_run_loads_main_bundle_alone_with_its_nodes_and_templates(loads):
    assert layers.bundles(ASSETS, "emulator") == [ASSETS / "resource" / "base"]
    assert templates(layers.bundles(ASSETS, "emulator")) == templates([ASSETS / "resource" / "base"])
    assert loads["emulator"]["loaded"] == [True] and loads["emulator"]["nodes"] == loads["main"]["nodes"]


def test_a_pc_run_loads_the_layer_after_base_and_its_node_takes_the_place_of_bases_of_that_name(loads):
    assert layers.bundles(ASSETS, "pc") == [ASSETS / "resource" / "base", LAYER]
    main, pc = loads["main"]["nodes"], loads["pc"]["nodes"]
    assert loads["pc"]["loaded"] == [True, True] and sorted(pc) == sorted(main)
    changed = sorted(n for n in main if pc[n] != main[n])
    assert changed == sorted(load_nodes(folder=LAYER / "pipeline")) == ["UpdateDialog"]
    # the layer writes the action alone: the recognition and every other field are base's
    assert {k: v for k, v in pc["UpdateDialog"].items() if k != "action"} == {k: v for k, v in main["UpdateDialog"].items() if k != "action"}
    assert main["UpdateDialog"]["action"]["param"]["custom_action"] == "AcceptUpdate"
    action = pc["UpdateDialog"]["action"]
    assert (action["type"], action["param"]["custom_action"], action["param"]["custom_action_param"]) == ("Custom", "Halt", STEAM)


def test_each_node_of_the_layer_is_a_base_node_and_each_stop_has_a_code():
    # a base node renamed would leave the layer's node one of its own, which nothing reaches
    nodes = load_nodes(folder=LAYER / "pipeline")
    assert nodes and sorted(set(nodes) - set(load_nodes())) == []
    stops = [n for n, spec in nodes.items() if spec.get("custom_action") in ("StopTask", "Halt")]
    assert stops == ["UpdateDialog"] and [n for n in stops if n not in reasons.CODES] == []
    assert "Steam" in reasons.CODES["UpdateDialog"]["zh_tw"] and "Steam" in reasons.CODES["UpdateDialog"]["en_us"]


def test_the_layer_holds_only_nodes_and_templates_as_a_bundle_does():
    assert sorted(p.name for p in LAYER.iterdir()) == ["pipeline"]  # templates go in image/ when one is needed


def test_the_install_holds_the_layer_and_the_resource_package_does_not(tmp_path):
    # the zip is install/ (release.yml, test_release_zip.py); the package is base's data/, image/ and pipeline/ (ADR 0012)
    repo, root = tmp_path / "repo", tmp_path / "install"
    for name in ("agent/main.py", "runner/__main__.py", "assets/interface.json", "assets/resource/base/data/client.json", "assets/resource/base/pipeline/a.json",
                 "assets/resource/pc/pipeline/popups.json"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text('{"client": "1.118.1"}', encoding="utf-8")
    mirror_repo(repo, root, "./python/python.exe")
    write_resource_manifest(root, release=True)
    assert (root / "resource/pc/pipeline/popups.json").is_file()
    assert sorted(brp.rp.read_manifest(root / "resource" / "base")["files"]) == ["data/client.json", "pipeline/a.json"]
    assert not any(LAYER in path.parents for path in brp.package_files(ASSETS / "resource" / "base").values())


@pytest.mark.parametrize("kind, bundles", [("emulator", ["base"]), ("pc", ["base", "pc"])])
def test_the_bot_reloads_the_bundles_its_runner_loaded(monkeypatch, tmp_path, kind, bundles):
    # the bot is started with the runner's agent_env; runner/ does not import agent/, so the two spellings meet here
    assert resource_update.LAYERS_ENV == layers.LAYERS_ENV
    monkeypatch.delenv(layers.LAYERS_ENV, raising=False)
    assert resource_update.bundles(tmp_path / "resource" / "base") == [tmp_path / "resource" / "base"]  # a bot of no runner
    for name, value in layers.agent_env(layers.bundles(tmp_path, kind)).items():
        monkeypatch.setenv(name, value)
    base = tmp_path / "resource" / "base"
    assert resource_update.bundles(base) == layers.bundles(tmp_path, kind) == [tmp_path / "resource" / b for b in bundles]


@pytest.mark.parametrize("world, device, names", [
    (lambda: World(ONE), {}, ["base"]),
    (lambda: pc_world(ONE, Desk(game())), {"kind": "pc", "address": None}, ["base", "pc"]),
], ids=["emulator", "pc"])
def test_a_run_loads_the_bundles_of_its_device_kind_and_hands_their_names_to_its_bot(monkeypatch, tmp_path, world, device, names):
    monkeypatch.delenv(layers.LAYERS_ENV, raising=False)
    world = world()
    run = Run(tmp_path, world)
    script = f"import os; print('[maalc] layers ' + os.environ.get({layers.LAYERS_ENV!r}, 'none'), flush=True)\n"
    script += f"import time\nwhile not os.path.exists({str(world.bye)!r}): time.sleep(0.02)\n"
    run.session.agent_command = lambda root, identifier: [sys.executable, "-c", script]
    assert run.start(TWO, **device) == "succeeded"
    assert world.bundles == [str(run.root / "resource" / name) for name in names]
    assert f"[maalc] layers {','.join(names)}" in run.lines("agent")


if __name__ == "__main__":
    child()
