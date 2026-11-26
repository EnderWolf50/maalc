"""Chinese names and starlight-grace text from the Localize Limbus Company (LLC) release, written into the data files.

Usage: uv run --group unpack python tools/llc_text.py [--release <tag>]  (default: the release the data files carry)
Downloads `LimbusLocalize_<release>.zip` from https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases
(cached under `.local/llc/`) and rewrites the `zh` of assets/resource/base/data/gift_search.json and gift_recipes.json
(from `LLC_zh-CN/EGOgift_*.json`, by gift id) and data/graces.json (names: `MirrorDungeonUI_5.json`
`mirror_dungeon_5_buffs_title_<id>`; effects: the `DungeonStartBuffs_MD7.json` templates filled with the effect values of
`.local/unpack/` static data mirrordungeon-start-buffs-08, each line as runs that say which text the game prints yellow; the
English effects the same from the client's `EN_DungeonStartBuffs_MD7.json`). It writes data/gift_effects.json too: the effect text of each
gift the settings GUI shows (catalog_ids) and of its + and ++ (the gifts of id + 10000 and + 20000, #961), English from the
client's `EN_EGOgift_*.json` and Chinese from `LLC_zh-CN/EGOgift_*.json` (`desc`), as runs that keep the game's markup (effect_runs: a keyword tag, flavour text), and the
keywords they name: their names in the `Bufs*.json` and `BattleKeywords*.json` of each, their colour and icon from the client's
static buff data (#764; tools/buf_icons.py draws the icons). And data/theme_pack_names.json: each theme pack's Chinese
name by its id in data/theme_packs.yaml's `pack_ids` (`LLC_zh-CN/MirrorDungeonTheme*.json`), and the packs the release names
none of, which the GUI shows in English (#899). All of it Simplified to Traditional characters in Taiwan's glyphs, LLC's
words kept (`to_traditional`, OpenCC s2tw and its fix table, #899). Fails on a gift or grace the release lacks;
gift_recipes.py reuses `gift_names`. LLC is CC BY-NC-SA 4.0 (NOTICE.md).
"""

import argparse
import difflib
import json
import re
import urllib.request
import zipfile
from pathlib import Path

import opencc
import yaml

from local_dir import local_dir
from sin_icons import COLOURS as ATTRIBUTE_TYPES  # ATTRIBUTE_TYPE 0..6, CRIMSON..VIOLET: a gift's sin as the data names it

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "assets/resource/base/data"
GRACES = DATA / "graces.json"
EFFECTS = DATA / "gift_effects.json"
THEME_PACKS = DATA / "theme_packs.yaml"
PACK_NAMES = DATA / "theme_pack_names.json"
LANG = "LimbusCompany_Data/Lang/LLC_zh-CN/"
URL = "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/download/{0}/LimbusLocalize_{0}.zip"
LEVELS = {1: "base", 2: "plus", 3: "plus2"}
# A gift's enhanced levels in gift_effects.json: the client's + gift is the base id + 10000, its ++ the id + 20000 (#961)
ENHANCED = {"plus": 10000, "plus2": 20000}
# How the client marks what an enhanced gift changed: the game draws it in its yellow
HIGHLIGHT = '<style="upgradeHighlight">{}</style>'
HIGHLIGHT_OPEN = re.compile(r'<style="?upgradeHighlight"?>', re.I)  # its opening tag; `</style>` closes it
HIGHLIGHT_TAGS = re.compile(HIGHLIGHT_OPEN.pattern + "|</style>", re.I)  # both, to drop the mark from a text
# The pieces marked_changes compares: a tag, a [keyword], a word, a number, whitespace, or any other one character (a CJK one)
TOKEN = re.compile(r"<[^>]+>|\[[^\]<]+\]|[A-Za-z']+|\d+(?:\.\d+)?%?|\s+|.", re.S)
STATIC = "static/Assets/Resources_moved/StaticData/static-data"  # the client's static data, under .local/unpack/
BUFFS = STATIC + "/buff"  # the client's buff records
# The gift records that carry a gift's sin (attributeType): the mirror dungeon's own first, then the plain ones; 9038, 9111
# and 9195 carry another sin in the plain tables (client 1.118.1).
GIFT_TABLES = ("ego-gift-mirrordungeon", "ego-gift")
# The lists of gifts gift_search.json (gifts) and gift_recipes.json (all four) carry, in the GUI catalog's order.
GIFT_LISTS = ("gifts", "materials", "extra_gifts", "vestiges")
YELLOW = "#f8c200"  # the game's yellow in a grace's effect text: what a + or ++ level changed (#733)
BLUE = "#627eff"  # the game's blue of a keyword in a grace's effect text; the GUI shows it plain
# The colours of a gift's effect text by their names in the game's ColorCode table (static data ui/ColorCode.json, client
# 1.118.1): a keyword in its buff's buffType colour, flavour text in Neutral. The GUI keeps a shade of each for its themes.
COLOURS = {YELLOW: "Positive", "#e30000": "Negative", "#a16a3b": "Neutral"}
# TextMeshPro's rich text tags: any other <word> in a text (<Bloodfiend>) is printed as written, as the game does.
TMP_TAGS = {"align", "allcaps", "alpha", "b", "br", "color", "cspace", "font", "font-weight", "gradient", "i", "indent",
            "line-height", "line-indent", "link", "lowercase", "margin", "mark", "mspace", "nobr", "noparse", "page", "pos",
            "rotate", "s", "size", "smallcaps", "space", "sprite", "strikethrough", "style", "sub", "sup", "u", "uppercase",
            "voffset", "width"}


