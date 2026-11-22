"""The English, Simplified and Traditional text of the event, gift and trial tables, written into data/ (#768).

Usage: uv run --group unpack python tools/text_tables.py [--release <tag>]  (default: the release the data files carry)
Reads the tables the other generators wrote (event_table.json, gift_search.json, gift_recipes.json, trials.yaml and
`.local/unpack/out/events-md8.json`), the client's English localization (`.local/unpack/raw/Localize/en`, its static gift data) and
the Localize Limbus Company (LLC) release's `LLC_zh-CN` files, and writes three id-keyed tables next to them:
  event_text.json  event id -> title, story and each option's text in English, Simplified (`_cn`, as LLC prints it) and Traditional (`_zh`)
  gift_text.json   gift id -> names, keyword and tier, effect and enhanced effect (the id + 10000 gift) in the same three languages
                   (desc_*, plus_*)
  trial_text.json  trial buff id -> the trial's English text, Simplified name and text, and Traditional name and text
Every Traditional field is the Simplified one with markup dropped, converted by `llc_text.to_traditional` (OpenCC s2tw and its fix
table): the one conversion maalc and lc-helper share. LLC is CC BY-NC-SA 4.0 (NOTICE.md). Written for the lc-helper (#759).
"""

import argparse
import json
import re
from pathlib import Path

import yaml

from llc_text import credit, current_release, files, read, release_zip, to_traditional
from local_dir import local_dir

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
LOCALIZE_EN = "raw/Localize/en"
STATIC = "static/Assets/Resources_moved/StaticData/static-data"
UI_KW = {"Combustion": "Burn", "Laceration": "Bleed", "Vibration": "Tremor", "Burst": "Rupture", "Sinking": "Sinking",
         "Breath": "Poise", "Charge": "Charge", "Slash": "Slash", "Penetrate": "Pierce", "Hit": "Blunt"}
ENHANCED = 10000  # an enhanced gift's id is the base gift's + this


def plain(text):
    """`text` without markup tags and edge whitespace; a missing text is empty."""
    return re.sub(r"<[^>]*>", "", text or "").strip()


def zh(text):
    """LLC's Simplified `text`, markup dropped, as Traditional (the shared s2tw conversion and fix table)."""
    return to_traditional(plain(text))


def gift_text(text, names):
    """A gift's effect for a reader: `[BuffId]` replaced by 「name」 (the id when unnamed), markup dropped, blank lines squeezed."""
    text = re.sub(r"\[(\w+)\]", lambda m: f"「{names.get(m[1]) or m[1]}」", plain(text))
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r", "")).strip()


def gift_info(ids, static, en_names, cn_names):
    """id -> {en, zh, keyword, tier} of the gifts `ids`: keyword and tier from the first static record that has one, the English
    name from `en_names` and the Simplified one from `cn_names` ({id: name}, see `first_names`)."""
    info = {i: {"en": "", "zh": "", "keyword": "Keywordless", "tier": None} for i in ids}
    for g in static:
        if not isinstance(g, dict) or g.get("id") not in info:
            continue
        row = info[g["id"]]
        if g.get("keyword") and row["keyword"] == "Keywordless":
            row["keyword"] = UI_KW.get(g["keyword"], "Keywordless")
        tier = next((int(m[1]) for t in g.get("tag") or [] if (m := re.fullmatch(r"TIER_(\d)", str(t)))), None)
        if tier and not row["tier"]:
            row["tier"] = tier
    for i, row in info.items():
        row["en"] = en_names.get(i, "").replace("’", "'")
        row["zh"] = zh(cn_names[i]) if i in cn_names else ""
    return info


def gift_rows(base, en_rows, cn_rows, cn_names, en_buffs, cn_buffs):
    """id -> the gift's names (`base`'s en, zh, keyword and tier; cn: LLC's Simplified name from `cn_names`), its effect `desc_*` and
    its enhanced effect `plus_*` (the gift of id + 10000) in English, Simplified and Traditional; a gift without an enhanced one
    has them empty. `cn_buffs`: buff id -> LLC's Simplified name; the Traditional effect is the whole Simplified one converted."""
    def desc(rows, i, buffs):
        return gift_text(rows[i].get("desc"), buffs) if i in rows else ""

    return {i: {"en": g["en"].replace("’", "'"), "zh": g["zh"], "cn": cn_names.get(i, ""), "keyword": g["keyword"], "tier": g["tier"],
                "desc_en": desc(en_rows, i, en_buffs), "desc_cn": desc(cn_rows, i, cn_buffs), "desc_zh": zh(desc(cn_rows, i, cn_buffs)),
                "plus_en": desc(en_rows, i + ENHANCED, en_buffs), "plus_cn": desc(cn_rows, i + ENHANCED, cn_buffs),
                "plus_zh": zh(desc(cn_rows, i + ENHANCED, cn_buffs))}
            for i, g in sorted(base.items())}


