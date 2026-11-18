"""`python <root>/runner/__main__.py` (or `python runner` from <root>): the runner, its protocol on stdin and stdout.

The package is loaded from this folder by its path, not by putting <root> on sys.path: <root>'s other folders
(resource/, config/) would then import as namespace packages under names a library may try (`import resource`).
"""
import importlib.util
import sys
from pathlib import Path

if "runner" not in sys.modules:
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("runner", here / "__init__.py", submodule_search_locations=[str(here)])
    sys.modules["runner"] = package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)

from runner.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
