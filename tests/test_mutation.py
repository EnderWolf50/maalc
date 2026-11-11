import ast

import mutation

SOURCE = '''"""Docstring."""


def f(x: int = 3) -> bool:
    """Docstring."""
    if x < 2 and not x:
        print(f"{x + 1}")
        return -x
    return None


if __name__ == "__main__":
    f(1)
'''


def whats(source):
    return [what for _, _, _, _, what in mutation.points(ast.parse(source))]


def test_every_operator_gets_its_mutant_and_annotations_docstrings_fstrings_and_main_are_left_alone():
    assert sorted(whats(SOURCE)) == sorted([
        "`3` -> `4`",  # the default
        "`if c:` -> `if not c:`",
        "`and` -> `or`",
        "`<` -> `<=`",
        "`2` -> `3`",
        "`not x` -> `x`",
        "call deleted",  # print(...)
        "`return x` -> `return None`",
        "`-x` -> `x`",
    ])


def apply(source, what):
    tree = ast.parse(source)
    for _, do, _, _, w in mutation.points(tree):
        if w == what:
            do()
            return ast.unparse(ast.fix_missing_locations(tree))
    raise AssertionError(what)


def test_a_mutant_changes_only_its_own_node():
    assert apply("y = not a\n", "`not x` -> `x`") == "y = a"
    assert apply("y = a < b <= c\n", "`<=` -> `<`") == "y = a < b < c"
    assert apply("for i in a:\n    break\n", "`break` -> `continue`") == "for i in a:\n    continue"
    assert apply("y = a + 1\n", "`+` -> `-`") == "y = a - 1"
    assert apply("y += 1\n", "`+=` -> `-=`") == "y -= 1"


def test_a_mutant_is_the_same_change_every_time_it_is_built(monkeypatch):
    monkeypatch.setattr(mutation, "source", lambda module: SOURCE)
    first = [ast.dump(mutation.mutant("m", i)[0]) for i in range(len(whats(SOURCE)))]
    assert first == [ast.dump(mutation.mutant("m", i)[0]) for i in range(len(whats(SOURCE)))]
    assert len(set(first)) == len(first)


def test_a_module_constant_is_rechecked_on_the_tests_that_run_a_line_reading_it(monkeypatch):
    source = "LIMIT = 5\n\n\ndef over(x):\n    return x > LIMIT\n\n\ndef other():\n    return 1\n"
    monkeypatch.setattr(mutation, "source", lambda module: source)
    cover = {"test_a.py": {"exit": 0, "lines": {"m": {"1": ["(import)"], "5": ["tests/test_a.py::test_over"],
                                                      "9": ["tests/test_a.py::test_other"]}}},
             "test_b.py": {"exit": 1, "lines": {"m": {"5": ["tests/test_b.py::test_red"]}}}}
    assert mutation.loaded_lines("m", 1) == {5}
    assert mutation.wide_tests(cover, "m", 1) == ["tests/test_a.py::test_over"]  # test_b failed unmutated
    assert mutation.wide_tests(cover, "m", 9) == ["tests/test_a.py::test_other"]
    assert mutation.wide_tests(cover, "m", 2) == []


def test_every_module_in_the_sweep_has_its_tests_on_disk():
    for module, files in mutation.MODULES.items():
        assert (mutation.AGENT / f"{module}.py").is_file()
        assert all((mutation.ROOT / "tests" / f).is_file() for f in files), module
