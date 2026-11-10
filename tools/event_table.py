"""Trim the unpacked client's Mirror Dungeon event table into assets/resource/base/data/event_table.json (#93).

Usage: uv run python tools/event_table.py [events-md8.json] [static-data dir]
Defaults: <unpack dir>/out/events-md8.json (from limbus-unpack's scripts/events_md8.py, client 1.117.0)
and that unpack's static-data folder, read again for each gift's keyword: events_md8.py takes the first record of
a gift id it finds, and the plain ego-gift files carry no keyword (Grimy Iron Stake read Keywordless, not Bleed).

Besides kind and gifts, an option keeps what the bot does not use yet (#234):
- odds: the branches of an option whose outcome is not sure (a random option, or one that depends on the team's SP).
- fail: the failure branches of the check the option starts.
- next: the follow-up pages without story text the option leads to; they are under "pages", by id, not under "events".
A branch is {"p": chance, "gets": [...]}; {"p_per_pick": x, ...} when the chance is x times the times the page was
picked (the other branch then has -x: the rest); {"if": "<the game's condition>", ...} for any other condition.
gets lists the effects: [hp|sp|hp%, amount, target] (a loss is negative, amount "max" heals to full),
[cost, amount], [gift|win_gift|buff|win_buff, id] (win_: only when the fight is won; buff: a hidden battle buff),
[battle, battle id], [next, event id]; "Nothing" is left out. An effect's own condition (only Identities without
some affinity, for instance) is not kept. An effect this file does not know stops the build.
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
            amount = "max" if full else -args[min(i, len(args) - 1)] if lose == "Lose" else args[min(i, len(args) - 1)]
            out.append([stat + "%" * bool(ratio), amount, *[x["target"]] * ("target" in x)])
        return out
    if name in ("MirrorDungeonAcquireCost", "MirrorDungeonLossCost"):
        return [["cost", x["cost"] if name.endswith("AcquireCost") else -x["cost"]]]
    if name in ("GetConfirmedEgogift", "GetConfirmedEgogiftOnWinBattle") and ("gift" in x or "hiddenBuff" in x):
        win = "win_" * name.endswith("OnWinBattle")
        return [[win + "gift", x["gift"]["id"]]] if "gift" in x else [[win + "buff", x["hiddenBuff"]]]
    if name.startswith("StartBattle") and "battle" in x:
        return [["battle", x["battle"]]]
    if name == "Nothing":
        return []
    raise ValueError(f"unknown event effect {name}: add it to tools/event_table.py's effect()")


def branch(r):
    """One result of events_md8.py -> {"p"|"p_per_pick"|"if": ..., "gets": [...]}."""
    cond = r.get("cond") or "Prob_1"
    how, _, x = cond.partition("_")
    head = {"p": number(x)} if how == "Prob" else {"p_per_pick": number(x)} if how == "ProbTimesRepeatCount" else {"if": cond}
    gets = [g for e in r["effects"] for g in effect(e)]
    return {**head, "gets": gets + ([["next", r["next"]]] if r.get("next") else [])}


def option(o, keyword, pages):
    real = [g for g in o["gifts"] if g["id"] < NOT_A_GIFT]
    gifts = sorted({(keyword.get(g["id"], "Keywordless"), g["how"]) for g in real})
    ids = sorted({(g["id"], g["how"]) for g in real})
    rs = o["results"]
    sure = len(rs) <= 1 and all((r.get("cond") or "Prob_1") == "Prob_1" for r in rs)  # no result: the page just goes on
    nexts = sorted({r["next"] for r in rs if r.get("next") in pages})
    return {"text": plain(o["text"]), "hint": plain(o["hint"]), "kind": o["kind"],
            **({"gifts": [list(g) for g in gifts], "gift_ids": [list(g) for g in ids]} if gifts else {}),
            **({} if sure else {"odds": [branch(r) for r in rs]}),
            **({"fail": [branch(r) for c in o["checks"] for r in c.get("failure", [])]} if o["checks"] else {}),
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
            "EN_ActionEvents/EN_AbEvents localization, ego-gift keywords), via limbus-unpack scripts/events_md8.py and "
            "tools/event_table.py. key: the story text's last 60 letters and digits, lower case. kind: direct, random, "
            "check, check_fail_gift, followup, battle, check_other, followup_other, other. gifts: [keyword, how]. "
            "gift_ids: [gift id, how]. how: direct, direct_random, check_pass, check_fail, win_battle, later_direct, "
            "later_direct_random, later_win_battle. odds, fail, next and pages (#234): see tools/event_table.py. "
            "Game data (c) Project Moon, see NOTICE.md.")
    def rows(rs):  # one row per line, so a regenerated table diffs by event
        return "[\n" + ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in rs) + "\n ]" if rs else "[]"

    return (f'{{\n "note": {json.dumps(note)},\n "client": "{src["meta"]["client"]}",\n'
            f' "events": {rows(events)},\n "pages": {rows(page_rows)}\n}}\n')


def main():
    text = build(sys.argv[1] if len(sys.argv) > 1 else SRC, sys.argv[2] if len(sys.argv) > 2 else STATIC)
    OUT.write_text(text, encoding="utf-8")
    table = json.loads(text)
    print(f"{len(table['events'])} events, {len(table['pages'])} pages -> {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