# The user's call of 2026-11-23 (#899), for all LLC text: the localizers' own words, Simplified characters to Traditional
# ones, glyphs in Taiwan's forms. OpenCC s2tw is s2t (STPhrases, STCharacters) and then Taiwan's variant glyphs (TWVariants:
# 爲 -> 為, 裏 -> 裡); s2twp would add Taiwan's wording (TWPhrases: 軟件 -> 軟體, 通過 -> 透過), which is not used.
_S2TW = opencc.OpenCC("s2tw")
# where s2tw's character is not the game's: 松 is both 松 (pine) and 鬆 (loose) in Traditional, and s2tw keeps the pine
FIXES = {"松肉": "鬆肉"}


def to_traditional(text):
    """LLC's Simplified `text` as Traditional: s2tw, then FIXES."""
    text = _S2TW.convert(text)
    for wrong, right in FIXES.items():
        text = text.replace(wrong, right)
    return text


# the conversion as a data file's note names it
CONVERSION_NOTE = "OpenCC s2tw (Taiwan's glyphs, LLC's words kept), then " + ", ".join(f"{a}->{b}" for a, b in FIXES.items())
NOTE_ZH = ("Chinese names: the Localize Limbus Company release's LLC_zh-CN/EGOgift_*.json by gift id (Simplified Chinese), "
           "converted with " + CONVERSION_NOTE + ". Chinese names licensed CC BY-NC-SA 4.0 (see NOTICE.md).")
def note_graces(client):
    return ("Effect text in each language under effects.en and effects.zh. Chinese names and effect text: the Localize Limbus Company "
            "release (Simplified Chinese): MirrorDungeonUI_5 titles and DungeonStartBuffs_MD7 templates filled with the client's "
            "start-buff values, converted with " + CONVERSION_NOTE + ". English names and effect text: the game client "
            f"{client}'s EN_MirrorDungeonUI_5.json titles and EN_DungeonStartBuffs_MD7.json templates filled with the same values, "
            "keywords named by its EN_Bufs*.json and EN_BattleKeywords*.json. Each effect line is a list of runs, `up` on the text the "
            "template colours the game's yellow (" + YELLOW + "), what a + or ++ level changed. Chinese text licensed CC BY-NC-SA 4.0 "
            "(see NOTICE.md). Written by tools/llc_text.py.")


