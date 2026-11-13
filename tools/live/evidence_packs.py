"""`evidence.py packs`: a still per theme pack reading, and how long the cards took from the deal to standing still
(evidence.py's docstring says what the still shows)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from live.evidence import (GREEN, YELLOW, H, W, Footage, annotated_clip, apply_masks, font, frames, grab, hms, load_masks, maalc,
                           masks_path, read_log)


def pack_readings(msgs, floor: int) -> list[dict]:
    """Each `floor N packs` line: its time, threshold, cards [(name, weight, event)] and the pulled card's name, the first
    `floor N: pull` before the floor's next `packs` line (a refresh's reading has none)."""
    reading = re.compile(rf"floor {floor} packs, threshold (-?\d+): (.*)")
    out = []
    for i, (t, x) in enumerate(msgs):
        if m := reading.match(x):
            cards = [(c[1], int(c[2]), bool(c[3])) for c in re.finditer(r"(?:^|, )(.+?) \((-?\d+)(, event)?\)(?=,|$)", m[2])]
            hit = None
            for _, y in msgs[i + 1:]:
                if reading.match(y):
                    break
                if hit := re.match(rf"floor {floor}: pull (.+) \((-?\d+)", y):
                    break
            out.append({"t": t, "threshold": int(m[1]), "cards": cards, "pull": hit and hit[1].strip("'\"")})
    return out


def card_rows(grays) -> list[tuple[float, float]]:
    """(mean brightness, mean abs difference from the frame before) of the card area, rows 150-600."""
    out, prev = [], None
    for g in grays:
        im = np.asarray(g[150:600], np.int16)
        out.append((float(im.mean()), 0.0 if prev is None else float(np.abs(im - prev).mean())))
        prev = im
    return out


EMPTY = 8  # mean brightness of an empty card area: black is 0, the starfield behind the cards 6.7 (floor 1, 2026-10-22)
# Mean abs change of a full card area in one frame that only a new hand makes: the 3 Refreshes of 2026-10-29 and
# 2026-11-07 changed it by 18.1-21.5 (the area dims to only 8.3-8.6, above EMPTY), while the dealt cards of those
# runs' 16 reads swing by at most 13.0.
SWAP = 15


def settle(rows, k_log: int):
    """(deal frame, settle frame or None, deal before the footage): the deal follows the last empty card area or
    swapped hand (a Refresh) before the log line; the cards stand still from the first of 8 frames each under 2 apart."""
    cuts = [i for i in range(min(k_log, len(rows) - 1) + 1)
            if rows[i][0] < EMPTY or (i and rows[i - 1][0] >= EMPTY and rows[i][1] >= SWAP)]
    deal = cuts[-1] + 1 if cuts else 0
    still = next((i for i in range(deal, len(rows) - 7) if rows[i][0] > 20 and all(rows[j][1] < 2 for j in range(i, i + 8))), None)
    return deal, still, not cuts


def centres(n: int) -> list[float]:
    return [640 + (i - (n - 1) / 2) * 210.5 for i in range(n)]


def draw_packs(raw: Image.Image, r: dict, banner: str) -> Image.Image:
    im = raw.copy()
    d, small = ImageDraw.Draw(im, "RGBA"), font(20)
    for x, (name, weight, event) in zip(centres(len(r["cards"])), r["cards"]):
        sel = name == r["pull"]
        col = GREEN if sel else YELLOW
        d.rectangle([x - 105, 180, x + 105, 525], outline=col + (255,), width=8 if sel else 4)
        lines, cur = [], ""
        for word in name.split():
            if cur and d.textlength(f"{cur} {word}", font=small) > 200:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
        lines.append(("★ 選中  " if sel else "") + f"權重 {weight}" + (" (活動)" if event else ""))
        for j, line in enumerate(lines):
            w = d.textlength(line, font=small)
            d.rectangle([x - w / 2 - 3, 596 + j * 26, x + w / 2 + 3, 620 + j * 26], fill=(0, 0, 0, 230))
            d.text((x - w / 2, 596 + j * 26), line, font=small, fill=col)
    d.rectangle([0, 686, W, H], fill=(0, 0, 0, 230))
    d.text((8, 688), banner, font=font(24), fill=(255, 255, 255))
    return im


def packs_cmd(a, fps: int = 30) -> None:
    out, msgs = Path(a.out), maalc(read_log(a.log))
    out.mkdir(parents=True, exist_ok=True)
    footage, masks, res = Footage(a.video), load_masks(masks_path(a)), []
    for k, r in enumerate(pack_readings(msgs, a.floor), 1):
        _, off = footage.locate(r["t"])
        times, grays = frames(footage, max(r["t"] - 10.0, r["t"] - off + 0.2), r["t"] + 3.0, fps, gray=True)
        k_log = min(len(times) - 1, round((r["t"] - times[0]) * fps))
        deal, still, partial = settle(card_rows(grays), k_log)
        raw = apply_masks(grab(footage, times[min(len(times) - 1, (still if still is not None else k_log) + 3)]), masks)
        raw.save(out / f"pack-{k}-raw.png")
        n, dur = len(r["cards"]), None if still is None else round(times[still] - times[deal], 2)
        msg = f"{n} 張卡，影片內沒有量到停住" if dur is None else f"{n} 張卡，發牌到停住 {dur:.1f} 秒" + ("，發牌起點在片段之前" if partial else "")
        draw_packs(raw, r, f"第 {a.floor} 層  第 {k} 次讀取  {msg}  log {hms(r['t'])}").save(out / f"pack-{k}.png")
        res.append({"k": k, "t_log": hms(r["t"]), "threshold": r["threshold"], "cards": r["cards"], "pull": r["pull"],
                    "settle_s": dur, "partial": partial, "log_after_settle_s": None if still is None else round(r["t"] - times[still], 2)})
        print(res[-1])
        if a.clip and still is not None:
            t_deal, t_still = times[deal], times[still]
            t0, t1 = t_deal - 0.8, t_still + 2.2
            steps = [{"from": hms(t0), "to": hms(t_deal), "title": f"第 {a.floor} 層選包頁"},
                     {"from": hms(t_deal), "to": hms(t_still), "title": f"發牌、搖擺：{t_still - t_deal:.1f} 秒"},
                     {"from": hms(t_still), "to": hms(t1), "title": f"卡片停住，log 讀出 {n} 張：選 {r['pull']}"}]
            annotated_clip(footage, t0, t1, out / f"pack-{k}-clip.mp4", {"space": [W, H], "pointer": "none", "events": []}, steps, a)
    (out / "packs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

