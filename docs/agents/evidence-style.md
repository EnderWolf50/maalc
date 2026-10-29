# Evidence style

How an evidence still or clip looks. A rule below is the user's own word, or the version the user accepted; `[main.20 10-27T07:47]` names the session part and the UTC time in the retro transcripts of 2026-10-30 (kept on one machine, so the bracket is a source note and not a link). `tools/live/evidence.py` (`draw_map`) is the code that draws it; where this file and the code differ, the code is what the user accepted.

## What goes in a report

- A live test, experiment or acceptance run comes back with images, clips and annotations, not text alone: routing (the drag, the nodes recognised, the weight per path, the route chosen) drawn on the screenshots. Captions, boxes and labels are burned into the clips. [user, 2026-10-18, memory `visual-live-test-reports`]
- Every run reports all the map routing and all the theme pack picks, per floor: the stitched floor with every node it read labelled, and the pack page with its cards, weights and the pick. Post them to the issue or PR when useful (#251 routes, #252 packs). [user, 2026-10-22, memory `route-and-pack-evidence-every-run`]
- A still that leaves a read node unlabelled cannot be checked. Label every node the bot read, not only the route. [same memory, "Why"]
- A GUI check returns screenshots of the GUI window only, never the full screen. [user rule, brief of this work package]

## Privacy

AGENTS.md "Public repo" is the rule: the UID plate, the account e-mail and the player name above the LV panel (36,626,98,20 in game pixels) are blacked out before a still or clip leaves `.local/`. `evidence.py` applies `.local/evidence/masks.json` to everything it writes; a device screenshot goes through `evidence.py mask`. A GUI screenshot of the settings app can show a webhook URL or a plan name: look at it before it is attached.

## The route picture (`evidence.py map`)

Settled over seven rounds with the user [main.20 10-27T06:12 to 07:47]. Start a change to it from these rules, and show one variable per round, not a new design.

1. **Keep the original style; move positions.** "這幾種都不如原版...你可以自由改位置" [06:15]. Fonts, boxes, colours and the route stay; three redesigned variants were rejected.
2. **The legend lists only the colours the picture uses, and does not repeat a colour's name.** "color legend 不需要重複顏色的名稱" [06:12].
3. **The header is one line.** "上方希望只剩一行" [07:08]. It holds the floor, the route's steps joined by `+` and ending in `= <score>`, and the drag and node counts small at the right. The score is written once ("路線分數寫了兩次" was a defect [07:06]). Steps carry their number (the same numbers as the route on the map) or the Up/Middle/Down mark, one of the two ("上方 step 或 u/m/d 選一個放" [07:11]); the connector is `+` or `>`, one of them ("上方 + 或 > 選一個放" [07:13]).
4. **Header text is small.** "上方文字大小調整，不需要這麼大" [07:02].
5. **A node's label hangs from the box's bottom edge and is exactly as wide as the box.** "節點標籤還是沒有對齊框線寬度" [07:08], "標籤右邊沒有切齊框線" [07:15]. PIL draws an outline inward, so the box's outer edge is the box coordinate; a label drawn 2 px wider overhangs on both sides. Draw box and label on the same supersampled layer with the same coordinates, or their pixel edges differ by 1 px.
6. **The score is inside the label** (type left, weight right), not a block of its own. "節點分數不要獨立區塊" [07:11].
7. **Boxes and labels are semi-transparent**, in the colour of the box, with white text. "半透明不錯，我認為所有框線都可以改成這樣的風格" [07:15]. A solid colour block and a black plate were both rejected ("太搶眼"; "黑底很醜" [07:02, 07:06]). The code's values: box ring alpha 210, label plate 110, note plate 60 (`draw_map`, `node`).
8. **A note is the next segment under the label**, in a light tint of the note's colour and a smaller font, and the label with its notes reads as one unit with rounded bottom corners at the last segment. Not a separate capsule, and not stuck to the label as a second pill ("兩個標籤黏在一起還是很彆扭" [07:06]). Keep a note short ("初讀 focused"). The unit takes the label's width.
9. **No jagged edges.** Circles, the route line, plates and box corners are drawn `SMOOTH` times larger and scaled down ("step number 圓形與路線都有點鋸齒" [07:11]).
10. **The caption under the picture is right-aligned**: "數字＝路線分數，越低越優先" [07:02, 07:09].
11. The user accepted round 7 with "非常好，採用這版" [07:47].

Check by measurement, not by eye: the label's outer edge equals the box's outer edge, and a ring sampled across the box edge shows no stair step (`tests/test_live_evidence.py`).

## Clips and stills in general

- `evidence-annotate` burns the touches, step captions, boxes and zoom into a clip; drawtext needs an explicit font file (`C:/Windows/Fonts/msjhbd.ttc`), without it ffmpeg crashes here. [memory `visual-live-test-reports`]
- The recording of a live test is the MuMu window only, 720p, with its 60 px title bar cropped (`maalc-live-test` step 5). A GUI clip or still is the GUI window only.
- `gh ... --attach '<file>#<alt>'`: the `#alt` works for images; a video takes no alt text, so attach it without. [main.20 10-27T06:09; the `gh issue comment` error "cannot set alt text on video"]
- An attached file is described by its content in the text, never by a local path (AGENTS.md "Public repo").