def note_effects(client):
    return ("The effect text of each gift the settings GUI shows (gift_search.json's, then gift_recipes.json's fusion gifts, "
            f"materials, extra gifts and vestiges), as the game's gift panel prints it. English: the game client {client}'s "
            "EN_EGOgift_*.json desc; Chinese: the Localize Limbus Company release's LLC_zh-CN/EGOgift_*.json desc (Simplified "
            "Chinese), by gift id. sin: the gift's sin, which colours the plate the game draws its name on (the attributeType of "
            "its record in the same client's static data, ego-gift-mirrordungeon/*.json before ego-gift/*.json). plus, plus2: "
            "the en and zh of the gift's + (the gift of id + 10000) and ++ (id + 20000), when the client has one. "
            "Each text is a list of runs: a string is plain text; {\"kw\": id} a [tag] that names a keyword, "
            "drawn as its icon and its name in its colour; {\"text\", \"i\", \"colour\"} italic or coloured text (flavour text); "
            "\"up\": true on a run of an enhanced text is what it changed from the level below, which the game prints in its "
            "yellow (the client's <style=\"upgradeHighlight\">; where a text has none, the words that differ from the level below). "
            "keywords: each keyword the texts name: its name in each language (Bufs*.json, BattleKeywords*.json of each), its "
            "colour as the client's ColorCode table names it (its buff's buffType in the static data buff/*.json) and its icon "
            "(data/buf_icons/<icon>.webp, tools/buf_icons.py). A bracketed note that names no keyword stays as written. The "
            "Chinese, keyword names included, converted run by run with " + CONVERSION_NOTE + ". Chinese text licensed CC BY-NC-SA 4.0 (see "
            "NOTICE.md). Written by tools/llc_text.py.")


def note_packs():
    return ("Each theme pack's Chinese name by its id (data/theme_packs.yaml's pack_ids; en: the pack's name there): the "
            "Localize Limbus Company release's LLC_zh-CN/MirrorDungeonTheme*.json name (Simplified Chinese), converted with "
            + CONVERSION_NOTE + ". missing: the ids of the packs of pack_ids the release names none of; the "
            "settings GUI shows their English name. The agent does not read this file. Chinese names licensed CC BY-NC-SA 4.0 "
            "(see NOTICE.md). Written by tools/llc_text.py.")


def current_release():
    """The release the data files were last written from (what a rerun without --release keeps)."""
    return json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["zh_release"]


def release_zip(release):
    path = local_dir("llc") / f"{release}.zip"
    if not path.is_file():
        part = path.with_suffix(".part")
        urllib.request.urlretrieve(URL.format(release), part)
        part.replace(path)
    return zipfile.ZipFile(path)


def read(z, name):
    return json.loads(z.read(LANG + name).decode("utf-8-sig"))["dataList"]


def files(z, prefix):
    return sorted(n[len(LANG):] for n in z.namelist() if n.startswith(LANG + prefix) and n.endswith(".json"))


def gift_names(z):
    """gift id -> Traditional name, the first file (sorted) that lists the id."""
    names = {}
    for f in files(z, "EGOgift_"):
        for x in read(z, f):
            names.setdefault(x["id"], to_traditional(x["name"]))
    return names


def pack_rows(cn, pack_ids):
    """(packs, missing) of `pack_ids` (name -> id, theme_packs.yaml's): packs str(id) -> {"en": its name, "zh": `cn`'s name of
    the id (id -> LLC's Simplified name), markup dropped and converted}, in the order of `pack_ids`; missing: the ids `cn` has
    no name for, in the same order."""
    names = {i: re.sub(r"<[^>]*>", "", cn.get(i) or "").strip() for i in pack_ids.values()}
    packs = {str(i): {"en": n, "zh": to_traditional(names[i])} for n, i in pack_ids.items() if names[i]}
    return packs, [i for i in pack_ids.values() if not names[i]]


