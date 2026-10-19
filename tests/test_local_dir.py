import subprocess
from pathlib import Path

import local_dir


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_every_worktree_resolves_to_the_main_checkout(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git("init", "-q", cwd=main)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x", cwd=main)
    other = tmp_path / "other"
    git("worktree", "add", "-q", str(other), "-b", "side", cwd=main)
    assert local_dir.main_checkout(main).resolve() == main.resolve()
    assert local_dir.main_checkout(other).resolve() == main.resolve()
    made = local_dir.local_dir("queue", "bench", cwd=other)
    assert made.is_dir() and made.resolve() == (main / ".local" / "queue" / "bench").resolve()


def test_without_a_cwd_it_uses_the_repo_of_the_script_not_the_callers_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # outside any repo
    here = Path(local_dir.__file__).resolve().parent
    assert local_dir.main_checkout().resolve() == local_dir.main_checkout(here).resolve()
