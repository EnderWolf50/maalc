"""`evidence.py map`: the floor stitched from the frames the bot read, each node it read boxed, and the route
(evidence.py's docstring says what the picture shows)."""
from __future__ import annotations

import json
import re
from itertools import accumulate
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

from live.evidence import (BLUE, CYAN, GREEN, MAGENTA, ORANGE, RED, TOOLS, VIOLET, WHITE, H, W, Footage, annotated_clip,
                           apply_masks, font, frames, grab, hms, load_masks, maalc, masks_path, read_log, secs, touches)

# a node's notes, in the order they ring its box: tag -> colour
NOTE_COLOUR = {"boss_shop": CYAN, "boss_glow": CYAN, "boss_by_cost": WHITE, "cost_miss": MAGENTA, "cost_none": MAGENTA, "retyped": VIOLET}
SHIFT_MIN = 0.6  # TM_CCOEFF_NORMED of a slide to trust: the real one scored 0.91-0.94 (run 11, floor 1), another place 0.5 at most
COLX = lambda k: 328 + 255 * (k - 1)  # noqa: E731  x of map column k (1-based) before any drag
ROWY = {"up": 144, "mid": 357, "down": 570}
BUS = (110, 357)


def floor_block(msgs, floor: int, after: float | None = None) -> list[tuple[float, str]]:
    """The floor's `map:` lines, from its pull (or the first map line after `after`) to its `map: path`. The lines
    start at the last `follow plan` or `reading the map again` line when there is one."""
    if after is not None:
        start = next(i for i, (t, x) in enumerate(msgs) if t > after and x.startswith("map:"))
    else:
        start = next(i for i, (_, x) in enumerate(msgs) if x.startswith(f"floor {floor}: pull"))
    out = []
    for t, x in msgs[start:]:
        if x.startswith("map:"):
            if x.startswith("map: follow plan") or x.endswith("reading the map again"):
                out = []
            out.append((t, x))
            if x.startswith("map: path"):
                break
    return out


def parse_map(block):
    """(stages [{cols: {k: {row: type}}, costs: [(x, y, cost, type)], misses: [(x, y, why)], boss: {k: tag}, t0, t1}],
    drags [(t, px, from column)], path)."""
    new = lambda t: {"cols": {}, "costs": [], "misses": [], "boss": {}, "t0": t}  # noqa: E731
    stages, drags, path = [new(block[0][0])], [], None
    for t, x in block:
        if m := re.match(r"map: node at (\d+), (\d+) reads Cost (\S+): (\w+)", x):
            stages[-1]["costs"].append((int(m[1]), int(m[2]), m[3], m[4]))  # "None": the bot saw a coin but read no number
        elif m := re.match(r"map: Cost miss at (\d+), (\d+) \(\w+\): (.*?), crop ", x):
            stages[-1]["misses"].append((int(m[1]), int(m[2]), m[3]))
        elif m := re.match(r"map: column (\d+): the boss' glow without", x):
            stages[-1]["boss"][int(m[1])] = "boss_glow"
        elif m := re.match(r"map: column (\d+): after the shop, so the boss|map: left the shop; column (\d+)", x):
            stages[-1]["boss"][int(m[1] or m[2])] = "boss_shop"
        elif m := re.match(r"map: column (\d+): (.*)", x):
            stages[-1]["cols"][int(m[1])] = {c[1]: c[2] for c in re.finditer(r"(up|mid|down) (\w+) \(", m[2])}
            stages[-1]["t1"] = t
        elif m := re.match(r"map: dragged the map (\d+) px; reading on from column (\d+)", x):
            drags.append((t, int(m[1]), int(m[2])))
            stages.append(new(t))
        elif m := re.match(r"map: path (.*), score (-?\d+)", x):
            path = ([tuple(p.split(" ", 1)) for p in m[1].split(" > ")], int(m[2]))
    return stages, drags, path


