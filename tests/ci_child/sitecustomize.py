"""Lets a Python child of the test run report the docs, gui and root files it opens (#684, tests/ci_filter.py).

conftest puts this folder on PYTHONPATH and names a log in CI_FILTER_LOG; the parent reads the log at the end of its run.
Self-contained: the child's sys.path does not hold tests/. The parent's `unlisted` decides what counts.
"""
import os
import sys

_log = os.environ.get("CI_FILTER_LOG")
if _log:
    _root = os.path.normcase(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) + os.sep
    _seen = set()

    def _hook(event, args):
        if event not in ("open", "os.listdir", "os.scandir") or not args or isinstance(args[0], int) or args[0] is None:
            return
        try:
            p = os.path.abspath(os.fsdecode(args[0]))
        except (TypeError, ValueError):
            return
        if not os.path.normcase(p).startswith(_root):
            return
        rel = p[len(_root):].replace(os.sep, "/")
        if event != "open":
            rel += "/"
            if not rel.startswith(("docs", "gui")):
                return
        if rel in _seen or any(s in rel for s in (".venv/", ".git/", ".local/", "node_modules/", "src-tauri/target/", "gui/dist/")):
            return
        _seen.add(rel)
        with open(_log, "a", encoding="utf-8") as f:
            f.write(rel + "\n")

    sys.addaudithook(_hook)
