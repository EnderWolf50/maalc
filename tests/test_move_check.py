import subprocess

import move_check


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True,
                   capture_output=True)


def commit(repo, files):
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", *files)
    git(repo, "commit", "-m", "c")


def test_a_move_reports_only_the_lines_it_did_not_move(tmp_path):
    git(tmp_path, "init", "-q")
    commit(tmp_path, {"a.py": "import os\n\ndef f():\n    return os.sep\n\nx = 1\n", "b.py": "y = 2\n"})
    # f moves into a class (indented once more), gains an import, and x = 1 is dropped on the way
    commit(tmp_path, {"a.py": "import os\n", "b.py": "from a import os\ny = 2\n\nclass C:\n    def f():\n"
                                                    "        return os.sep\n"})

    added, removed = move_check.unmatched("HEAD~", "HEAD", cwd=tmp_path)

    assert added == [("b.py", 1, "from a import os"), ("b.py", 4, "class C:")]
    assert removed == [("a.py", 6, "x = 1")]


def test_a_module_split_off_actions_pairs_its_renamed_reads_off(tmp_path):
    # #676: a test that read actions.LUX (defined in lux_actions) or actions.luxcavation (imported there, no longer in
    # actions) reads it through lux_actions; only the new import is left. ROOT stays in actions: a test that reads it
    # through lux_actions reads lux_actions' own binding, which is no rename. Nor is test_lux_actions.FUSING.
    git(tmp_path, "init", "-q")
    (tmp_path / "agent").mkdir()
    commit(tmp_path, {"agent/actions.py": "import luxcavation\n\nROOT = 1\nLUX = luxcavation.COST\n",
                      "t.py": "import actions\n\nx = actions.LUX + actions.luxcavation.COST + test_actions.LUX\n"
                              "y = test_actions.FUSING\nz = actions.ROOT\n"})
    commit(tmp_path, {"agent/actions.py": "ROOT = 1\n",
                      "agent/lux_actions.py": "import luxcavation\nfrom actions import ROOT\n\nLUX = luxcavation.COST\n",
                      "t.py": "import actions\nimport lux_actions\n\n"
                              "x = lux_actions.LUX + lux_actions.luxcavation.COST + test_actions.LUX\n"
                              "y = test_lux_actions.FUSING\nz = lux_actions.ROOT\n"})

    added, removed = move_check.unmatched("HEAD~", "HEAD", cwd=tmp_path, module="lux_actions")

    assert added == [("agent/lux_actions.py", 2, "from actions import ROOT"), ("t.py", 2, "import lux_actions"),
                     ("t.py", 5, "y = test_lux_actions.FUSING"), ("t.py", 6, "z = lux_actions.ROOT")]
    assert removed == [("t.py", 4, "y = test_actions.FUSING"), ("t.py", 5, "z = actions.ROOT")]
    assert ("t.py", 4, "x = lux_actions.LUX + lux_actions.luxcavation.COST + test_actions.LUX") in \
        move_check.unmatched("HEAD~", "HEAD", cwd=tmp_path)[0]
