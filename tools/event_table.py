"""Trim the unpacked client's Mirror Dungeon event table into assets/resource/base/data/event_table.json (#93).

Usage: uv run python tools/event_table.py [events-md8.json] [static-data dir]
Defaults: the main checkout's .local/unpack/out/events-md8.json (from tools/events_md8.py) and .local/unpack's
static-data folder, read again for each gift's keyword: events_md8.py takes the first record of
a gift id it finds, and the plain ego-gift files carry no keyword (Grimy Iron Stake read Keywordless, not Bleed).

The table's fields, the odds and failure branches (#234) and the follow-up "pages" included, are described in
docs/spec/05-game-data.md section 7. An effect effect() does not know stops the build.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_dir import local_dir  # noqa: E402

SRC = "out/events-md8.json"  # under .local/unpack/ (tools/local_dir.py)
STATIC = "static/Assets/Resources_moved/StaticData/static-data"
OUT = Path(__file__).resolve().parent.parent / "assets/resource/base/data/event_table.json"
UI_KW = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
         "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}
NOT_A_GIFT = 990000  # ids from here up are hidden battle buffs (#420)
KEY_LEN = 60  # the story box shows the end of a long text: the key is its last 60 letters and digits
HP_SP = re.compile(r"(Lose|Recover)(Ratio)?(HpMp|Hp|Mp)(Only|SameAmount|DifferentAmount)(UntilMax)?")


def plain(s):
    return re.sub(r"<[^>]*>", "", s or "").replace("\n", " ").strip()


def norm(s):
    return re.sub(r"[^a-z0-9]", "", plain(s).lower())


def number(s):
    x = float(s)
    return int(x) if x.is_integer() else x


def effect(x):
    """One effect of events_md8.py -> the gets entries it makes (none for Nothing)."""
    name = x["effect"]
    if m := HP_SP.fullmatch(name):
        lose, ratio, what, _, full = m.groups()
        stats = {"HpMp": ["hp", "sp"], "Hp": ["hp"], "Mp": ["sp"]}[what]
        args = x.get("args", [])
        out = []
        for i, stat in enumerate(stats):
            if full:
                amount = "max"
            else:
                amount = args[min(i, len(args) - 1)]  # SameAmount has one number for both
                if lose == "Lose":
                    amount = -amount
            entry = [stat + "%" if ratio else stat, amount]
            if "target" in x:
                entry.append(x["target"])
            out.append(entry)
        return out
    if name in ("MirrorDungeonAcquireCost", "MirrorDungeonLossCost"):
        return [["cost", x["cost"] if name.endswith("AcquireCost") else -x["cost"]]]
    if name in ("GetConfirmedEgogift", "GetConfirmedEgogiftOnWinBattle") and ("gift" in x or "hiddenBuff" in x):
        win = "win_" if name.endswith("OnWinBattle") else ""
        return [[win + "gift", x["gift"]["id"]]] if "gift" in x else [[win + "buff", x["hiddenBuff"]]]
    if name.startswith("StartBattle") and "battle" in x:
        return [["battle", x["battle"]]]
    if name == "Nothing":
        return []
    raise ValueError(f"unknown event effect {name}: add it to tools/event_table.py's effect()")


def cond(r):
    return r.get("cond") or "Prob_1"  # a result with no condition always happens


def branch(r):
    """One result of events_md8.py -> {"p"|"p_per_pick"|"if": ..., "gets": [...]}."""
    how, _, x = cond(r).partition("_")
    head = {"p": number(x)} if how == "Prob" else {"p_per_pick": number(x)} if how == "ProbTimesRepeatCount" else {"if": cond(r)}
    gets = [g for e in r["effects"] for g in effect(e)]
    return {**head, "gets": gets + ([["next", r["next"]]] if r.get("next") else [])}


def option(o, keyword, pages):
    real = [g for g in o["gifts"] if g["id"] < NOT_A_GIFT]
    gifts = sorted({(keyword.get(g["id"], "Keywordless"), g["how"]) for g in real})
    ids = sorted({(g["id"], g["how"]) for g in real})
    rs = o["results"]
    sure = len(rs) <= 1 and all(cond(r) == "Prob_1" for r in rs)  # no result: the page just goes on
    fails = [branch(r) for c in o["checks"] for r in c.get("failure", [])]  # a check with no failure result: no field
    nexts = sorted({r["next"] for r in rs if r.get("next") in pages})
    return {"text": plain(o["text"]), "hint": plain(o["hint"]), "kind": o["kind"],
            **({"gifts": [list(g) for g in gifts], "gift_ids": [list(g) for g in ids]} if gifts else {}),
            **({} if sure else {"odds": [branch(r) for r in rs]}),
            **({"fail": fails} if fails else {}),
            **({"next": nexts} if nexts else {})}


def build(src_path, static):
    """The table file's text, from the intermediate events file and the static-data folder."""
    src = json.loads(Path(src_path).read_text(encoding="utf-8"))
    keyword = {}
    for f in Path(static).glob("ego-gift*/*.json"):
        for g in json.loads(f.read_text(encoding="utf-8-sig")).get("list", []):
            if isinstance(g, dict) and g.get("keyword"):
                keyword.setdefault(g["id"], UI_KW.get(g["keyword"], "Keywordless"))
    choices = [e for e in src["events"] if e["type"] == "choice"]
    pages = {e["id"] for e in choices if not norm(e["desc"])}  # no story text to match it by (battle and follow-up pages)
    events, seen = [], {}
    for e in choices:
        if e["id"] in pages:
            continue  # the hint rules take it
        options = [option(o, keyword, pages) for o in e["options"]]
        key = norm(e["desc"])[-KEY_LEN:]
        if seen.get(key) == options:
            continue  # the same page under another id (971070-971072 and five more groups)
        seen[key] = options
        events.append({"id": e["id"], "key": key, "options": options})
    page_rows = [{"id": e["id"], "options": [option(o, keyword, pages) for o in e["options"]]} for e in choices if e["id"] in pages]
    note = (f"Mirror Dungeon choice events (#93): the game client {src['meta']['client']}'s static data (abnormality-event, "
            "EN_ActionEvents/EN_AbEvents localization, ego-gift keywords), via tools/events_md8.py and "
            "tools/event_table.py. key: the story text's last 60 letters and digits, lower case. kind: direct, random, "
            "check, check_fail_gift, followup, battle, check_other, followup_other, other. gifts: [keyword, how]. "
            "gift_ids: [gift id, how]. how: direct, direct_random, check_pass, check_fail, win_battle, later_direct, "
            "later_direct_random, later_win_battle. odds, fail, next and pages (#234): see docs/spec/05-game-data.md section 7. "
            "Game data (c) Project Moon, see NOTICE.md.")
    def rows(rs):  # one row per line, so a regenerated table diffs by event
        return "[\n" + ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in rs) + "\n ]" if rs else "[]"

    return (f'{{\n "note": {json.dumps(note)},\n "client": "{src["meta"]["client"]}",\n'
            f' "events": {rows(events)},\n "pages": {rows(page_rows)}\n}}\n')


def main():
    unpack = local_dir("unpack") if len(sys.argv) < 3 else None
    text = build(sys.argv[1] if len(sys.argv) > 1 else unpack / SRC, sys.argv[2] if len(sys.argv) > 2 else unpack / STATIC)
    OUT.write_text(text, encoding="utf-8")
    table = json.loads(text)
    print(f"{len(table['events'])} events, {len(table['pages'])} pages -> {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