def node_table(stages, drags) -> dict:
    """{(column, row): {type: last read, first: first read, cost: the Cost read there or None, stage: the stage of the
    last read, notes: [(tag, detail)] in NOTE_COLOUR's order}}."""
    offsets = list(accumulate((px for _, px, _ in drags), initial=0))
    nodes, notes = {}, {}
    cell = lambda x, y, off: (round((x + off - COLX(1)) / 255) + 1, min(ROWY, key=lambda r: abs(ROWY[r] - y)))  # noqa: E731
    for s, (st, off) in enumerate(zip(stages, offsets)):
        for k, cells in st["cols"].items():
            for row, typ in cells.items():
                n = nodes.setdefault((k, row), {"type": typ, "first": typ, "cost": None, "stage": s})
                n["type"], n["stage"] = typ, s
        for x, y, cost, kind in st["costs"]:
            if (key := cell(x, y, off)) in nodes:
                nodes[key]["cost"] = cost
                found = notes.setdefault(key, {})
                if cost == "None":
                    found["cost_none"] = None
                if kind == "boss":
                    found["boss_by_cost"] = None
        for x, y, why in st["misses"]:
            if (key := cell(x, y, off)) in nodes:
                notes.setdefault(key, {})["cost_miss"] = why
        for k, tag in st["boss"].items():
            for row in ROWY:
                if (k, row) in nodes:
                    notes.setdefault((k, row), {})[tag] = None
    for key, n in nodes.items():
        found = notes.get(key, {})
        if n["first"] != n["type"]:
            found["retyped"] = None
        if n["type"] != "boss":  # a boss note belongs to a node that ended as the boss
            found = {t: d for t, d in found.items() if not t.startswith("boss")}
        n["notes"] = [(t, found[t]) for t in NOTE_COLOUR if t in found]
    return nodes


def motion(grays) -> list[bool]:
    """Per frame: did the map area (rows 110-620) change from the frame before (mean abs difference over 5)?"""
    out, prev = [], None
    for g in grays:
        im = np.asarray(g[110:620], np.int16)
        out.append(prev is not None and float(np.abs(im - prev).mean()) > 5)
        prev = im
    return out


def runs(mov) -> list[tuple[int, int]]:
    """(first, last) frame of each motion run; a single still frame inside does not end one."""
    out, i, n = [], 0, len(mov)
    while i < n:
        if mov[i]:
            j = i
            while j + 1 < n and (mov[j + 1] or mov[min(j + 2, n - 1)]):
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def still_spans(mov, margin: int = 2) -> list[tuple[int, int]]:
    """(first, last) frame of each stretch between motion runs, a margin of frames off the sides that touch one."""
    spans, lo = [], 0
    for a, b in runs(mov):
        spans.append((lo, a - 1 - margin))
        lo = b + 1 + margin
    spans.append((lo, len(mov) - 1))
    return [(a, b) for a, b in spans if a <= b]


def pick_shots(times, mov, reads) -> list[int]:
    """Frame index of the still map each reading (a wall time) saw: its frame, clipped into the still stretch that
    holds it, or into the nearest one when the footage shows the map moving then (the clocks differ by a fraction of a second).

    Run 11, floor 1 (2026-10-24): the map is dragged twice, then back. The log's `dragged` line comes about a second
    after the drag ended and the drag back starts 0.4 s later: the last motion run within a second of the line is the
    drag back, so a pick by motion runs showed the map of the first drag for the second.
    """
    spans = still_spans(mov) or [(0, len(times) - 1)]
    picks = []
    for t in reads:
        k = min(range(len(times)), key=lambda i: abs(times[i] - t))
        a, b = min(spans, key=lambda s: max(s[0] - k, k - s[1], 0))
        picks.append(min(max(k, a), b))
    return picks


def measure_shift(prev, cur, expect: int, reach: int = 100, rows=(150, 560), cols=(40, 440)):
    """(shift, score): how far the map slid from the gray frame prev to cur (cur's x is prev's x minus shift), by the
    best match of cur's left part within reach px of expect; None when it scores under SHIFT_MIN or cur is flat.

    Rows 150-560 leave the HUD and the party bar out. The columns repeat every 255 px, so the search stays near expect.
    """
    (y0, y1), (x0, x1) = rows, cols
    tpl = np.ascontiguousarray(cur[y0:y1, x0:x1])
    if tpl.std() < 3:
        return None
    import cv2  # the dev and probe groups' since #325; imported here so a flat frame needs none

    lo, hi = max(0, x0 + expect - reach), min(prev.shape[1], x1 + expect + reach)
    score = cv2.matchTemplate(np.ascontiguousarray(prev[y0:y1, lo:hi]), tpl, cv2.TM_CCOEFF_NORMED)[0]
    best = int(score.argmax())
    return (lo + best - x0, float(score[best])) if score[best] >= SHIFT_MIN else None


LEGEND_TEXT = {GREEN: "讀對", RED: "類型錯", ORANGE: "Cost 錯或漏列", VIOLET: "先讀錯，拖近後改正", MAGENTA: "Cost 沒讀到或 miss",
               WHITE: "靠 Cost 判成 Boss", CYAN: "Boss 紅光或商店判定", BLUE: "路線"}
