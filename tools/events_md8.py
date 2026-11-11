"""Mirror Dungeon (MD8) event table of the unpacked client: event -> options -> kind / gifts / checks / costs (#93).

Usage: uv run python tools/events_md8.py [out_dir]   (default: .local/unpack/out of the main checkout)
Writes events-md8.json (tools/event_table.py reads it), events-md8.csv, events-md8-summary.md. Reads `.local/unpack/`'s
static/ and raw/Localize/en only; the client version is the one `.local/unpack/client.json` names (tools/game_data.py).
"""
import csv, glob, json, os, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_data import unpack_client  # noqa: E402
from local_dir import local_dir  # noqa: E402

ROOT = local_dir("unpack").as_posix() + "/"
CLIENT = unpack_client(Path(ROOT))
B = ROOT + "static/Assets/Resources_moved/StaticData/static-data/"
L = ROOT + "raw/Localize/en/"
OUT = sys.argv[1] if len(sys.argv) > 1 else ROOT + "out"
ld = lambda f: json.load(open(f, encoding="utf-8-sig"))
UI_KW = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
         "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}
SIN = {"CRIMSON": "Wrath", "SCARLET": "Lust", "AMBER": "Sloth", "SHAMROCK": "Gluttony", "AZURE": "Gloom", "INDIGO": "Pride", "VIOLET": "Envy"}
tag = lambda s: re.sub(r"</?[a-z][^>]*>", "", s or "").replace("\n", " ").strip()

# ---- static: events (all abnormality-event files; first file wins on a duplicate id), gifts, battles
EV, EVFILE = {}, {}
for f in sorted(glob.glob(B + "abnormality-event/*.json")):
    for e in ld(f).get("list", []):
        if e["id"] not in EV:
            EV[e["id"]], EVFILE[e["id"]] = e, os.path.basename(f)
GIFT = {}
for f in glob.glob(B + "ego-gift*/*.json"):
    for g in ld(f).get("list", []):
        if isinstance(g, dict) and "id" in g:
            GIFT.setdefault(g["id"], g)
BATTLE = {}
for f in glob.glob(B + "battle-mirrordungeon/*.json"):
    for b in ld(f)["list"]:
        BATTLE.setdefault(b["id"], b)

# ---- localize: action events (desc/options), personality events (success/failure text), gift names, effect texts
LOC, LOCFILE, NAME, EFFTXT = {}, {}, {}, {}
for f in sorted(glob.glob(L + "EN_ActionEvents*.json") + glob.glob(L + "EN_AbEvents*.json")):
    for x in ld(f).get("dataList", []):
        LOC.setdefault(x["id"], x); LOCFILE.setdefault(x["id"], os.path.basename(f))
for f in glob.glob(L + "*EGOgift*.json"):
    for x in ld(f).get("dataList", []):
        x.get("name") and NAME.setdefault(x["id"], x["name"])
for x in ld(L + "EN_ChoiceEventEffect.json")["dataList"]:
    EFFTXT[x["id"]] = tag(x["content"])


def gift(gid):
    g = GIFT.get(gid, {})
    kw = g.get("keyword")
    return {"id": gid, "name": NAME.get(gid), "keyword": UI_KW.get(kw, "Keywordless"),
            "tier": next((t for t in g.get("tag", []) if t.startswith("TIER")), None)}


def effect(form):
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
        out["gift"] = gift(r["rewardId"])
    elif r:
        out["cost"] = r["num"]
    if form.get("nextBattleID", -1) != -1:
        out["battle"] = form["nextBattleID"]
    if form.get("resultDescId"):
        out["text"] = EFFTXT.get(form["resultDescId"])
    return out


def results(rl):
    """resultList -> [{cond, effects, next}]"""
    return [{"cond": r.get("resultCondition"), "effects": [effect(d["resultForm"]) for d in r.get("eventResultDataList", [])],
             "next": r.get("nextEventID", -1) if r.get("nextEventID", -1) != -1 else None} for r in rl]


def walk_gifts(rs, how, found, seen, path):
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
        if n is None or n in seen or n not in EV:
            continue
        seen = seen | {n}
        ev = EV[n]
        if "personalityEvent" in ev:
            for br in ev["personalityEvent"].get("eventResults", []):
                h = "check_pass" if br.get("eventResult") == "SUCCESS" else "check_fail"
                sub = results(br.get("eventResultDataList", []))
                walk_gifts(sub, h, found, seen, path + [n])
        else:
            for o in ev["actionEvent"]["eachOptionList"]:
                walk_gifts(results(o.get("resultList", [])), "later_direct" if how in ("direct", "later_direct") else how, found, seen, path + [n, o["index"]])


def check_info(n):
    """Personality event n -> check description with success/failure effects."""
    p = EV[n]["personalityEvent"]
    j = p["judgement"]
    out = {"event": n, "sins": [SIN.get(a["attributeType"], a["attributeType"]) for a in j.get("judgementDataList", [])],
           "upDown": j.get("upDownType"), "range": [j.get("inclusiveValue"), j.get("exclusiveValue")],
           "participants": [p.get("participantInfo", {}).get("min"), p.get("participantInfo", {}).get("max")]}
    for br in p.get("eventResults", []):
        k = "success" if br.get("eventResult") == "SUCCESS" else "failure"
        out[k] = [{"cond": r.get("resultCondition"), "effects": [effect(d["resultForm"]) for d in r.get("eventResultDataList", [])],
                   **({"next": r["nextEventID"]} if r.get("nextEventID", -1) != -1 else {})} for r in br.get("eventResultDataList", [])]
    loc = LOC.get(n, {})
    out["successText"], out["failureText"] = loc.get("successDesc"), loc.get("failureDesc")
    return out