def option_text(row, i):
    """(text, hint) of option `i` of an event's LLC row, Simplified as LLC has them."""
    options = (row or {}).get("options") or []
    if i >= len(options):
        return "", ""
    return plain(options[i].get("message")), plain(options[i].get("messageDesc"))


def event_text(table, md8, llc_event_rows):
    """str(event id) -> {title, story, story_cn, story_zh, options: [{text, text_cn, text_zh, hint_cn, hint_zh}]} for every event
    and page of the event table. `md8`: the client's full English events; an option it lacks keeps the table's own text.
    `llc_event_rows(file)`: id -> LLC row of the event file (LLC's name of md8's `locFile` without its `EN_`); an event LLC lacks
    has empty Chinese text. The option's hint stays in event_table.json (it is English only)."""
    full = {e["id"]: e for e in md8}
    out = {}
    for e in table["events"] + table["pages"]:
        src = full[e["id"]]
        row = llc_event_rows(src["locFile"].removeprefix("EN_")).get(e["id"])
        story_cn = plain((row or {}).get("desc") or (row or {}).get("eventDesc"))
        options = []
        for i, o in enumerate(e["options"]):
            text_cn, hint_cn = option_text(row, i)
            theirs = src["options"][i] if i < len(src["options"]) else {}
            options.append({"text": plain(theirs.get("text")) or o["text"], "text_cn": text_cn, "text_zh": zh(text_cn),
                            "hint_cn": hint_cn, "hint_zh": zh(hint_cn)})
        out[str(e["id"])] = {"title": plain(src.get("title")), "story": plain(src.get("desc")), "story_cn": story_cn,
                             "story_zh": zh(story_cn), "options": options}
    return out


def trial_rows(table, en_rows, cn_rows):
    """buff id -> {desc_en, cn, desc_cn, zh, desc_zh} of each trial of trials.yaml's `table`: the English text the game shows, LLC's
    Simplified name and text and their Traditional conversion; empty where a language lacks the trial."""
    out = {}
    for t in table["trials"].values():
        c = cn_rows.get(t["id"], {})
        out[t["id"]] = {"desc_en": plain((en_rows.get(t["id"]) or {}).get("desc")), "cn": plain(c.get("name")),
                        "desc_cn": plain(c.get("desc")), "zh": zh(c.get("name")), "desc_zh": zh(c.get("desc"))}
    return out


def dump(data, rows_key):
    """The file's layout: the header keys one per line, then `rows_key`'s rows one per line, JSON indented by 1."""
    head = [f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != rows_key]
    rows = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data[rows_key].items())
    return "{\n" + ",\n".join(head) + f',\n {json.dumps(rows_key)}: {{\n' + rows + "\n }\n}\n"


# ---- the files


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def first_rows(rows_by_file):
    """id -> row over files in order, the first file that lists an id wins."""
    out = {}
    for rows in rows_by_file:
        for row in rows:
            out.setdefault(row["id"], row)
    return out


def first_names(rows_by_file):
    """id -> the first non-empty plain `name` over the files in order."""
    out = {}
    for rows in rows_by_file:
        for row in rows:
            if name := plain(row.get("name")):
                out.setdefault(row["id"], name)
    return out


def en_rows(unpack, pattern):
    """id -> row of the client's English files matching `pattern` (`EN_Bufs*.json`), first file (sorted) wins."""
    return first_rows((load(f).get("dataList") or [] for f in sorted((unpack / LOCALIZE_EN).glob(pattern))))


def llc_rows(z, prefix):
    """id -> row of LLC's files whose names start with `prefix`, first file (sorted) wins."""
    return first_rows(read(z, f) for f in files(z, prefix))