TOP, LINE = 44, 40  # the header line above the map; a legend line below it
SMOOTH = 4  # shapes are drawn this many times larger and scaled down: PIL draws them without antialiasing
BG = (22, 22, 22)
EDGE = 52  # half a node box: PIL draws an outline inside its rectangle, so this is its outer edge


def note_text(tag: str, n) -> str:
    """A note's line under the node's label: short, the label is a box wide."""
    return {"retyped": f"初讀 {n['first']}", "cost_none": "Cost 沒讀到", "cost_miss": "Cost miss",
            "boss_by_cost": "靠 Cost 判 boss", "boss_glow": "Boss 紅光", "boss_shop": "商店後，判 boss"}[tag]


def map_weights(nodes, hard: bool | None = None) -> dict:
    """The route weights of the floor's difficulty (map_weights.yaml): hard as the log said (`floor N: HARD`), else told by
    the Costs read (a hard battle costs 85, a normal one 75). The boss is not weighted: it scores as unknown, as the
    bot's route does."""
    data = yaml.safe_load((TOOLS.parent / "assets/resource/base/data/map_weights.yaml").read_text(encoding="utf-8"))
    if hard is None:
        costs = {str(c) for c in data["node_costs"]["hard"]} - {str(c) for c in data["node_costs"]["normal"]}
        hard = any(str(n.get("cost")) in costs for n in nodes.values())
    return data["hard" if hard else "normal"]


def smooth(canvas: Image.Image, paint) -> None:
    """paint(draw, k) on a layer SMOOTH times larger, scaled down onto canvas (RGBA)."""
    layer = Image.new("RGBA", (canvas.width * SMOOTH, canvas.height * SMOOTH), (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer), SMOOTH)
    canvas.alpha_composite(layer.resize(canvas.size, Image.LANCZOS))


def badge(d, x, y, n, r, k):
    x, y, r = x * k, y * k, r * k
    d.ellipse([x - r, y - r, x + r, y + r], fill=BLUE + (255,), outline=(0, 0, 0, 255), width=2 * k)
    d.text((x, y), str(n), font=font(16 * k), fill=(0, 0, 0), anchor="mm")


