"""How well the theme pack page is read, offline (#274): every card of the given screenshots through each way of reading it.

Usage: uv run python tools/pack_stats.py IMAGE_OR_DIR... [--glob PATTERN] [--cache FILE] [--csv FILE] [--md FILE]

No emulator: actions.ocr runs in a MaaFramework task over still images (the pattern of tests/test_shop_cells.py), on the
card strip PACK_TITLES of every page, pages with the same pixels counted once. The OCR boxes of a page are kept in --cache
(JSON; delete it to read again) so the readings below can be rerun in seconds.

Readings, each with the matcher it names (docs/spec/05-game-data.md section 2):
  main    main's pack_titles: boxes with a lowercase letter, columns within 80 px, name and title-art match
  #270    pack_cards of PR #270: the same filter, boxes within 15 px one card, a capitals-only card kept from 80 px wide
  list, no span  pack_cards now with CARD_SPAN off: the filter alone (15 px grouping as in #270), name and title-art match
  list    pack_cards now: only boxes reading a NOT_TITLE word dropped, texts within CARD_SPAN one card; name and title-art match
  +key    list + the keyword of the pack (run_start.match_keyword)
  +cover  +key + the cover art (pack_cover.read_cover): the agent's PickThemePack
  #270+all  the #270 cards with the keyword and cover paths: what the new paths give without the new filter
A card's truth is the pack of the `+cover` reading, which every card of the captures names. That is not independent of the
readings compared, so each card also gets two verdicts that do not rest on the whole-title match: the cover art alone and the
keyword alone (--csv lists them); the summary counts the cards neither confirms. A card of another reading is listed when a
card of the truth stands within CARD_SPAN px of its centre, then named right, wrong or not at all.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import types
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import pack_cover  # noqa: E402
import run_start  # noqa: E402

DATA = yaml.safe_load((ROOT / "assets/resource/base/data/theme_packs.yaml").read_text(encoding="utf-8"))
NAMES, ART = list(DATA["packs"]), DATA["title_art"]
PLAN = {"weights": DATA["default_plan"]["weights"], "unlisted": 0}
READINGS = ("main", "#270", "list, no span", "list", "+key", "+cover", "#270+all")


def read_ocr(images):
    """{image: [[text, [x, y, w, h]], ...]} of PACK_TITLES for each image, in a MaaFramework task."""
    from maa.controller import CustomController
    from maa.custom_action import CustomAction
    from maa.resource import Resource
    from maa.tasker import Tasker

    resource = Resource()  # MaaFramework itself, before anything loads the AgentServer library
    stub = types.ModuleType("maa.agent.agent_server")
    stub.AgentServer = type("AgentServer", (), {"custom_action": staticmethod(lambda name: lambda c: c),
                                                "custom_recognition": staticmethod(lambda name: lambda c: c)})
    sys.modules["maa.agent"] = types.ModuleType("maa.agent")
    sys.modules["maa.agent.agent_server"] = stub
    import actions

    class Still(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "pack-stats"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):
            return lambda *args: True

    out, seen = {}, {}

    class Probe(CustomAction):
        def run(self, context, argv):
            for path in images:
                page = np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB").resize((1280, 720)))[:, :, ::-1])
                x, y, w, h = actions.PACK_TITLES
                key = hashlib.md5(page[y - 20:y + h + 100, x:x + w].tobytes()).hexdigest()
                if key in seen:
                    continue  # the same pixels again: a refresh that changed nothing
                seen[key] = path
                out[str(path)] = [[t, list(b)] for t, b in actions.ocr(context, page, actions.PACK_TITLES)]
            return True

    resource.post_bundle(ROOT / "assets" / "resource" / "base").wait()
    resource.register_custom_action("Probe", Probe())
    controller = Still()
    controller.post_connection().wait()
    tasker = Tasker()
    tasker.bind(resource, controller)
    tasker.post_task("Probe", {"Probe": {"action": "Custom", "custom_action": "Probe"}}).wait()
    return out


def main_cards(results):
    """main's pack_titles: boxes with a lowercase letter, columns within 80 px."""
    lines = sorted((x + w // 2, y, t) for t, (x, y, w, h) in results if re.search(r"[a-z]", t))
    groups = []
    for line in lines:
        if groups and line[0] - groups[-1][-1][0] < 80:
            groups[-1].append(line)
        else:
            groups.append([line])
    return [(g[0][0], [t for _, _, t in sorted(g, key=lambda line: line[1])]) for g in groups]


def pr270_cards(results):
    """pack_cards of PR #270: the lowercase filter, 15 px grouping, a capitals-only card kept from 80 px wide."""
    boxes = sorted((x, x + w, y, t) for t, (x, y, w, h) in results)
    groups = []
    for box in boxes:
        if groups and box[0] - groups[-1][1] < run_start.CARD_GAP:
            groups[-1][1] = max(groups[-1][1], box[1])
            groups[-1][2].append(box)
        else:
            groups.append([box[0], box[1], [box]])
    cards = []
    for left, right, group in groups:
        lines = [(y, t) for _, _, y, t in group]
        small = [line for line in lines if re.search(r"[a-z]", line[1])]
        if small or max(x1 - x0 for x0, x1, _, _ in group) >= 80:
            cards.append(((left + right) // 2, [t for _, t in sorted(small or lines)]))
    return cards


def image_id(path):
    """A page of this repo by its path in it; any other capture by the hash of its file (no local folder names in the output)."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "capture-" + hashlib.md5(Path(path).read_bytes()).hexdigest()[:8]


def gate_sweep(cards):
    """cards: [(page, x, pack)]. For each (score, lead) gate: cards the cover reads, and the ones it reads wrong."""
    covers = pack_cover.covers()
    best = []
    for page, x, pack in cards:
        sig = pack_cover.signature(pack_cover.card_image(page, x))
        scores = sorted(((pack_cover.correlation(sig, c), n) for n, c in covers.items()), reverse=True)
        best.append((scores[0][0], scores[0][0] - scores[1][0], scores[0][1] == pack))
    rows = []
    for score, lead in [(0.5, 0.05), (0.5, 0.1), (0.5, 0.15), (0.6, 0.1), (0.7, 0.1)]:
        read = [ok for s_, l_, ok in best if s_ >= score and l_ >= lead]
        rows.append([score, lead, len(read), read.count(False)])
    return rows


def read(reading, results, page):
    """[(x, lines, pack or None, how)] of a page under a reading."""
    make = {"main": main_cards, "#270": pr270_cards, "#270+all": pr270_cards}.get(reading, run_start.pack_cards)
    span, real_keyword = run_start.CARD_SPAN, run_start.match_keyword
    try:
        if reading == "list, no span":
            run_start.CARD_SPAN = -1  # no two texts are nearer than that: only the 15 px grouping remains
        cards = make(results)
    finally:
        run_start.CARD_SPAN = span
    art = {k: v for k, v in ART.items() if reading != "main" or k != "MADNESS"}
    try:
        if reading in ("main", "#270", "list, no span", "list"):  # no keyword path
            run_start.match_keyword = lambda text, names: None
        cover = (lambda i, allowed: pack_cover.read_cover(page, cards[i][0], allowed)) if reading in ("+cover", "#270+all") else None
        ranked = run_start.rank_packs([lines for _, lines in cards], NAMES, PLAN, art, cover)
    finally:
        run_start.match_keyword = real_keyword
    named = lambda title, how: title if how in ("name", "title_art", "keyword") or how.startswith("cover") else None  # noqa: E731
    return [(x, lines, named(t, how), how) for (x, lines), (t, _, how) in zip(cards, ranked)]


def per_pack(seen_by):
    """One row per pack: its keyword, its cards among the captures, its own cover read off a page, and how many single words
    of its name, read alone (a half-read title), name it by the whole-title match and by that or the keyword."""
    covers = pack_cover.SIGNATURES.parent / "theme_pack_covers"
    index = json.loads((covers / "index.json").read_text(encoding="utf-8"))
    names = NAMES + list(ART)
    keywords = run_start.pack_keywords(names)
    rows = []
    for name in NAMES:
        page = np.zeros((720, 1280, 3), np.uint8)
        left = int(640 - pack_cover.CARD[0] / 2)
        page[pack_cover.CARD_TOP:pack_cover.CARD_TOP + pack_cover.CARD[1], left:left + pack_cover.CARD[0]] = \
            np.asarray(Image.open(covers / index[name]).convert("RGB").resize(pack_cover.CARD))[:, :, ::-1]
        found = pack_cover.read_cover(page, 640)
        words = [w for w in re.split(r"[\W_]+", name) if len(w) >= 3]
        by_name = sum(run_start.match_card([w], names)[0] == name for w in words)
        by_key = sum(run_start.match_card([w], names)[0] == name or run_start.match_keyword(w, names) == name for w in words)
        rows.append([name, keywords.get(name, "-"), seen_by[name], "read" if found and found[0] == name else ("WRONG " + found[0] if found else "silent"),
                     f"{by_name}/{len(words)}", f"{by_key}/{len(words)}"])
    return rows


def table(rows, head):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--glob", default="*.png", help="which files of a directory (an annotated copy of a page is not a page)")
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--md", type=Path)
    args = ap.parse_args()
    paths = sorted({f for p in args.images for f in ([p] if p.is_file() else p.rglob(args.glob))})
    if args.cache and args.cache.is_file():
        ocr = json.loads(args.cache.read_text(encoding="utf-8"))
    else:
        ocr = read_ocr(paths)
        if args.cache:
            args.cache.write_text(json.dumps(ocr, ensure_ascii=False), encoding="utf-8")

    rows, truth_cards, covered = [], 0, []
    stats = {r: Counter() for r in READINGS}
    seen_by = Counter()
    for path, boxes in ocr.items():
        results = [(t, tuple(b)) for t, b in boxes]
        page = np.ascontiguousarray(np.asarray(Image.open(path).convert("RGB").resize((1280, 720)))[:, :, ::-1])
        truth = read("+cover", results, page)
        reads = {r: read(r, results, page) for r in READINGS}
        for x, lines, name, how in truth:
            truth_cards += 1
            seen_by[name] += 1
            verdict = pack_cover.read_cover(page, x)
            word = run_start.match_keyword(" ".join(lines), NAMES + list(ART))
            word = ART.get(word, word)
            covered.append((page, x, name))
            rows.append([image_id(path), x, " / ".join(lines), name, how.split()[0], verdict[0] if verdict else "",
                         "agree" if verdict and verdict[0] == name else ("silent" if not verdict else "DISAGREE"),
                         word or "", "agree" if word == name else ("silent" if not word else "DISAGREE")])
            for r in READINGS:
                near = [c for c in reads[r] if abs(c[0] - x) < run_start.CARD_SPAN]
                if not near:
                    stats[r]["lost"] += 1
                elif near[0][2] is None:
                    stats[r]["unnamed"] += 1
                else:
                    stats[r]["right" if near[0][2] == name else "wrong"] += 1
                    stats[r][near[0][3].split()[0]] += 1
        for r in READINGS:
            stats[r]["cards read"] += len(reads[r])

    out = [f"{len(ocr)} pages, {truth_cards} cards, {len(seen_by)} of {len(NAMES)} packs seen\n"]
    out.append(table([[r, s["right"], s["wrong"], s["unnamed"], s["lost"], s["cards read"] - (truth_cards - s["lost"]),
                       f"{100 * s['right'] / truth_cards:.1f} %"] for r, s in stats.items()],
                     ["reading", "right", "wrong", "listed, no pack", "not listed", "extra cards", "right of all"]))
    out.append("")
    out.append(table([[r, *(s[k] for k in ("name", "title_art", "keyword", "cover"))] for r, s in stats.items()],
                     ["reading", "name", "title_art", "keyword", "cover"]))
    out.append("\nper pack (the keyword; cards among the captures; its own cover pasted on a page; single words of its name read alone):\n")
    out.append(table(per_pack(seen_by), ["pack", "keyword", "cards seen", "own cover", "words by title", "words by title or keyword"]))
    out.append("\nthe cover's gate (MIN_SCORE, MIN_LEAD), on every card against its truth:\n")
    out.append(table(gate_sweep(covered), ["best correlation at least", "lead over the next at least", "cards read", "read wrong"]))
    cover_says, keyword_says = Counter(r[6] for r in rows), Counter(r[8] for r in rows)
    neither = [r for r in rows if r[6] != "agree" and r[8] != "agree"]
    out.append(f"\ncover art alone against the truth: {dict(cover_says)}; keyword alone: {dict(keyword_says)}; "
               f"confirmed by neither: {len(neither)} of {len(rows)} ({len({r[3] for r in neither})} packs)")
    text = "\n".join(out)
    print(text)
    if args.md:
        args.md.write_text(text + "\n", encoding="utf-8")
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["image", "x", "ocr lines", "pack", "path", "cover", "cover verdict", "keyword", "keyword verdict"])
            w.writerows(rows)


if __name__ == "__main__":
    main()
