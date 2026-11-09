"""Trim the unpacked client's Mirror Dungeon event table into assets/resource/base/data/event_table.json (#93).

Usage: uv run python tools/event_table.py [events-md8.json] [static-data dir]
Defaults: <unpack dir>/out/events-md8.json (from limbus-unpack's scripts/events_md8.py, client 1.117.0)
and that unpack's static-data folder, read again for each gift's keyword: events_md8.py takes the first record of
a gift id it finds, and the plain ego-gift files carry no keyword (Grimy Iron Stake read Keywordless, not Bleed).
"""

import json
import re
import sys
from pathlib import Path

UNPACK = "<unpack dir>/"
SRC = UNPACK + "out/events-md8.json"
STATIC = UNPACK + "static/Assets/Resources_moved/StaticData/static-data"
OUT = Path(__file__).resolve().parent.parent / "assets/resource/base/data/event_table.json"
UI_KW = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
         "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}
NOT_A_GIFT = 990000  # ids from here up are hidden battle buffs (#420)
KEY_LEN = 60  # the story box shows the end of a long text: the key is its last 60 letters and digits


def plain(s):
    return re.sub(r"<[^>]*>", "", s or "").replace("\n", " ").strip()


def norm(s):
    return re.sub(r"[^a-z0-9]", "", plain(s).lower())


def build(src_path, static):
    """The table file's text, from the intermediate events file and the static-data folder."""
    src = json.loads(Path(src_path).read_text(encoding="utf-8"))
    keyword = {}
    for f in Path(static).glob("ego-gift*/*.json"):
        for g in json.loads(f.read_text(encoding="utf-8-sig")).get("list", []):
            if isinstance(g, dict) and g.get("keyword"):
                keyword.setdefault(g["id"], UI_KW.get(g["keyword"], "Keywordless"))
    events, seen = [], {}
    for e in src["events"]:
        if e["type"] != "choice" or not norm(e["desc"]):
            continue  # no story text to match it by (13 battle and follow-up pages): the hint rules take it
        options = []
        for o in e["options"]:
            real = [g for g in o["gifts"] if g["id"] < NOT_A_GIFT]
            gifts = sorted({(keyword.get(g["id"], "Keywordless"), g["how"]) for g in real})
            ids = sorted({(g["id"], g["how"]) for g in real})
            options.append({"text": plain(o["text"]), "hint": plain(o["hint"]), "kind": o["kind"],
                            **({"gifts": [list(g) for g in gifts], "gift_ids": [list(g) for g in ids]} if gifts else {})})
        key = norm(e["desc"])[-KEY_LEN:]
        if seen.get(key) == options:
            continue  # the same page under another id (971070-971072 and five more groups)
        seen[key] = options
        events.append({"id": e["id"], "key": key, "options": options})
    note = (f"Mirror Dungeon choice events (#93): the game client {src['meta']['client']}'s static data (abnormality-event, "
            "EN_ActionEvents/EN_AbEvents localization, ego-gift keywords), via limbus-unpack scripts/events_md8.py and "
            "tools/event_table.py. key: the story text's last 60 letters and digits, lower case. kind: direct, random, "
            "check, check_fail_gift, followup, battle, check_other, followup_other, other. gifts: [keyword, how]. "
            "gift_ids: [gift id, how]. how: direct, direct_random, check_pass, check_fail, win_battle, later_direct, "
            "later_direct_random, later_win_battle. "
            "Game data (c) Project Moon, see NOTICE.md.")
    lines = ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in events)
    return f'{{\n "note": {json.dumps(note)},\n "client": "{src["meta"]["client"]}",\n "events": [\n{lines}\n ]\n}}\n'


def main():
    text = build(sys.argv[1] if len(sys.argv) > 1 else SRC, sys.argv[2] if len(sys.argv) > 2 else STATIC)
    OUT.write_text(text, encoding="utf-8")
    print(f"{len(json.loads(text)['events'])} events -> {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