def pack_names(z, pack_ids):
    """pack_rows of LLC's `MirrorDungeonTheme*.json` names, the first file (sorted) that names an id."""
    cn = {}
    for f in files(z, "MirrorDungeonTheme"):
        for x in read(z, f):
            if x.get("name"):
                cn.setdefault(x["id"], x["name"])
    return pack_rows(cn, pack_ids)


def keyword_names(z):
    """keyword id -> LLC's (Simplified) name, from Bufs*.json and BattleKeywords*.json; the first file (sorted) that names it."""
    names = {}
    for f in files(z, "Bufs") + files(z, "BattleKeywords"):
        for x in read(z, f):
            if x.get("name"):
                names.setdefault(x["id"], x["name"])
    return names


def effect_runs(text, names, convert=lambda t: t):
    """A gift's effect text as runs: a plain run is a string, a `[tag]` that names a keyword of `names` (id -> name) is
    {"kw": id}; a bracketed note that names none (`[Cannot Stack]`) stays in the text as the game prints it. Text in `<i>` or
    a `<color=...>` is {"text", "i": True, "colour": <the colour's name in the game's ColorCode table, COLOURS>}, each key
    only when it holds (a gift's flavour text); a run (a keyword's too) in `<style="upgradeHighlight">`, what an enhanced
    gift changed, has "up": True. `<noparse>` text is printed as written, and so is a `<word>` TextMeshPro has
    no tag for (`<Bloodfiend>`); any other tag is an error, since the GUI would not draw it. Each run's text goes through
    `convert` on its own (LLC's Simplified to Traditional), and with the keywords' names converted the same way the text
    must read as the whole text converted at once."""
    runs = _runs(text, names)
    out = [r if "kw" in r else convert(r) if isinstance(r, str) else {**r, "text": convert(r["text"])} for r in runs]
    def shown(rs, name):
        return "".join(r if isinstance(r, str) else name(r["kw"]) if "kw" in r else r["text"] for r in rs)
    whole = convert(shown(runs, names.get))
    if shown(out, lambda k: convert(names[k])) != whole:
        raise ValueError(f"converted run by run, the text reads otherwise than whole: {whole}")
    return out


def _runs(text, names):
    """effect_runs before conversion."""
    runs, italic, colours, highlight_depth = [], 0, [], 0

    def add(piece):
        style = {k: v for k, v in (("i", italic > 0), ("colour", colours[-1] if colours else None), ("up", highlight_depth > 0)) if v}
        last = runs[-1] if runs else None
        if not style:
            if isinstance(last, str):
                runs[-1] += piece
            else:
                runs.append(piece)
        elif isinstance(last, dict) and "text" in last and {k: v for k, v in last.items() if k != "text"} == style:
            last["text"] += piece
        else:
            runs.append({"text": piece, **style})

    # TextMeshPro reads its tags in any case: each is matched lower-cased
    for piece in re.split(r"(<noparse>.*?</noparse>|<[^>]+>|\[[^\]<]+\])", text, flags=re.S | re.I):
        low = piece.lower() if piece.startswith("<") else ""
        tag = re.match(r"</?([a-z-]+)\b", low)
        if low.startswith("<noparse>"):
            add(piece[len("<noparse>"):-len("</noparse>")])
        elif low == "<i>":
            italic += 1
        elif low == "</i>" and italic:
            italic -= 1
        elif low.startswith("<color=") and low[len("<color="):-1] in COLOURS:
            colours.append(COLOURS[low[len("<color="):-1]])
        elif low == "</color>" and colours:
            colours.pop()
        elif HIGHLIGHT_OPEN.fullmatch(piece):
            highlight_depth += 1
        elif low == "</style>" and highlight_depth:
            highlight_depth -= 1
        elif tag and tag[1] in TMP_TAGS:  # a new mark, or a closing tag with nothing open
            raise ValueError(f"markup the GUI does not draw: {piece} in {text}")
        elif piece.startswith("[") and piece[1:-1] in names:
            runs.append({"kw": piece[1:-1], **({"up": True} if highlight_depth else {})})
        elif piece:
            add(piece)
    return runs


