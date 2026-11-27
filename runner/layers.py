"""The resource bundles a run loads (#944, ADR 0017): resource/base, and after it on a PC run the PC resource layer,
resource/pc. MaaFramework merges a later bundle's node over the earlier one's of the same name, field by field.

The bot reloads base after a hot update (agent/resource_update.py) and has to load the layer again with it; runner/ does
not import agent/, so the runner hands it the names of the bundles it loaded in its environment, under LAYERS_ENV."""
from __future__ import annotations

from pathlib import Path

LAYERS = {"emulator": ("base",), "pc": ("base", "pc")}  # by the start's device.kind (runner/protocol.py KINDS)
LAYERS_ENV = "MAALC_RESOURCE_LAYERS"  # agent/resource_update.py's LAYERS_ENV: the names, comma-separated


def bundles(root: Path, kind: str) -> list[Path]:
    """The bundles to load for a run on `kind`, in their order."""
    return [Path(root) / "resource" / name for name in LAYERS[kind]]


def agent_env(kind: str) -> dict[str, str]:
    """What the bot's environment gets for a run on `kind`, over whatever the runner's own environment holds."""
    return {LAYERS_ENV: ",".join(LAYERS[kind])}
