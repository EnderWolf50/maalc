"""Write every theme pack's floors into assets/resource/base/data/theme_packs.yaml from the game's static data (#387).

Usage: uv run python tools/theme_pack_floors.py [--check]
Reads `.local/unpack/` (docs/agents/local-dev.md "Game data"): `mirrordungeon-theme-floor-*.json` for each pack's modes,
floors and difficulty, `EN_MirrorDungeonTheme-1.json` for the English name of a pack the file does not list yet.
Rewrites the floors and the DIFFICULT comment of each pack of `packs`, appends the packs the data puts on a floor of
some mode that `packs` lacks (with the data's name), and rewrites `pack_ids` in the order of `packs` (an id of a pack
`packs` does not list stays, after them). The file's other lines (comments, sections, event packs, title art, the
default plan) stay as they are, and so does a listed name the data spells otherwise (1119, read live). --check writes
nothing and exits 1 when the file is not what the data gives. Rerun it each season, before tools/theme_pack_covers.py
(spec 05 section 8).
"""

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

from local_dir import local_dir

DATA = Path(__file__).resolve().parent.parent / "assets/resource/base/data/theme_packs.yaml"
THEME_FLOOR_DIR = "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-theme-floor"
LOCALIZE = "raw/Localize/en/EN_MirrorDungeonTheme-1.json"
MODES = "NHIX"  # exceptionConditions[].dungeonIdx 0-3: NORMAL, HARD, INFINITY, EXTREME (the mirrordungeon-08* files' typeIndex)
PACK_LINE = re.compile(r'^  ("(?:[^"\\]|\\.)*"|[^\s"#][^:#]*?): (\{[^}]*\})(  # .*)?$')
ID_LINE = re.compile(r'^  ("(?:[^"\\]|\\.)*"|[^\s"#][^:#]*?): (\d+)$')


def floors(row):
    """A static-data row's floors: {mode: [floor, ...]} counted from 1, or {mode: True} where it lists none (every floor)."""
    out = {}
    for c in row.get("exceptionConditions", []):
        mode = MODES[c["dungeonIdx"]]
        out[mode] = [f + 1 for f in c["selectableFloors"]] if "selectableFloors" in c else True
    return {m: out[m] for m in MODES if m in out}


class Row(NamedTuple):
    """A pack of the static data: its English name, its floors (floors()), whether the data marks it DIFFICULT."""
    name: str
    floors: dict
    difficult: bool


def key(name):
    """The name as a YAML key: plain where YAML reads it back as written, else double-quoted (JSON escapes are YAML's)."""
    plain = not any(c in name for c in "&,:'#\"") and name[:1] not in "-?[]{}!*|>%@`" and name == name.strip()
    return name if plain else json.dumps(name, ensure_ascii=False)


def floors_text(floors):
    """{N: [1, 2], I: true}: the flow mapping theme_packs.yaml writes floors as."""
    return "{" + ", ".join(f"{m}: {'true' if v is True else '[' + ', '.join(map(str, v)) + ']'}" for m, v in floors.items()) + "}"


def pack_line(name, row):
    return f"  {key(name)}: {floors_text(row.floors)}" + ("  # DIFFICULT" if row.difficult else "")


def block(lines, header):
    """(first, end) line index of the indented block under `header:` (end: its first blank or unindented line)."""
    start = lines.index(f"{header}:") + 1
    end = start
    while end < len(lines) and lines[end].startswith("  "):
        end += 1
    return start, end


def update(text, rows):
    """theme_packs.yaml's text with the floors of rows ({id: Row}); see the module doc."""
    lines = text.split("\n")
    ids = {}
    start, end = block(lines, "pack_ids")
    for line in lines[start:end]:
        if m := ID_LINE.match(line):
            ids[yaml.safe_load(m[1])] = int(m[2])
    listed = []
    start, end = block(lines, "packs")
    for i in range(start, end):
        if m := PACK_LINE.match(lines[i]):
            name = yaml.safe_load(m[1])
            if ids.get(name) not in rows:
                raise SystemExit(f"pack {name!r} (id {ids.get(name)}) is not in the game data")
            lines[i] = pack_line(name, rows[ids[name]])
            listed.append(name)
    by_id = {i: n for n, i in ids.items()}
    taken = {ids.get(n) for n in listed}
    new = [(by_id.get(pid, row.name), pid) for pid, row in sorted(rows.items()) if row.floors and pid not in taken]
    lines[end:end] = [pack_line(name, rows[pid]) for name, pid in new]
    ids.update({name: pid for name, pid in new})
    order = listed + [n for n, _ in new]
    start, end = block(lines, "pack_ids")
    lines[start:end] = [f"  {key(n)}: {ids[n]}" for n in order + [n for n in ids if n not in order]]
    return "\n".join(lines)


def game_rows(unpack):
    names = {r["id"]: r["name"] for r in json.loads((unpack / LOCALIZE).read_text(encoding="utf-8-sig"))["dataList"]}
    rows = {}
    for f in sorted((unpack / THEME_FLOOR_DIR).glob("*.json")):
        for r in json.loads(f.read_text(encoding="utf-8-sig"))["list"]:
            rows[r["id"]] = Row(names.get(r["id"], f"#{r['id']}"), floors(r), r.get("difficulty") == "DIFFICULT")
    return rows


def main():
    text = DATA.read_text(encoding="utf-8")
    out = update(text, game_rows(local_dir("unpack")))
    if "--check" in sys.argv:
        sys.exit(0 if out == text else 1)
    DATA.write_text(out, encoding="utf-8", newline="\n")
    packs = yaml.safe_load(out)["packs"]
    print(f"{len(packs)} packs, {sum('I' in f for f in packs.values())} INFINITY, {sum('X' in f for f in packs.values())} EXTREME -> {DATA}")


if __name__ == "__main__":
    main()