def marked_changes(text, below):
    """`text` of an enhanced gift with what differs from `below` (the level below's text) marked as the client marks it
    (HIGHLIGHT), piece by piece (TOKEN), when the client marks nothing in it; a text it marks is left as it is."""
    if HIGHLIGHT_OPEN.search(text):
        return text
    old, new = TOKEN.findall(HIGHLIGHT_TAGS.sub("", below)), TOKEN.findall(text)
    out = []
    for op, _, _, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        piece = "".join(new[j1:j2])
        out.append(HIGHLIGHT.format(piece) if op in ("replace", "insert") and piece.strip() else piece)
    return "".join(out)


def _en_list(unpack, pattern):
    """id -> record of the client's English localization files matching `pattern` (`EN_Bufs*.json`); the first file (sorted)
    that lists the id."""
    out = {}
    for f in sorted((unpack / "raw/Localize/en").glob(pattern)):
        for x in json.loads(f.read_text(encoding="utf-8-sig")).get("dataList", []):
            out.setdefault(x["id"], x)
    return out


def en_keyword_names(unpack):
    """keyword id -> the client's English name, from EN_Bufs*.json and EN_BattleKeywords*.json; the first that names it."""
    return {k: x["name"] for p in ("EN_Bufs*.json", "EN_BattleKeywords*.json") for k, x in _en_list(unpack, p).items() if x.get("name")}


def buff_records(unpack):
    """buff id -> its record in the client's static data `buff/*.json` (its buffType and iconId); the first file (sorted)
    that lists the id."""
    out = {}
    for f in sorted((unpack / BUFFS).glob("*.json")):
        for x in json.loads(f.read_text(encoding="utf-8-sig")).get("list", []):
            out.setdefault(x["id"], x)
    return out


def keyword_entry(buff, en, zh):
    """A keyword as gift_effects.json gives it: the ColorCode name of its buff's buffType (the colour the game prints its name
    in), its icon (the buff's iconId, else its id: the sprite Assets/Resources_moved/Buf/<icon>.png, tools/buf_icons.py) and
    its name in each language."""
    if buff["buffType"] not in COLOURS.values():
        raise ValueError(f"buff {buff['id']}: buffType {buff['buffType']} is none of the game's keyword colours {sorted(COLOURS.values())}")
    return {"colour": buff["buffType"], "icon": buff.get("iconId") or buff["id"], "en": en, "zh": zh}


def gift_sins(unpack, ids):
    """gift id -> its sin, for each of `ids`: the attributeType of its record in the client's static data, the mirror
    dungeon's tables (GIFT_TABLES) first. The game draws the gift's name on a plate of that sin's colour (#786). Two records
    of one table folder that disagree, or a gift with no sin of ATTRIBUTE_TYPES, stop the tool: the GUI would have no plate for it."""
    sins = {}
    for folder in GIFT_TABLES:
        found = {}
        for f in sorted((unpack / STATIC / folder).glob("*.json")):
            for g in json.loads(f.read_text(encoding="utf-8-sig")).get("list", []):
                if isinstance(g, dict) and "attributeType" in g:
                    if found.setdefault(g["id"], g["attributeType"]) != g["attributeType"]:
                        raise ValueError(f"gift {g['id']}: {folder} gives it both {found[g['id']]} and {g['attributeType']}")
        for i, sin in found.items():
            sins.setdefault(i, sin)
    missing = [i for i in ids if sins.get(i) not in ATTRIBUTE_TYPES]
    if missing:
        raise ValueError(f"gifts with no sin of {ATTRIBUTE_TYPES}: {[(i, sins.get(i)) for i in missing]}")
    return {i: sins[i] for i in ids}


