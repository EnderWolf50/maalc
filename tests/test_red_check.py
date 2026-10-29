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
    assert "passes on main: test_lib::test_green" in out and "test_red" not in out.replace("2 test(s)", "")
    assert "red_check: 2 test(s) added or changed, 1 pass on main" in out
