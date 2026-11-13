"""Mirror Dungeon (MD8) event table of the unpacked client: event -> options -> kind / gifts / checks / costs (#93).

Usage: uv run python tools/events_md8.py [out_dir]   (default: .local/unpack/out of the main checkout)
Writes events-md8.json (tools/event_table.py reads it), events-md8.csv, events-md8-coverage.json, events-md8-summary.md.
Reads `.local/unpack/`'s static/ and raw/Localize/en only; the client version is the one `.local/unpack/client.json`
names (tools/game_data.py).
"""
import csv
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from game_data import unpack_client
from local_dir import local_dir

STATIC = "static/Assets/Resources_moved/StaticData/static-data/"
LOCALIZE = "raw/Localize/en/"
UI_KW = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
         "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}
SIN = {"CRIMSON": "Wrath", "SCARLET": "Lust", "AMBER": "Sloth", "SHAMROCK": "Gluttony", "AZURE": "Gloom", "INDIGO": "Pride", "VIOLET": "Envy"}


def ld(f):
    with open(f, encoding="utf-8-sig") as fh:
        return json.load(fh)


def tag(s):
    return re.sub(r"</?[a-z][^>]*>", "", s or "").replace("\n", " ").strip()


@dataclass
class Tables:
    """The client's tables, by id: what load reads once and every builder below looks up."""
    event_rows: dict  # abnormality-event records; the first file wins on a duplicate id
    event_file: dict  # the file each event came from
    gift_rows: dict
    battle_rows: dict
    loc: dict  # action events (desc/options) and personality events (success/failure text)
    loc_file: dict
    gift_names: dict
    effect_texts: dict


def load(root: str) -> Tables:
    """static: events (all abnormality-event files), gifts, battles; localize: event texts, gift names, effect texts."""
    b, lz = root + STATIC, root + LOCALIZE
    t = Tables({}, {}, {}, {}, {}, {}, {}, {})
    for f in sorted(glob.glob(b + "abnormality-event/*.json")):
        for e in ld(f).get("list", []):
            if e["id"] not in t.event_rows:
                t.event_rows[e["id"]], t.event_file[e["id"]] = e, os.path.basename(f)
    for f in glob.glob(b + "ego-gift*/*.json"):
        for g in ld(f).get("list", []):
            if isinstance(g, dict) and "id" in g:
                t.gift_rows.setdefault(g["id"], g)
    for f in glob.glob(b + "battle-mirrordungeon/*.json"):
        for row in ld(f)["list"]:
            t.battle_rows.setdefault(row["id"], row)
    for f in sorted(glob.glob(lz + "EN_ActionEvents*.json") + glob.glob(lz + "EN_AbEvents*.json")):
        for x in ld(f).get("dataList", []):
            t.loc.setdefault(x["id"], x)
            t.loc_file.setdefault(x["id"], os.path.basename(f))
    for f in glob.glob(lz + "*EGOgift*.json"):
        for x in ld(f).get("dataList", []):
            if x.get("name"):
                t.gift_names.setdefault(x["id"], x["name"])
    for x in ld(lz + "EN_ChoiceEventEffect.json")["dataList"]:
        t.effect_texts[x["id"]] = tag(x["content"])
    return t


def gift(t, gid):
    g = t.gift_rows.get(gid, {})
    kw = g.get("keyword")
    return {"id": gid, "name": t.gift_names.get(gid), "keyword": UI_KW.get(kw, "Keywordless"),
            "tier": next((x for x in g.get("tag", []) if x.startswith("TIER")), None)}


def effect(t, form):
    """One resultForm -> compact effect dict."""
    name = form.get("resultEffect", "")
    base, *args = re.split(r"_(?=[\d.-])", name, maxsplit=1)
    out = {"effect": base}
    if args:
        out["args"] = [float(a) if "." in a else int(a) for a in re.findall(r"-?[\d.]+", args[0])]
    for k, o in (("resultEffectTarget", "target"), ("resultEffectCondition1", "when")):
        if form.get(k):
            out[o] = form[k]
    r = form.get("itemReward")
    if r and r["type"] == "EGO_GIFT" and r["rewardId"] >= 990000:
        out["hiddenBuff"] = r["rewardId"]  # 99xxxx = hidden-ego-gift-mirrordungeon.json: invisible battle-buff holder, not a pickable gift
    elif r and r["type"] == "EGO_GIFT":
        out["gift"] = gift(t, r["rewardId"])
    elif r:
        out["cost"] = r["num"]
    if form.get("nextBattleID", -1) != -1:
        out["battle"] = form["nextBattleID"]
    if form.get("resultDescId"):
        out["text"] = t.effect_texts.get(form["resultDescId"])
    return out


