"""tools/red_check.py: tests a branch adds that already pass on the base."""
import subprocess
import textwrap

import red_check

SOURCE = textwrap.dedent('''\
    import pytest


    def helper():
        return 1


    @pytest.mark.parametrize("x", [1, 2])
    def test_a(x):
        assert x


    class TestB:
        def test_b(self):
            assert True


    def test_c():
        assert True
''')
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))  # not text: a line diff does not name it


def test_changed_tests_are_the_functions_whose_span_holds_a_changed_line():
    assert red_check.changed_tests(SOURCE, {8}, "tests/test_x.py") == ["tests/test_x.py::test_a"]  # a decorator counts
    assert red_check.changed_tests(SOURCE, {14, 18}, "tests/test_x.py") == ["tests/test_x.py::TestB::test_b", "tests/test_x.py::test_c"]
    assert red_check.changed_tests(SOURCE, {4}, "tests/test_x.py") == []  # a helper is not a test


def branch(tmp_path, monkeypatch, base: dict[str, str | bytes], feat: dict[str, str | bytes], moves=()) -> None:
    """A repo at tmp_path: `base` committed on main, then branch feat moves the `moves` (old, new) paths and writes `feat`."""
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)

    def write(files):
        for path, content in files.items():
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_bytes(content if isinstance(content, bytes) else content.encode())
    write({"pytest.ini": "[pytest]\npythonpath = .\ntestpaths = tests\n", **base})
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    for old, new in moves:
        run("mv", old, new)
    write(feat)
    run("add", ".")
    run("commit", "-qm", "change")
    monkeypatch.setattr(red_check, "ROOT", tmp_path)


def test_a_test_that_passes_on_the_base_is_reported(tmp_path, monkeypatch, capsys):
    branch(tmp_path, monkeypatch, {"lib.py": "def f():\n    return 1\n",
                                   "tests/test_lib.py": "import lib\n\n\ndef test_old():\n    assert lib.f() == 1\n"},
           {"lib.py": "def f():\n    return 2\n",
            "tests/test_lib.py": "import lib\n\n\ndef test_old():\n    assert lib.f() == 1\n\n\n"
                                 "def test_red():\n    assert lib.f() == 2\n\n\n"
                                 "def test_green():\n    assert lib.f() > 0\n"})
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "passes on main: test_lib::test_green" in out and "passes on main: test_lib::test_red" not in out
    assert "red on main: test_lib::test_red" in out
    assert "red_check: 2 test(s) added or changed, 1 pass on main" in out


def test_a_new_screen_reaches_the_base_and_a_real_failure_stays_red(tmp_path, monkeypatch, capsys):
    """#541: a branch that adds only a screenshot and its tests. On the base the picture is there, so the test that only
    reads it passes on the base (reported), and the ones whose assertion fails are red, not "could not read data"."""
    branch(tmp_path, monkeypatch, {"lib.py": "def size(data):\n    return len(data)\n",
                                   "tests/test_lib.py": "import lib\n\n\ndef test_old():\n    assert lib.size(b'') == 0\n"},
           {"tests/screens/New.png": PNG, "assets/New.png": PNG,
            "tests/test_lib.py": "from pathlib import Path\n\nimport pytest\n\nimport lib\n\n"
                                 "NEW = Path(__file__).parent / 'screens' / 'New.png'\n\n\n"
                                 "def test_old():\n    assert lib.size(b'') == 0\n\n\n"
                                 "def test_reads_new_screen():\n    assert lib.size(NEW.read_bytes()) == 264\n\n\n"
                                 "def test_new_screen_fails():\n    assert lib.size(NEW.read_bytes()) == 0\n\n\n"
                                 "def test_raises_on_a_missing_file():\n"
                                 "    with pytest.raises(FileNotFoundError):\n        lib.size(NEW.read_bytes())\n\n\n"
                                 "def test_new_asset():\n    assert lib.size(Path('assets/New.png').read_bytes()) == 264\n"})
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "passes on main: test_lib::test_reads_new_screen" in out
    assert "red on main: test_lib::test_new_screen_fails" in out
    assert "red on main: test_lib::test_raises_on_a_missing_file" in out  # DID NOT RAISE FileNotFoundError is a failed assertion
    assert "red on main: test_lib::test_new_asset" in out  # a resource the base lacks is the base's code, not test data
    assert "could not read data on main" not in out
    assert "red_check: 4 test(s) added or changed, 1 pass on main, 3 red, 0 could not read data" in out


def test_a_moved_screen_reaches_the_base(tmp_path, monkeypatch, capsys):
    branch(tmp_path, monkeypatch, {"tests/screens/Old.png": PNG, "tests/test_x.py": "def test_old():\n    assert True\n"},
           {"tests/test_x.py": "from pathlib import Path\n\n\ndef test_old():\n    assert True\n\n\n"
                               "def test_moved():\n    assert (Path(__file__).parent / 'screens' / 'New.png').read_bytes()\n"},
           moves=[("tests/screens/Old.png", "tests/screens/New.png")])
    assert red_check.main("main") == 1
    assert "passes on main: test_x::test_moved" in capsys.readouterr().out


def test_missing_data_and_a_skip_are_listed_apart_from_red(tmp_path, monkeypatch, capsys):
    """A file the test opens that the branch does not add (here: gitignored), or a skip, is "could not read data", not red."""
    branch(tmp_path, monkeypatch, {".gitignore": "local.bin\n", "tests/test_x.py": "def test_old():\n    assert True\n"},
           {"local.bin": b"x",
            "tests/test_x.py": "from pathlib import Path\n\nimport pytest\n\n\ndef test_old():\n    assert True\n\n\n"
                               "def test_local():\n    assert Path('local.bin').read_bytes() == b'x'\n\n\n"
                               "def test_skipped():\n    pytest.skip('no unpacked game data')\n"})
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "could not read data on main: test_x::test_local" in out
    assert "could not read data on main: test_x::test_skipped" in out
    assert "red on main" not in out
    assert "red_check: 2 test(s) added or changed, 0 pass on main, 0 red, 2 could not read data" in out


def test_a_moved_test_file_lists_the_tests_it_changed(tmp_path, monkeypatch, capsys):
    """A test file moved and edited (git sees a rename) still has its new test checked, and only that one."""
    old = "".join(f"def test_old_{n}():\n    assert {n} == {n}\n\n\n" for n in range(6))
    branch(tmp_path, monkeypatch, {"tests/test_a.py": old},
           {"tests/test_b.py": old + "def test_new():\n    assert True\n"}, moves=[("tests/test_a.py", "tests/test_b.py")])
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "passes on main: test_b::test_new" in out and "test_old_" not in out
    assert "red_check: 1 test(s) added or changed" in out


def test_a_fixture_that_cannot_read_its_data_is_not_red(tmp_path, monkeypatch, capsys):
    """A missing file read in a fixture fails the test at setup (junit: `failed on setup with "FileNotFoundError: ..."`)."""
    branch(tmp_path, monkeypatch, {".gitignore": "local.bin\n", "tests/test_x.py": "def test_old():\n    assert True\n"},
           {"local.bin": b"x",
            "tests/test_x.py": "from pathlib import Path\n\nimport pytest\n\n\n@pytest.fixture\ndef data():\n"
                               "    return Path('local.bin').read_bytes()\n\n\ndef test_old():\n    assert True\n\n\n"
                               "def test_local(data):\n    assert data == b'x'\n"})
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "could not read data on main: test_x::test_local" in out and "red on main" not in out