def draw_map(shots, offsets, drags, nodes, path, fix, floor: int, hard: bool | None = None) -> Image.Image:
    """offsets: the x of each shot on the picture (the slides measured, or the log's px); drags: the log's; hard: the
    floor's difficulty as the log said, None to tell it by the Costs.

    One header line (the floor, the route's steps with their weights and its score, the drags and nodes read), the
    map, the legend flowing over as many lines as it needs. Each node: a box in its colour (one ring per colour), its
    label hanging from the box's bottom edge as wide as the box (the type and its route weight), a line per note under
    it, widened to a note longer than the box; boxes and labels half see-through."""
    logged = list(accumulate((px for _, px, _ in drags), initial=0))
    f, fs, fx, ft = font(18), font(16), font(14), font(24)
    weights = map_weights(nodes, hard)
    weight = lambda t: weights.get(t, weights["unknown"])  # noqa: E731
    width = W + int(offsets[-1])
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    explain = "數字＝路線分數，越低越優先"
    canvas = Image.new("RGBA", (width, TOP + H + 3 * LINE), BG + (255,))  # cropped to the legend's lines
    for im, off in zip(shots, offsets):
        canvas.paste(im.convert("RGB"), (int(off), TOP))

    def where(k, row):
        """A node sits where the shot it was last read in shows it: the log's column grid, moved by what that shot's
        offset differs from the log's px."""
        # a node the bot did not list: the last shot that shows its column
        s = nodes[k, row]["stage"] if (k, row) in nodes else max((i for i in range(len(offsets)) if 60 <= COLX(k) - logged[i] <= 1200), default=0)
        return COLX(k) + offsets[s] - logged[s], ROWY[row] + TOP

    pts = [(BUS[0], BUS[1] + TOP)] + [where(k, row) for k, (row, _) in enumerate(path[0], 1)] if path else []
    smooth(canvas, lambda d, k: [d.line([(x * k, y * k) for x, y in pts], fill=c, width=w * k, joint="curve")
                                 for c, w in (((0, 0, 0, 170), 11), (BLUE + (235,), 6))] if pts else None)
    shapes, texts, used = [], [], {BLUE} if pts else set()

    def node(x, y, rings, rows):
        """rings: the box's colours, outermost first; rows: (left, right, colour) of the label, then the notes."""
        used.update(rings)
        for i, col in enumerate(rings):
            e = EDGE - 5 * i
            shapes.append(([x - e, y - e, x + e, y + e], None, col + (210,), (True, True, False, False)))
        top = y + EDGE
        for j, (left, right, col) in enumerate(rows):
            (h, alpha), last = (24, 110) if j == 0 else (22, 60), j == len(rows) - 1
            # a row with no weight (a note, a FIX line, a missed node's label) longer than the box widens its plate to
            # the right; a node's label is the box's width
            right_x = x + EDGE if right else max(x + EDGE, x - EDGE + 14 + probe.textlength(left, font=fs if j == 0 else fx))
            shapes.append(([x - EDGE, top, right_x, top + h], col + (alpha,), None, (False, False, last, last)))
            lit = (255, 255, 255) if j == 0 else tuple(min(255, v + 60) for v in col)
            texts.append(((x - EDGE + 7, top + h / 2), left, "lm", lit, fs if j == 0 else fx))
            if right:
                texts.append(((x + EDGE - 7, top + h / 2), right, "rm", lit, fs))
            top += h

    for (k, row), n in sorted(nodes.items()):
        real = fix.get(f"c{k}/{row}")
        notes = [(t, det) for t, det in n["notes"] if not (t == "cost_none" and any(u == "cost_miss" for u, _ in n["notes"]))]
        rings = ([ORANGE if real[0] == "cost" else RED] if real else []) + list(dict.fromkeys(NOTE_COLOUR[t] for t, _ in notes)) or [GREEN]
        rows = [(n["type"], str(weight(n["type"])), rings[0])] + [(note_text(t, n), "", NOTE_COLOUR[t]) for t, _ in notes]
        if real:
            rows.append((f"Cost 讀錯：{real[1]}" if real[0] == "cost" else f"實為 {real[0]}", "", rings[0]))
        node(*where(k, row), rings, rows)
    for key, real in fix.items():
        if real[0] == "missed":
            k, row = int(key[1:].split("/")[0]), key.split("/")[1]
            node(*where(k, row), [ORANGE], [(real[1], "", ORANGE)])

    def plates(d, k):
        for box, fill, outline, corners in shapes:
            d.rounded_rectangle([v * k for v in box], 6 * k, fill=fill, outline=outline, width=4 * k if outline else 0, corners=corners)
    smooth(canvas, plates)
    d = ImageDraw.Draw(canvas, "RGBA")
    for xy, text, anchor, col, fnt in texts:
        d.text(xy, text, font=fnt, fill=col, anchor=anchor)

    # header: the floor, the steps (number, type, weight) summed to the route's score; the drags and nodes at the right
    y, badges = TOP // 2, [(x - EDGE, y - EDGE, i, 12) for i, (x, y) in enumerate(pts[1:], 1)]
    d.text((16, y), f"第 {floor} 層", font=ft, fill=(255, 255, 255), anchor="lm")
    x = 104
    for i, (_, t) in enumerate(path[0] if path else [], 1):
        badges.append((x + 11, y, i, 11))
        d.text((x + 28, y), t, font=f, fill=(240, 240, 240), anchor="lm")
        x += 28 + d.textlength(t, font=f) + 5
        d.text((x, y + 1), str(weight(t)), font=fs, fill=(175, 175, 175), anchor="lm")
        x += d.textlength(str(weight(t)), font=fs) + 10
        if i < len(path[0]):
            d.text((x, y), "+", font=f, fill=(110, 110, 110), anchor="lm")
            x += 22
    if path:
        d.text((x + 4, y), f"＝ {path[1]}", font=f, fill=(255, 255, 255), anchor="lm")
    d.text((width - 16, y), f"拖曳 {len(drags)} 次　讀到 {len(nodes)} 個節點", font=fs, fill=(175, 175, 175), anchor="rm")
    smooth(canvas, lambda dd, k: [badge(dd, *b, k) for b in badges])

    # legend: the colours this picture uses, the route last, flowing over lines; what the numbers are at the right of
    # the last line, or below it when there is no room
    d = ImageDraw.Draw(canvas, "RGBA")
    x, y = 16, TOP + H + LINE // 2
    for col in [c for c in LEGEND_TEXT if c in used]:
        text = LEGEND_TEXT[col]
        if x > 16 and x + 32 + d.textlength(text, font=fs) > width - 16:
            x, y = 16, y + LINE
        if col == BLUE:
            d.line([x, y, x + 24, y], fill=col, width=6)
        else:
            d.rectangle([x + 2, y - 10, x + 22, y + 10], outline=col, width=4)
        d.text((x + 32, y), text, font=fs, fill=(175, 175, 175), anchor="lm")
        x += 32 + d.textlength(text, font=fs) + 28
    if x + d.textlength(explain, font=fs) > width - 16:
        y += LINE
    d.text((width - 16, y), explain, font=fs, fill=(130, 130, 130), anchor="rm")
    return canvas.crop((0, 0, width, y + LINE // 2)).convert("RGB")


def drag_steps(block, stages, drags, path, floor: int, t0: float, t1: float) -> list[dict]:
    t_plan, first = block[-1][0] - 0.3, stages[0].get("t1", block[0][0])
    steps, prev = [{"from": t0, "to": first, "title": f"第 {floor} 層：先讀巴士加 {len(stages[0]['cols'])} 欄"}], first
    for n, (t, px, col) in enumerate(drags):
        nxt = drags[n + 1][0] if n + 1 < len(drags) else t_plan
        steps += [{"from": prev, "to": t, "title": f"拖曳地圖，位移 {px} px"},
                  {"from": t, "to": nxt, "title": f"從第 {col} 欄接著讀，拼成整層"}]
        prev = nxt
    if path:
        steps.append({"from": t_plan, "to": t1, "title": f"規劃路線，分數 {path[1]}：" + " > ".join(f"{r} {t}" for r, t in path[0])})
    return [{**s, "from": hms(s["from"]), "to": hms(s["to"])} for s in steps if s["from"] < s["to"]]


def logged_hard(msgs, floor: int, until: float) -> bool | None:
    """The difficulty the bot logged for the floor (`floor N: HARD|NORMAL`), the last time before until (the map's
    reading: a log of several runs has the floor once per run); None when it never did."""
    said = [x for t, x in msgs if t <= until and re.fullmatch(rf"floor {floor}: (HARD|NORMAL)", x)]
    return said[-1].endswith("HARD") if said else None


def map_cmd(a) -> None:
    log, out = read_log(a.log), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    block = floor_block(maalc(log), a.floor, secs(a.after) if a.after else None)
    stages, drags, path = parse_map(block)
    nodes, fix = node_table(stages, drags), json.loads(Path(a.fix).read_text(encoding="utf-8")) if a.fix else {}
    footage, masks = Footage(a.video), load_masks(masks_path(a))
    # The floor's first reading (a floor's block opens at `floor N's map is up, floor N+1 next; waiting`, while the
    # last floor's map still shows), then the first after each `dragged` line.
    first = next((t for t, x in block if x.startswith(("map: node at", "map: column"))), block[0][0])  # none read: the block's first line
    reads = [first] + [t + 0.1 for t, _, _ in drags]
    times, grays = frames(footage, reads[0] - 0.5, block[-1][0] + 0.5, 10, gray=True)
    idx = pick_shots(times, motion(grays), reads)
    shots = [apply_masks(grab(footage, times[i]), masks) for i in idx]
    for n, im in enumerate(shots):
        im.save(out / ("before-1.png" if n == 0 else f"after-{n}.png"))
    gray = [np.asarray(im.convert("L")) for im in shots]
    slides = [measure_shift(gray[n], gray[n + 1], px) for n, (_, px, _) in enumerate(drags)]
    offsets = list(accumulate((s[0] if s else px for s, (_, px, _) in zip(slides, drags)), initial=0))
    measured = [s and s[0] for s in slides]
    draw_map(shots, offsets, drags, nodes, path, fix, a.floor, logged_hard(maalc(log), a.floor, block[-1][0])).save(out / "stitched.png")
    (out / "route.json").write_text(json.dumps({
        "floor": a.floor, "drags": [{"t": hms(t), "px": px, "from_column": c, "measured": m, "score": s and round(s[1], 3)}
                                    for (t, px, c), m, s in zip(drags, measured, slides)],
        "path": path and {"nodes": [" ".join(p) for p in path[0]], "score": path[1]},
        "nodes": [{"column": k, "row": row, **n, "fix": fix.get(f"c{k}/{row}")} for (k, row), n in sorted(nodes.items())],
        "shots": [hms(times[i]) for i in idx]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"floor {a.floor}: {len(nodes)} nodes, {len(drags)} drags -> {out / 'stitched.png'}")
    if a.clip:
        t0, t1 = block[0][0] - 0.5, block[-1][0] + 2.0
        annotated_clip(footage, t0, t1, out / "drag-clip.mp4", touches(log, t0, t1),
                       drag_steps(block, stages, drags, path, a.floor, t0, t1), a)