def results(t, rl):
    """resultList -> [{cond, effects, next}]"""
    return [{"cond": r.get("resultCondition"), "effects": [effect(t, d["resultForm"]) for d in r.get("eventResultDataList", [])],
             "next": r.get("nextEventID", -1) if r.get("nextEventID", -1) != -1 else None} for r in rl]


def walk_gifts(t, rs, how, found, seen, path):
    """Collect (gift, how, path) for results rs; follow nextEventID (check -> pass/fail, action -> follow-up)."""
    for r in rs:
        for e in r["effects"]:
            if "gift" not in e:
                continue
            h = how
            if how in ("direct", "later_direct"):
                h = "win_battle" if e["effect"].endswith("OnWinBattle") else ("direct" if r["cond"] == "Prob_1" else "direct_random")
                h = ("later_" if how == "later_direct" else "") + h
            found.append({**e["gift"], "how": h, "cond": r["cond"], "via": path})
        n = r["next"]
        if n is None or n in seen or n not in t.event_rows:
            continue
        seen = seen | {n}
        ev = t.event_rows[n]
        if "personalityEvent" in ev:
            for br in ev["personalityEvent"].get("eventResults", []):
                h = "check_pass" if br.get("eventResult") == "SUCCESS" else "check_fail"
                sub = results(t, br.get("eventResultDataList", []))
                walk_gifts(t, sub, h, found, seen, path + [n])
        else:
            for o in ev["actionEvent"]["eachOptionList"]:
                walk_gifts(t, results(t, o.get("resultList", [])), "later_direct" if how in ("direct", "later_direct") else how, found, seen,
                           path + [n, o["index"]])


def check_info(t, n):
    """Personality event n -> check description with success/failure effects."""
    p = t.event_rows[n]["personalityEvent"]
    j = p["judgement"]
    out = {"event": n, "sins": [SIN.get(a["attributeType"], a["attributeType"]) for a in j.get("judgementDataList", [])],
           "upDown": j.get("upDownType"), "range": [j.get("inclusiveValue"), j.get("exclusiveValue")],
           "participants": [p.get("participantInfo", {}).get("min"), p.get("participantInfo", {}).get("max")]}
    for br in p.get("eventResults", []):
        k = "success" if br.get("eventResult") == "SUCCESS" else "failure"
        out[k] = [{"cond": r.get("resultCondition"), "effects": [effect(t, d["resultForm"]) for d in r.get("eventResultDataList", [])],
                   **({"next": r["nextEventID"]} if r.get("nextEventID", -1) != -1 else {})} for r in br.get("eventResultDataList", [])]
    loc = t.loc.get(n, {})
    out["successText"], out["failureText"] = loc.get("successDesc"), loc.get("failureDesc")
    return out


def build_event(t, eid):
    ev, loc = t.event_rows[eid], t.loc.get(eid, {})
    rec = {"id": eid, "type": "check" if "personalityEvent" in ev else "choice", "file": t.event_file[eid], "locFile": t.loc_file.get(eid),
           "title": loc.get("name") or loc.get("title") or "", "desc": loc.get("desc") or loc.get("eventDesc") or ""}
    if "personalityEvent" in ev:
        rec["check"] = check_info(t, eid)
        return rec
    ae = ev["actionEvent"]
    rec["hideHint"] = bool(ae.get("isHideHint"))
    rec["options"] = []
    for o in ae["eachOptionList"]:
        i = o["index"]
        lo = loc.get("options", [])[i] if i < len(loc.get("options", [])) else {}
        rs = results(t, o.get("resultList", []))
        found = []
        walk_gifts(t, rs, "direct", found, {eid}, [])
        hows = {g["how"] for g in found}
        nexts = [r["next"] for r in rs if r["next"] in t.event_rows]
        checks = [check_info(t, n) for n in nexts if "personalityEvent" in t.event_rows[n]]
        follow = [n for n in nexts if "actionEvent" in t.event_rows[n]]
        battle = any("battle" in e for r in rs for e in r["effects"])
        kind = ("direct" if "direct" in hows else "random" if "direct_random" in hows else "check" if "check_pass" in hows
                else "check_fail_gift" if "check_fail" in hows else "followup" if any(h.startswith("later_") for h in hows)
                else "battle" if "win_battle" in hows else "check_other" if checks else "followup_other" if follow else "other")
        hint = lo.get("messageDesc")
        rec["options"].append({
            "index": i, "text": lo.get("message"), "hint": hint, "hintHidden": hint == "???",
            "cantSelect": o.get("cantSelectInThisCase"), "kind": kind, "battle": battle,
            "gifts": found, "results": rs, "checks": checks, "followup": follow,
            "resultText": lo.get("result")})
    return rec