def event_gift_ids(table):
    """The gift ids the options of an event table give (a gift or a won gift in odds and fail, or a listed gift id)."""
    options = [o for e in table["events"] + table["pages"] for o in e["options"]]
    return ({g[1] for o in options for b in o.get("odds", []) + o.get("fail", []) for g in b["gets"] if g[0] in ("gift", "win_gift")}
            | {g[0] for o in options for g in o.get("gift_ids", [])})


def base_gifts(unpack, ids_wanted, en_names, cn_names):
    """id -> {en, zh, keyword, tier} of every gift of gift_search.json and gift_recipes.json (their own names), and of the `ids_wanted`
    they lack (gift_info)."""
    search = load(DATA / "gift_search.json")["gifts"]
    recipes = load(DATA / "gift_recipes.json")
    base = {g["id"]: {k: g.get(k) for k in ("en", "zh", "keyword", "tier")}
            for g in search + recipes["materials"] + recipes["extra_gifts"] + recipes["vestiges"] + recipes["gifts"]}
    static = [g for f in sorted((unpack / STATIC).glob("ego-gift*/*.json")) for g in load(f).get("list", [])]
    base.update(gift_info(set(ids_wanted) - set(base), static, en_names, cn_names))
    return base


def notes(client, release):
    common = (f"the game client {client}'s English text and the Localize Limbus Company release's LLC_zh-CN files (Simplified Chinese, in the "
              "_cn fields and cn), the Traditional Chinese (_zh fields and zh) converted from it with OpenCC s2tw and its fix table "
              "(tools/llc_text.py), markup tags dropped. Chinese text licensed CC BY-NC-SA 4.0 (see NOTICE.md). Written by tools/text_tables.py.")
    return {"event_text.json": "Text of each event and page of event_table.json by event id (the table has the keys, hints and effects): " + common,
            "gift_text.json": ("Names, keyword, tier, effect (desc_*) and enhanced effect (plus_*, the gift of id + 10000) of each gift of "
                               "gift_search.json and gift_recipes.json and of each gift an event option gives, by gift id; a [BuffId] in an effect "
                               "is named, as 「name」. From " + common),
            "trial_text.json": "Text of each trial of trials.yaml by its buff id (the table has the pools and scores): " + common}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=current_release(), help="the LLC release tag; default: the one the data files carry")
    args = parser.parse_args()
    from game_data import unpack_client
    unpack = local_dir("unpack")
    client, z = unpack_client(unpack), release_zip(args.release)
    table = load(DATA / "event_table.json")
    md8 = load(unpack / "out/events-md8.json")["events"]
    cache = {}

    def event_rows(name):
        if name not in cache:
            cache[name] = first_rows([read(z, name)] if name in files(z, name) else [])
        return cache[name]

    texts = notes(client, args.release)
    events = event_text(table, md8, event_rows)

    en_gifts, cn_gifts = en_rows(unpack, "EN_EGOgift*.json"), llc_rows(z, "EGOgift_")
    en_names = first_names(load(f).get("dataList") or [] for f in sorted((unpack / LOCALIZE_EN).glob("EN_EGOgift*.json")))
    cn_names = first_names(read(z, f) for f in files(z, "EGOgift_"))
    base = base_gifts(unpack, event_gift_ids(table), en_names, cn_names)
    en_buffs = {i: plain(r.get("name")) for i, r in en_rows(unpack, "EN_Bufs*.json").items()}
    cn_buffs = first_names(read(z, f) for f in files(z, "Bufs"))
    gifts = gift_rows(base, en_gifts, cn_gifts, cn_names, en_buffs, cn_buffs)

    trials = trial_rows(load_yaml(DATA / "trials.yaml"), en_rows(unpack, "EN_Bufs_Mirror*.json"), llc_rows(z, "Bufs_Mirror"))
    for name, rows, key in (("event_text.json", events, "events"), ("gift_text.json", gifts, "gifts"), ("trial_text.json", trials, "trials")):
        data = {"note": texts[name], **credit(args.release), "client": client, key: {str(k): v for k, v in rows.items()}}
        (DATA / name).write_text(dump(data, key), encoding="utf-8")
        print(f"{name}: {len(rows)} rows, {(DATA / name).stat().st_size} bytes")


if __name__ == "__main__":
    main()
