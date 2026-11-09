# Evidence style

How an evidence still or clip looks. A rule below is the user's own word, or the version the user accepted, with its date. `tools/live/evidence.py` (`draw_map`) is the code that draws it; where this file and the code differ, the code is what the user accepted. `tools/live/reel.py` builds a review reel; it refuses a chapter with an unwritten draft, a caption that breaks the language or duration rule below, boxes with no named grid or a box outside it, and warns about log text.

## What goes in a report

- A live test, experiment or acceptance run comes back with images, clips and annotations, not text alone: routing (the drag, the nodes recognised, the weight per path, the route chosen) drawn on the screenshots. Captions, boxes and labels are burned into the clips. [user, 2026-10-18]
- Every run reports all the map routing and all the theme pack picks, per floor: the stitched floor with every node it read labelled, and the pack page with its cards, weights and the pick. Post them to the issue or PR when useful (#251 routes, #252 packs). [user, 2026-10-22]
- A still that leaves a read node unlabelled cannot be checked. Label every node the bot read, not only the route. [2026-10-22: the user could not check such a still]
- A GUI check returns screenshots of the GUI window only, never the full screen. [user rule, 2026-10-30]

## Privacy

AGENTS.md "Public repo" is the rule: the UID plate, the account e-mail and the player name above the LV panel (36,626,98,20 in game pixels) are blacked out before a still or clip leaves `.local/`. `evidence.py` applies `.local/evidence/masks.json` to everything it writes; a device screenshot goes through `evidence.py mask`. A GUI screenshot of the settings app can show a webhook URL or a plan name: look at it before it is attached.

## The route picture (`evidence.py map`)

Settled over seven rounds with the user on 2026-10-27. Start a change to it from these rules, and show one variable per round, not a new design.

1. **Keep the original style; move positions.** "這幾種都不如原版...你可以自由改位置". Fonts, boxes, colours and the route stay; three redesigned variants were rejected.
2. **The legend lists only the colours the picture uses, and does not repeat a colour's name.** "color legend 不需要重複顏色的名稱".
3. **The header is one line.** "上方希望只剩一行". It holds the floor, the route's steps joined by `+` and ending in `= <score>`, and the drag and node counts small at the right. The score is written once ("路線分數寫了兩次" was a defect). Steps carry their number (the same numbers as the route on the map) or the Up/Middle/Down mark, one of the two ("上方 step 或 u/m/d 選一個放"); the connector is `+` or `>`, one of them ("上方 + 或 > 選一個放").
4. **Header text is small.** "上方文字大小調整，不需要這麼大".
5. **A node's label hangs from the box's bottom edge and is exactly as wide as the box.** "節點標籤還是沒有對齊框線寬度", "標籤右邊沒有切齊框線". PIL draws an outline inward, so the box's outer edge is the box coordinate; a label drawn 2 px wider overhangs on both sides. Draw box and label on the same supersampled layer with the same coordinates, or their pixel edges differ by 1 px.
6. **The score is inside the label** (type left, weight right), not a block of its own. "節點分數不要獨立區塊".
7. **Boxes and labels are semi-transparent**, in the colour of the box, with white text. "半透明不錯，我認為所有框線都可以改成這樣的風格". A solid colour block and a black plate were both rejected ("太搶眼"; "黑底很醜"). The code's values: box ring alpha 210, label plate 110, note plate 60 (`draw_map`, `node`).
8. **A note is the next segment under the label**, in a light tint of the note's colour and a smaller font, and the label with its notes reads as one unit with rounded bottom corners at the last segment. Not a separate capsule, and not stuck to the label as a second pill ("兩個標籤黏在一起還是很彆扭"). Keep a note short ("初讀 focused"). The unit takes the label's width.
9. **No jagged edges.** Circles, the route line, plates and box corners are drawn `SMOOTH` times larger and scaled down ("step number 圓形與路線都有點鋸齒").
10. **The caption under the picture is right-aligned**: "數字＝路線分數，越低越優先".
11. The user accepted round 7 with "非常好，採用這版".

Check by measurement, not by eye: the label's outer edge equals the box's outer edge, and a ring sampled across the box edge shows no stair step. `tests/test_live_evidence.py` checks the ring colour and that a plate widens to its label, not these two edges.

## Clips and stills in general

- `evidence-annotate` burns the touches, step captions, boxes and zoom into a clip; on Windows drawtext needs an explicit font file (`C:/Windows/Fonts/msjhbd.ttc`); without one it crashed (2026-10-18).
- The recording of a live test is the MuMu window only, 720p, with its title bar cropped: `screenrec.py start --window "Android Device" --crop-top 60`, the values every live test has used (the bar's height follows the display's scaling; check a first frame after a change); the other options are in `maalc-live-test` step 5. A GUI clip or still is the GUI window only.
- A clip may speed up or skip the stretches outside the issue's focus (battles, map walks, loading when the issue is the shop); the part the issue is about stays at normal speed. [user, 2026-11-04: 「非當次 issue 重點的證據片段可以些微加速跳過」] Mark each such stretch on the clip ("×4", "略過 2:10") so a reviewer knows it was cut; the archive recording stays uncut.
- Captions are Traditional Chinese in game terms: no log text, pipeline node names or function names. A game label the viewer must read stays as the game shows it, in 「」 (「To Window」, 「Parallel Superposition Mode : ON」). [user, 2026-11-09: 「部分 log 直出成 step，無法閱讀」; 「部分 step 顯示為英文，可以閱讀，但會增加驗收時的成本，請統一語系」] `evidence.py steps` writes drafts, not captions: one per moment (log lines less than 3 s after its first line join it), the log lines in `note` and an empty `title` that `reel.py` refuses until it is written. [main thread, 2026-11-09: 「草稿把 log 原文放進 `note`，`title` 留空…讓 `reel.py --check` 擋下沒改寫的草稿；同一刻、相隔不到規則時間的 log 行合併成一則草稿」]
- A caption stays up at least max(3 s, characters ÷ 5 s), spaces not counted: 20 characters, 4 s (the user leaves the numbers to us). Actions faster than that share one caption, or are held with a freeze frame or slow motion that the clip marks (「定格」, 「慢放 0.5×」), as a speed-up is marked. A speed-up inside a caption shortens it. [user, 2026-11-09: 「部分 step 顯示時間太短，無法閱讀」; the first reel had 98 of 167 captions under 3 s, 23 of them 0 s]
- A before/after step puts its side, 改前 or 改後, in the step's `tag`, which `evidence-annotate` shows in place of the step number (「改前 │ 等了 1.5 秒才重拖」), not at the head of the title. The tag needs a Chinese character and counts toward the caption's time like the title; `reel.py` warns about a title that opens with 「改前：」 or 「改後：」. [user, 2026-11-09: 「都跟進」, on the main thread's proposal to use the skill's new step `tag` for the before/after chapters]
- A clip with boxes names the grid they are written in: `box_space` in the reel manifest, `[1920, 1080]` for a touch log or `[1280, 720]` for game pixels. `reel.py` draws the boxes on the clip's grid from it, and refuses a clip with boxes and no `box_space`, or a box outside its own `box_space`. A box shows only while its target is on screen, and it is checked on stills before the clip is handed over (`reel.py` writes a sheet per chapter, one still at the middle of each caption). [2026-11-09: the #94 chapter's boxes were written in 1280x720 game pixels on a 1920x1080 grid and landed at 2/3 of their place, the lever's on the progress track; main thread, the same day: 「每個步驟檔（或 manifest 每章）都要寫明框是用哪個座標格寫的…沒寫的要擋下，寫了但框超出自己那個格子的也要擋」]
- `gh ... --attach '<file>#<alt>'`: the `#alt` works for images; a video takes no alt text, so attach it without. [2026-10-27, the `gh issue comment` error "cannot set alt text on video"]
- An attached file is described by its content in the text, never by a local path (AGENTS.md "Public repo").

## Review reel

A review reel strings the acceptance clips of several issues into one MP4, a chapter per issue, for the user to review in one sitting. `tools/live/reel.py` builds it from a manifest: it renders each clip from the uncut recording with `evidence-annotate`, plays the speed-ups, slow motion and freezes the manifest lists, and refuses a chapter whose captions or boxes break the rules above. `reel.py sheet` lays out a recording's frames over a stretch, one every few seconds and masked, to find the moments before the steps are written.

- The current chapter shows at every moment after the opening list: its number alone (`08`, as the opening list numbers it), issue and one line. The strip is a 56 px band above the 1280x720 picture, so it never hides game UI. [user, 2026-11-09: 「分了章節，但是影片播放過程中沒有『持續可見的』章節資訊，我只能依每個章節前面的 3s title 來判斷」; on the second reel, the same day: 「「第 xx/XX 章」不美觀，可能只顯示當前章節數字還比較好看」]
- The strip's number is amber text, not on a pill. [user, 2026-11-09: 「左上不要做成標籤，顏色字就好」]
- The speed and freeze marks (「快轉 4×」, 「慢放 0.5×」, 「定格」) sit in amber beside the clock in evidence-annotate's bottom-left corner, not on the strip: `reel.py` hands them to evidence-annotate as blocks beside the corner. A block fades in and out over 0.35 s, so a freeze's mark is centred on the held frame and also shows for 0.35 s on either side of it, and a speed mark whose edge is that close to a held frame is stretched to cover it. [user, 2026-11-09: 「感覺倍速可以整合到左下角時間就好」; user, 2026-11-10, on the mark that read 「停格」: 「定格」]
- The opening list fills the whole 1280x776 frame, with no strip above it. [user, 2026-11-09, on the second reel: 「目錄感覺不需要上方那條」]
- The opening list gives each chapter's start time, and the MP4 carries a chapter mark per chapter that a player can jump to. [user, 2026-11-09: 「開頭的清單沒有時間戳記」]
- A chapter shows the run that met the acceptance: cross-check it with the issue's acceptance comment. A failing run from before the fix appears only in a before/after chapter that says so. [2026-11-09: the #94 chapter of the first reel showed the run before PR #524, which read `oN`]