def theme_floors(root: str):
    """(event id -> the theme floors that pool it, the battle ids they pool). MD8 data has no per-MD theme list: every
    theme floor is shared."""
    roots = defaultdict(set)
    battles = set()
    for f in sorted(glob.glob(root + STATIC + "mirrordungeon-theme-floor/*.json")):
        for t in ld(f)["list"]:
            m = t["mapGenOption"]
            for k in ("eventPool", "specialEventPool"):
                for i in m.get(k, []):
                    roots[i].add(t["id"])
            for s in t.get("mapGenSequence", []):
                if "EVENT" in s["type"]:
                    for i in s.get("numberList", []):
                        roots[i].add(t["id"])
            for k in ("bossPool", "battlePool", "abBattlePool", "hardBattlePool", "hardAbBattlePool"):
                battles |= set(m.get(k, []))
    return roots, battles


def nexts(o, acc, battles):
    """Every nextEventID in o into acc; every nextBattleID into battles."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("nextEventID",) and v != -1:
                acc.add(v)
            elif k == "nextBattleID" and v != -1:
                battles.add(v)
            else:
                nexts(v, acc, battles)
    elif isinstance(o, list):
        for v in o:
            nexts(v, acc, battles)


def closure(t, start, battles):
    seen, st = set(), [i for i in start if i in t.event_rows]
    while st:
        i = st.pop()
        if i in seen:
            continue
        seen.add(i)
        acc = set()
        nexts(t.event_rows[i], acc, battles)
        st += [j for j in acc if j in t.event_rows and j not in seen]
    return seen


def event_list(t, roots, battles):
    """(events, map ids, battle ids): every event the theme-floor pools reach (scope map), then every event in a battle
    they or those events lead to (scope battle), each linked to the option that leads to it."""
    map_ids = closure(t, roots, battles)
    # in-battle events: abnormalityEventList of every battle reachable from the pools / event outcomes
    battle_ev = defaultdict(set)
    for b in sorted(battles):
        for e in t.battle_rows.get(b, {}).get("abnormalityEventList", []):
            battle_ev[e].add(b)
    battle_ids = closure(t, battle_ev, battles) - map_ids

    events = []
    for i in sorted(map_ids | battle_ids):
        r = build_event(t, i)
        r["scope"] = "map" if i in map_ids else "battle"
        r["themeFloors"] = sorted(roots.get(i, []))
        if i in battle_ev:
            r["battles"] = sorted(battle_ev[i])
        r["root"] = i in roots or i in battle_ev
        events.append(r)

    # link follow-up/check events back to their parent so a root event is the unit the bot matches
    parent = {}
    for e in events:
        for o in e.get("options", []):
            for n in o["followup"] + [c["event"] for c in o["checks"]]:
                parent.setdefault(n, (e["id"], o["index"]))
    for e in events:
        e["parent"] = parent.get(e["id"])
    return events, map_ids, battle_ids


def sig(o):
    g = sorted({(x["keyword"], x["how"]) for x in o["gifts"]})
    return f'{o["kind"]}|{g}'


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def write_csv(path, events):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scope", "eventId", "title", "optIdx", "optionText", "hint", "hintHidden", "kind", "battle", "gifts(keyword:name:how)", "check(sins;range)", "failure/other effects"])
        for e in events:
            for o in e.get("options", []):
                gs = "; ".join(f'{g["keyword"]}:{g["name"]}:{g["how"]}' for g in o["gifts"])
                ck = "; ".join(f'{"&".join(c["sins"])};{c["range"]}' for c in o["checks"])
                oth = []
                for r in o["results"]:
                    oth += [f'{x["effect"]}{x.get("args", "")}' for x in r["effects"] if "gift" not in x]
                for c in o["checks"]:
                    for br in ("failure",):
                        oth += [f'fail:{x["effect"]}{x.get("args", "")}' for r in c.get(br, []) for x in r["effects"] if "gift" not in x]
                w.writerow([e["scope"], e["id"], e["title"], o["index"], o["text"], o["hint"], o["hintHidden"], o["kind"], o["battle"], gs, ck, " ".join(oth)])


def coverage(events):
    """(coverage numbers, the root map events whose texts look alike, those of them that give different gifts, the
    options with a ??? hint)."""
    opts = [(e, o) for e in events for o in e.get("options", [])]
    ch = [e for e in events if e["type"] == "choice"]
    miss_loc = [e["id"] for e in events if not e["desc"] and e["type"] == "choice" and not e["title"]]
    no_text = [(e["id"], o["index"]) for e, o in opts if o["text"] is None]
    hid = [(e, o) for e, o in opts if o["hintHidden"]]
    nohint = [(e, o) for e, o in opts if not o["hint"]]
    key = defaultdict(list)
    for e in ch:
        if e["scope"] == "map" and e["root"]:
            key[norm(e["desc"][:200]) + "|" + "|".join(norm(o["text"]) + norm(o["hint"]) for o in e["options"])].append(e)
    amb = {k: v for k, v in key.items() if len(v) > 1}
    amb_diff = [v for v in amb.values() if len({tuple(sig(o) for o in e["options"]) for e in v}) > 1]
    cov = {
        "choiceEvents": len(ch), "mapRootChoiceEvents": sum(1 for e in ch if e["scope"] == "map" and e["root"]),
        "optionsTotal": len(opts), "optionsWithText": len(opts) - len(no_text), "optionsHintHidden(???)": len(hid),
        "optionsNoHintAtAll": len(nohint), "kinds": dict(Counter(o["kind"] for _, o in opts)),
        "hintHiddenKinds": dict(Counter(o["kind"] for _, o in hid)),
        "choiceEventsWithoutLocalizedDescOrTitle": len(miss_loc),
        "ambiguousGroupsByText": len(amb), "ambiguousEvents": sum(len(v) for v in amb.values()),
        "ambiguousGroupsWithDifferentGiftOutcome": len(amb_diff),
        "optionGiftHowCounts": dict(Counter(g["how"] for _, o in opts for g in o["gifts"])),
        "giftsWithoutEnName": sum(1 for _, o in opts for g in o["gifts"] if not g["name"]),
        "mapEventsWithoutThemeFloor": sum(1 for e in events if e["scope"] == "map" and e["root"] and not e["themeFloors"]),
    }
    return cov, amb, amb_diff, hid


def write_summary(path, client, meta, events):
    """One line per root map event, options as "text [kind: keyword gifts]"."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# MD8 events (client {client})\n\n{json.dumps(meta)}\n\nCoverage: see events-md8-coverage.json\n\n")
        fh.write("| event | title/desc | option | hint | kind | gifts |\n|---|---|---|---|---|---|\n")
        for e in events:
            if e["type"] != "choice" or e["scope"] != "map" or not e["root"]:
                continue
            t = (e["title"] or e["desc"][:40]).replace("\n", " ").replace("|", "/")
            for o in e["options"]:
                g = ", ".join(f'{x["keyword"]} {x["name"]} ({x["how"]})' for x in o["gifts"])
                fh.write(f'| {e["id"]} | {t} | {o["index"]}. {(o["text"] or "").replace("|", "/")} | {(o["hint"] or "").replace("|", "/")} | {o["kind"]} | {g} |\n')


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)