def catalog_ids():
    """Every gift the settings GUI shows, in its catalog's order (gui/src/giftCatalog.ts CATALOG): gift_search.json's, then
    gift_recipes.json's fusion gifts, materials, extra gifts and vestiges."""
    recipes = json.loads((DATA / "gift_recipes.json").read_text(encoding="utf-8"))
    return [g["id"] for g in json.loads((DATA / "gift_search.json").read_text(encoding="utf-8"))["gifts"]] + [
        g["id"] for k in GIFT_LISTS for g in recipes[k]]


def gift_effects(z, unpack, ids):
    """(keywords, effects): effects str(gift id) -> {"sin", "en", "zh", "plus", "plus2"}, each gift's sin (gift_sins) and effect
    text as runs (effect_runs), in the order of `ids`, and the {"en", "zh"} of its + and ++ (ENHANCED) when the client has
    them, marked where the client marks nothing (marked_changes); keywords keyword id -> keyword_entry, every keyword the effects name, by id. A
    keyword that names no buff of the static data stops the tool: the GUI would have no colour and no icon for it."""
    en = _en_list(unpack, "EN_EGOgift_*.json")
    en_names = en_keyword_names(unpack)
    zh = {}
    for f in files(z, "EGOgift_"):
        for x in read(z, f):
            zh.setdefault(x["id"], x)
    zh_names = keyword_names(z)
    sins = gift_sins(unpack, ids)

    def texts(i, below=None):  # {"en", "zh"} of gift i; an enhanced one marked against the level below where the client does not
        out = {}
        for lang, rows, names, convert in (("en", en, en_names, lambda t: t), ("zh", zh, zh_names, to_traditional)):
            text = rows[i]["desc"].strip()
            out[lang] = effect_runs(text if below is None else marked_changes(text, rows[below]["desc"].strip()), names, convert)
        return out

    effects = {}
    for i in ids:
        effects[str(i)] = {"sin": sins[i], **texts(i)}
        below = i  # the level below the next one: the base, then the + when there is one
        for level, plus in ENHANCED.items():
            if i + plus in en:
                effects[str(i)][level] = texts(i + plus, below)
                below = i + plus
    used = sorted({r["kw"] for e in effects.values() for t in [e, *(e[k] for k in ENHANCED if k in e)] for runs in (t["en"], t["zh"])
                   for r in runs if isinstance(r, dict) and "kw" in r})
    buffs = buff_records(unpack)
    missing = [k for k in used if k not in buffs or k not in en_names or k not in zh_names]
    if missing:
        raise ValueError(f"keywords with no buff record or no name in a language: {missing}")
    return {k: keyword_entry(buffs[k], en_names[k], to_traditional(zh_names[k])) for k in used}, effects


def dump_effects(data):
    """gift_effects.json's layout: one line per header key, per keyword and per gift."""
    def block(key):
        rows = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data[key].items())
        return f'  "{key}": {{\n' + rows + "\n  }"
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k not in ("keywords", "effects")]
    return "{\n" + ",\n".join(head + [block("keywords"), block("effects")]) + "\n}\n"


def needed(value, template):
    if value is None:
        raise ValueError(f"template needs a value the effect lacks: {template}")
    return value


