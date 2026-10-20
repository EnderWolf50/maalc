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