def run(root: str, out: str) -> None:
    """Every events-md8 file of the unpack folder root (a path ending in /) into out."""
    client = unpack_client(Path(root))
    t = load(root)
    roots, battles = theme_floors(root)
    events, map_ids, battle_ids = event_list(t, roots, battles)
    os.makedirs(out, exist_ok=True)
    meta = {"client": client, "dungeon": 8, "events": len(events), "choiceEvents": sum(e["type"] == "choice" for e in events),
            "checkEvents": sum(e["type"] == "check" for e in events), "mapEvents": len(map_ids), "battleEvents": len(battle_ids)}
    dump({"meta": meta, "events": events}, out + "/events-md8.json")
    write_csv(out + "/events-md8.csv", events)
    cov, amb, amb_diff, hid = coverage(events)
    dump({"meta": meta, "coverage": cov, "ambiguous": [[e["id"] for e in v] for v in amb.values()],
          "ambiguousDifferent": [[e["id"] for e in v] for v in amb_diff],
          "hiddenHint": [[e["id"], o["index"], o["kind"]] for e, o in hid]}, out + "/events-md8-coverage.json")
    print(json.dumps({"meta": meta, "coverage": cov}, ensure_ascii=False, indent=1))
    write_summary(out + "/events-md8-summary.md", client, meta, events)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    root = local_dir("unpack").as_posix() + "/"
    run(root, argv[0] if argv else root + "out")


if __name__ == "__main__":
    main()
