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


def test_changed_tests_are_the_functions_whose_span_holds_a_changed_line():
    assert red_check.changed_tests(SOURCE, {8}, "tests/test_x.py") == ["tests/test_x.py::test_a"]  # a decorator counts
    assert red_check.changed_tests(SOURCE, {14, 18}, "tests/test_x.py") == ["tests/test_x.py::TestB::test_b", "tests/test_x.py::test_c"]
    assert red_check.changed_tests(SOURCE, {4}, "tests/test_x.py") == []  # a helper is not a test


def test_a_test_that_passes_on_the_base_is_reported(tmp_path, monkeypatch, capsys):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\ntestpaths = tests\n")
    (tmp_path / "lib.py").write_text("def f():\n    return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_lib.py").write_text("import lib\n\n\ndef test_old():\n    assert lib.f() == 1\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    (tmp_path / "lib.py").write_text("def f():\n    return 2\n")
    (tmp_path / "tests/test_lib.py").write_text("import lib\n\n\ndef test_old():\n    assert lib.f() == 1\n\n\n"
                                                "def test_red():\n    assert lib.f() == 2\n\n\n"
                                                "def test_green():\n    assert lib.f() > 0\n")
    run("commit", "-qam", "change")
    monkeypatch.setattr(red_check, "ROOT", tmp_path)
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "passes on main: test_lib::test_green" in out and "passes on main: test_lib::test_red" not in out
    assert "red on main: test_lib::test_red" in out
    assert "red_check: 2 test(s) added or changed, 1 pass on main" in out


def test_a_new_screen_reaches_the_base_and_a_real_failure_stays_red(tmp_path, monkeypatch, capsys):
    """#541: a branch that adds only a screenshot and its tests. On the base the picture is there, so the test that only
    reads it passes on the base (reported), and the one whose assertion fails is red, not "could not read data"."""
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\ntestpaths = tests\n")
    (tmp_path / "lib.py").write_text("def size(data):\n    return len(data)\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_lib.py").write_text("import lib\n\n\ndef test_old():\n    assert lib.size(b'') == 0\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    (tmp_path / "tests/screens").mkdir()
    (tmp_path / "tests/screens/New.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))
    (tmp_path / "tests/test_lib.py").write_text(
        "from pathlib import Path\n\nimport lib\n\nNEW = Path(__file__).parent / 'screens' / 'New.png'\n\n\n"
        "def test_old():\n    assert lib.size(b'') == 0\n\n\n"
        "def test_reads_new_screen():\n    assert lib.size(NEW.read_bytes()) == 264\n\n\n"
        "def test_new_screen_fails():\n    assert lib.size(NEW.read_bytes()) == 0\n")
    run("add", ".")
    run("commit", "-qm", "screen")
    monkeypatch.setattr(red_check, "ROOT", tmp_path)
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "passes on main: test_lib::test_reads_new_screen" in out
    assert "red on main: test_lib::test_new_screen_fails" in out
    assert "could not read data on main" not in out
    assert "red_check: 2 test(s) added or changed, 1 pass on main, 1 red, 0 could not read data" in out


def test_a_test_whose_data_is_missing_on_the_base_is_listed_apart_from_red(tmp_path, monkeypatch, capsys):
    """A file the test opens that the branch does not add (here: gitignored) is "could not read data", not red."""
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.test", *args], check=True,
                       capture_output=True)
    (tmp_path / ".gitignore").write_text("local.bin\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\ntestpaths = tests\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_x.py").write_text("def test_old():\n    assert True\n")
    run("init", "-q", "-b", "main")
    run("add", ".")
    run("commit", "-qm", "base")
    run("checkout", "-qb", "feat")
    (tmp_path / "local.bin").write_bytes(b"x")
    (tmp_path / "tests/test_x.py").write_text("from pathlib import Path\n\n\ndef test_old():\n    assert True\n\n\n"
                                              "def test_local():\n    assert Path('local.bin').read_bytes() == b'x'\n")
    run("commit", "-qam", "local")
    monkeypatch.setattr(red_check, "ROOT", tmp_path)
    assert red_check.main("main") == 1
    out = capsys.readouterr().out
    assert "could not read data on main: test_x::test_local" in out
    assert "red on main: test_x::test_local" not in out
    assert "red_check: 1 test(s) added or changed, 0 pass on main, 0 red, 1 could not read data" in out