def effect_lines(template, values, keyword_names, convert):
    """One effect's text as the game prints it: its lines, each a list of runs {"text", "up"}, `up` where the template colours
    the text YELLOW. Colour tags nest, the inner one holding until its own closing tag (TextMeshPro's colour stack); a colour
    other than YELLOW and BLUE is an error, since it might be a new mark. Each run goes through `convert` on its own (LLC's
    Simplified to Traditional; the client's English as it is), and must come out as the line converted whole does."""
    ref = values.get("referenceData")
    args = [values.get("value"), values.get("value2")] if not ref else [None, keyword_names[ref["buffKeyword"]], ref["stack"], ref["turn"], ref.get("limit")]
    lines, colours = [[]], []
    for piece in re.split(r"(</?color[^>]*>)", template):
        if piece == "</color>":
            colours.pop()
        elif piece.startswith("<color="):
            colour = piece[len("<color="):-1].lower()
            if colour not in (YELLOW, BLUE):
                raise ValueError(f"template has a colour that is neither the game's yellow nor its blue: {colour} in {template}")
            colours.append(colour)
        else:
            text = re.sub(r"\{(\d)\}", lambda m: str(needed(args[int(m[1])], template)), piece)
            up = bool(colours) and colours[-1] == YELLOW
            for k, part in enumerate(text.split("\n")):
                if k:
                    lines.append([])
                if not part:
                    continue
                runs = lines[-1]
                if runs and runs[-1]["up"] == up:
                    runs[-1]["text"] += part
                else:
                    runs.append({"text": part, "up": up})
    out = []
    for runs in filter(None, lines):
        converted = [{"text": convert(r["text"]), "up": r["up"]} for r in runs]
        whole = convert("".join(r["text"] for r in runs))
        if "".join(r["text"] for r in converted) != whole:
            raise ValueError(f"converted run by run, the line reads otherwise than whole: {whole}")
        out.append(converted)
    return out


def _start_buffs(static, titles, templates, keywords, convert):
    """(base id -> title, base id -> {base, plus, plus2} -> [effect lines]) of the start-buff graces of `static`, from one
    language's titles (by localize id), `DungeonStartBuffs_MD7` templates and keyword names."""
    out, names = {}, {}
    for b in static["list"][0]["buffs"]:
        names[b["baseId"]] = convert(titles[b["localizeId"]])
        lines = []
        for e in b["effects"]:
            key = e.get("customLocalizeTextId", e["type"])
            lines += effect_lines(templates[key], e, keywords, convert)
        out.setdefault(b["baseId"], {})[LEVELS[b["level"]]] = lines
    return names, out


def grace_texts(z, static):
    """(base id -> title, base id -> {base, plus, plus2} -> [effect lines]) of the start-buff graces, LLC's Chinese in
    its own wording and Taiwan's glyphs (to_traditional), and the game's yellow marks (effect_lines)."""
    templates = {x["id"]: x["description"] for x in read(z, "DungeonStartBuffs_MD7.json")}
    titles = {x["id"]: x["content"] for x in read(z, "MirrorDungeonUI_5.json")}
    return _start_buffs(static, titles, templates, keyword_names(z), to_traditional)


def english_grace_texts(unpack, static):
    """grace_texts in the client's English: its `EN_MirrorDungeonUI_5.json` titles, `EN_DungeonStartBuffs_MD7.json` templates
    (the same ids and yellow marks as LLC's) and keyword names, filled with the same values."""
    titles = {i: x["content"] for i, x in _en_list(unpack, "EN_MirrorDungeonUI_5.json").items()}
    templates = {i: x["description"] for i, x in _en_list(unpack, "EN_DungeonStartBuffs_MD7.json").items()}
    return _start_buffs(static, titles, templates, en_keyword_names(unpack), lambda text: text)


def dump_graces(data):
    """graces.json's layout: JSON indented by 2, except that each effect line, a list of runs, stays on one line."""
    def levels(effects):
        return ",\n".join(f"          {json.dumps(level)}: [\n" + ",\n".join("            " + json.dumps(runs, ensure_ascii=False) for runs in lines)
                          + "\n          ]" for level, lines in effects.items())

    def grace(g):
        langs = ",\n".join(f"        {json.dumps(lang)}: {{\n" + levels(effects) + "\n        }" for lang, effects in g["effects"].items())
        keys = [f"      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in g.items() if k != "effects"]
        return "    {\n" + ",\n".join(keys + ['      "effects": {\n' + langs + "\n      }"]) + "\n    }"
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "graces"]
    return "{\n" + ",\n".join(head) + ',\n  "graces": [\n' + ",\n".join(map(grace, data["graces"])) + "\n  ]\n}\n"