def build_event(eid):
    ev = EV[eid]; loc = LOC.get(eid, {})
    rec = {"id": eid, "type": "check" if "personalityEvent" in ev else "choice", "file": EVFILE[eid], "locFile": LOCFILE.get(eid),
           "title": loc.get("name") or loc.get("title") or "", "desc": loc.get("desc") or loc.get("eventDesc") or ""}
    if "personalityEvent" in ev:
        rec["check"] = check_info(eid)
        return rec
    ae = ev["actionEvent"]
    rec["hideHint"] = bool(ae.get("isHideHint"))
    rec["options"] = []
    for o in ae["eachOptionList"]:
        i = o["index"]
        lo = loc.get("options", [])[i] if i < len(loc.get("options", [])) else {}
        rs = results(o.get("resultList", []))
        found = []
        walk_gifts(rs, "direct", found, {eid}, [])
        hows = {g["how"] for g in found}
        nexts = [r["next"] for r in rs if r["next"] in EV]
        checks = [check_info(n) for n in nexts if "personalityEvent" in EV[n]]
        follow = [n for n in nexts if "actionEvent" in EV[n]]
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


# ---- universe: theme-floor pools (MD8 data has no per-MD theme list; every theme floor is shared) + follow-ups
roots = defaultdict(set)
battles = set()
for f in sorted(glob.glob(B + "mirrordungeon-theme-floor/*.json")):
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


def nexts(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("nextEventID",) and v != -1:
                acc.add(v)
            elif k == "nextBattleID" and v != -1:
                battles.add(v)
            else:
                nexts(v, acc)
    elif isinstance(o, list):
        for v in o:
            nexts(v, acc)


def closure(start):
    seen, st = set(), [i for i in start if i in EV]
    while st:
        i = st.pop()
        if i in seen:
            continue
        seen.add(i)
        acc = set(); nexts(EV[i], acc)
        st += [j for j in acc if j in EV and j not in seen]
    return seen


map_ids = closure(roots)
# in-battle events: abnormalityEventList of every battle reachable from the pools / event outcomes
battle_ev = defaultdict(set)
for b in sorted(battles):
    for e in BATTLE.get(b, {}).get("abnormalityEventList", []):
        battle_ev[e].add(b)
battle_ids = closure(battle_ev) - map_ids

events = []
for i in sorted(map_ids | battle_ids):
    r = build_event(i)
    r["scope"] = "map" if i in map_ids else "battle"
    r["themeFloors"] = sorted(roots.get(i, []))
    if i in battle_ev:
        r["battles"] = sorted(battle_ev[i])
    r["root"] = i in roots or i in battle_ev
    events.append(r)
byid = {e["id"]: e for e in events}

# ---- link follow-up/check events back to their parent so a root event is the unit the bot matches
parent = {}
for e in events:
    for o in e.get("options", []):
        for n in o["followup"] + [c["event"] for c in o["checks"]]:
            parent.setdefault(n, (e["id"], o["index"]))
for e in events:
    e["parent"] = parent.get(e["id"])

# ---- write
os.makedirs(OUT, exist_ok=True)
roots_ev = [e for e in events if e["type"] == "choice" and (e["root"] or e["id"] not in parent)]
meta = {"client": CLIENT, "dungeon": 8, "events": len(events), "choiceEvents": sum(e["type"] == "choice" for e in events),
        "checkEvents": sum(e["type"] == "check" for e in events), "mapEvents": len(map_ids), "battleEvents": len(battle_ids)}
json.dump({"meta": meta, "events": events}, open(OUT + "/events-md8.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def sig(o):
    g = sorted({(x["keyword"], x["how"]) for x in o["gifts"]})
    return f'{o["kind"]}|{g}'

with open(OUT + "/events-md8.csv", "w", encoding="utf-8-sig", newline="") as fh:
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

# ---- coverage numbers
opts = [(e, o) for e in events for o in e.get("options", [])]
ch = [e for e in events if e["type"] == "choice"]
miss_loc = [e["id"] for e in events if not e["desc"] and e["type"] == "choice" and not e["title"]]
no_text = [(e["id"], o["index"]) for e, o in opts if o["text"] is None]
hid = [(e, o) for e, o in opts if o["hintHidden"]]
nohint = [(e, o) for e, o in opts if not o["hint"]]
def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
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
json.dump({"meta": meta, "coverage": cov, "ambiguous": [[e["id"] for e in v] for v in amb.values()],
           "ambiguousDifferent": [[e["id"] for e in v] for v in amb_diff],
           "hiddenHint": [[e["id"], o["index"], o["kind"]] for e, o in hid]},
          open(OUT + "/events-md8-coverage.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"meta": meta, "coverage": cov}, ensure_ascii=False, indent=1))

# ---- markdown summary: one line per root map event, options as "text [kind: keyword gifts]"
with open(OUT + "/events-md8-summary.md", "w", encoding="utf-8") as fh:
    fh.write(f"# MD8 events (client {CLIENT})\n\n{json.dumps(meta)}\n\nCoverage: see events-md8-coverage.json\n\n")
    fh.write("| event | title/desc | option | hint | kind | gifts |\n|---|---|---|---|---|---|\n")
    for e in events:
        if e["type"] != "choice" or e["scope"] != "map" or not e["root"]:
            continue
        t = (e["title"] or e["desc"][:40]).replace("\n", " ").replace("|", "/")
        for o in e["options"]:
            g = ", ".join(f'{x["keyword"]} {x["name"]} ({x["how"]})' for x in o["gifts"])
            fh.write(f'| {e["id"]} | {t} | {o["index"]}. {(o["text"] or "").replace("|", "/")} | {(o["hint"] or "").replace("|", "/")} | {o["kind"]} | {g} |\n')