def credit(release):
    """The provenance keys of a data file whose Chinese text is LLC's (they replace the wiki's source and license keys)."""
    return {"zh_source": "https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany", "zh_release": release,
            "license": "CC BY-NC-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/"}


def retitled(data, release, note):
    """data with `note` and the credit (replacing any earlier credit keys) first; the other keys keep their order."""
    drop = {"note", "license", "license_url", "zh_source", "zh_release"}
    return {"note": note, **credit(release), **{k: v for k, v in data.items() if k not in drop}}


def dump_search(data):
    """gift_search.json's layout: one line per header key and per gift."""
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "gifts"]
    gifts = ",\n".join("    " + json.dumps(g, ensure_ascii=False) for g in data["gifts"])
    return "{\n" + ",\n".join(head) + ',\n  "gifts": [\n' + gifts + "\n  ]\n}\n"


def dump_pack_names(data):
    """theme_pack_names.json's layout: one line per header key and per pack."""
    head = [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "packs"]
    packs = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data["packs"].items())
    return "{\n" + ",\n".join(head) + ',\n  "packs": {\n' + packs + "\n  }\n}\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default=current_release(), help="the LLC release tag; default: the one the data files carry")
    args = parser.parse_args()
    z = release_zip(args.release)
    names = gift_names(z)
    for name, dump in (("gift_search.json", dump_search), ("gift_recipes.json", lambda d: json.dumps(d, ensure_ascii=False, indent=1) + "\n")):
        data = json.loads((DATA / name).read_text(encoding="utf-8"))
        lists = [data[k] for k in GIFT_LISTS if k in data]
        missing = [g["id"] for gifts in lists for g in gifts if g["id"] not in names]
        assert not missing, f"{name}: not in the release: {missing}"
        for gifts in lists:
            for g in gifts:
                g["zh"] = names[g["id"]]
        note = re.sub(r"Chinese names: .*?\(see NOTICE\.md\)\.", lambda _: NOTE_ZH, data["note"])
        assert NOTE_ZH in note, name
        (DATA / name).write_text(dump(retitled(data, args.release, note)), encoding="utf-8")
    static = json.loads((local_dir("unpack") / "static/Assets/Resources_moved/StaticData/static-data/mirrordungeon-start-buffs/"
                         "mirrordungeon-start-buffs-08.json").read_text(encoding="utf-8-sig"))
    from game_data import unpack_client
    unpack = local_dir("unpack")
    zh_titles, zh_effects = grace_texts(z, static)
    en_titles, en_effects = english_grace_texts(unpack, static)
    graces = json.loads(GRACES.read_text(encoding="utf-8"))
    base_ids = {name: i for i, name in en_titles.items()}  # grace en name -> base id
    assert sorted(base_ids) == sorted(g["en"] for g in graces["graces"]), "graces.json and the client disagree on the grace names"
    for g in graces["graces"]:
        i = base_ids[g["en"]]
        g["zh"], g["effects"] = zh_titles[i], {"en": en_effects[i], "zh": zh_effects[i]}
    GRACES.write_text(dump_graces(retitled(graces, args.release, note_graces(unpack_client(unpack)))), encoding="utf-8")
    keywords, effects = gift_effects(z, unpack, catalog_ids())
    EFFECTS.write_text(dump_effects({"note": note_effects(unpack_client(unpack)), **credit(args.release), "keywords": keywords,
                                     "effects": effects}), encoding="utf-8")
    packs, missing = pack_names(z, yaml.safe_load(THEME_PACKS.read_text(encoding="utf-8"))["pack_ids"])
    PACK_NAMES.write_text(dump_pack_names({"note": note_packs(), **credit(args.release), "missing": missing, "packs": packs}),
                          encoding="utf-8")
    print(f"release {args.release}: {len(names)} gift names, {len(zh_titles)} graces, {len(effects)} gift effects, "
          f"{len(packs)} theme pack names (none for {missing})")


if __name__ == "__main__":
    main()
