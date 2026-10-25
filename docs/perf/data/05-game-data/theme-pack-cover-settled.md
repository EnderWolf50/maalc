# Theme pack covers on settled cards, offline (2026-10-24)

Question: [theme-pack-ocr.md](theme-pack-ocr.md) row d (SIFT on the covers) was measured on cards still swinging, and with
the old covers, whose seven-sin packs were blank backgrounds. The bot now waits until the cards stop (`still(runs=2)`) before it reads
([theme-pack-recognition.md](theme-pack-recognition.md)). How well do the covers (#242, the current ones) read a **settled** card, and
would cover-first beat the OCR path?

## Data

The 112 pages and 531 cards of [theme-pack-recognition.md](theme-pack-recognition.md), found again by the hash of each page (all 112
of its [card list](theme-pack-recognition-cards.csv) matched, 531 cards). A card's truth is that list's pack, so the numbers
below measure the cover readers against the pack the full reading (name, title art, keyword, cover) named, not against a hand check.
The pages stayed on the developer's machine; so did the one-off script (OpenCV SIFT, BFMatcher, Lowe ratio 0.6, covers scaled 1.55,
a match counts as good under the ratio; a card is read as the cover with the most good matches). What each reader picked for every
card, with its verdict, is in [theme-pack-cover-settled-cards.csv](theme-pack-cover-settled-cards.csv) (531 rows, a capture by the hash
of its file), so every number below can be counted from it; the times can not (they depend on the machine). The script is not in `tools/`:
it needs the local captures and the OpenCV probe group, and the OCR answers it reads come from `tools/pack_stats.py`'s `--cache`.

Each card (a 260 px wide column of the 720p page around its centre) is read five ways:

- **A** the whole card, against all 94 covers.
- **B** the whole card, against the covers of the page's floor only.
- **C** the title strip (card rows 300–500), against the covers' title rows (38–88 % of the height), all 94.
- **D** the title strip, floor covers only.
- **D+colour** D's five best, re-ranked by good matches × the intersection of the HSV (16 × 8 hue/saturation) histograms of the card art and the cover art.
- **thumbnail** `pack_cover.read_cover` as the bot runs it (12 × 16 colour thumbnail, correlation ≥ 0.5, lead ≥ 0.1), nothing else.

The floor of a page: from the folder of the capture (`run N / floor N`); the difficulty of a run is not in its file names, so it is the one
under which most of the run's cards are packs of their floor (`theme_packs.yaml`) (inferred). The 62 cards of pages without such a folder (the repo's `tests/screens/` pages and a fixture) have none; their floor is the (difficulty, floor) with the fewest packs that holds all the page's cards (inferred, so
B and D are a little generous on them; on the 469 cards whose floor comes from a folder, B reads 466, D 465 and D+colour 466 right). In 3 cards of 531 the true pack is not among the floor's covers (Miracle in District 20 on a
HARD floor 5 page, which `theme_packs.yaml` lists for `H34` only: a gap of the list or of the inferred difficulty, unverified); B and D cannot read them.

## Results

| reading | right of 531 | wrong | silent | wrong packs | mean per card |
|---|---|---|---|---|---|
| A whole card, 94 covers | 531 (100.0 %) | 0 | 0 | none | 416 ms |
| B whole card, floor covers | 528 (99.4 %) | 3 | 0 | Miracle in District 20 ×3 (not a floor candidate) | 104 ms |
| C title strip, 94 covers | 530 (99.8 %) | 1 | 0 | Line 4 - Section #3 ×1 (named Section #4, its sibling) | 159 ms |
| D title strip, floor covers | 527 (99.2 %) | 4 | 0 | Miracle in District 20 ×3, Line 4 - Section #3 ×1 | 42 ms |
| D+colour | 528 (99.4 %) | 3 | 0 | Miracle in District 20 ×3 | 43 ms |
| thumbnail `read_cover` | 467 (87.9 %) | 0 | 64 | none; silent on The Outcast 15, Devoured Gluttony 15, Thunder and Lightning 4, Sinking Deluge 4, 3 each of Miracle in District 20, Mountain of Corpses Sea of Blood, Tangling Lust, 2 each of Sinking Pang, Repressed Wrath, Nocturnal Sweeping, Timekilling Time, Line 4 - Section #3, and others | 3 ms |

The thumbnail without its gate (best correlation taken as it is): 510 of 531 right, 21 wrong.

Against the swing-window numbers of the same covers and script on 537 cards of the swing window of the #246 recordings, every 8th frame
(A 84.2 %, 449 ms; D 88.5 %, 43 ms; B 84.2 %, 98 ms; C 87.5 %, 188 ms; those frames stayed on the developer's machine, and the figures are
quoted in [theme-pack-ocr.md](theme-pack-ocr.md) row d): on a settled card
A rises to 100 % and D to 99.2 %, at the same cost. The seven-sin packs, which the old covers could not tell apart, are all right in A, C, D and
D+colour (D's four misses are Miracle and Line 4). The colour step changes D by one card (the Line 4 - Section #3 card is then right), and no sin pack needed it: **colour is not needed on settled cards**.

## Against the OCR path

`actions.ocr` on the card strip `PACK_TITLES` takes **116 ms per page** (112 pages, second pass, median 107, 90th percentile 158, max 189; MaaFramework, no
emulator). Pages hold 4.7 cards on average. The 531 of 531 of the OCR path is by definition: the truth of a card is what that path
read, confirmed by the keyword or the cover alone for every card (theme-pack-recognition.md), so it is not an independent score:

| way to read a page | per page | cards right |
|---|---|---|
| OCR (the bot now) | 116 ms | 531 / 531 (the truth itself, see above) |
| thumbnail only | 15 ms (3.2 ms per card × 4.7) | 467 / 531, 64 silent; all cards of a page read on 64 of 112 pages |
| D, SIFT title strip, floor covers | 199 ms | 527 / 531 |
| A, SIFT whole card, 94 covers | 1973 ms | 531 / 531 |

- The only reader faster than the OCR is the thumbnail, and it leaves 64 cards (12 %) silent: it reads every card on 64 of 112 pages (57 %), and the
  OCR would still run on the other 43 %. As a first pass that is 15 + 0.43 × 116 = about 65 ms per page against 116 ms, about 50 ms saved per page
  (derived from the means above, not timed as one flow). That holds only if the card centres are known without the OCR: the thumbnail reads the card at
  a centre `x`, which the OCR boxes supply today. The cards stand on a grid of the card count (`pack_cover.card_image` snaps `x` to it, so the thumbnail figures above
  are what a grid gives; the SIFT readers cropped around the OCR's `x`), but how the bot would get the count without the OCR is not measured here.
- SIFT (D, 199 ms per page) costs more than the whole OCR (116 ms), and A (1.97 s) is 17 times more. Neither saves time as a first pass; as a
  second pass after the OCR they only add time.
- SIFT agrees with the truth on 527–531 of 531, so it could replace the text only on accuracy, not on speed. It could not do so for the
  floor-candidate readings (B, D) unless `theme_packs.yaml`'s floor lists are right for every dealt pack (3 misses here).

Conclusion on these 531 cards: the covers can not replace the text (the thumbnail is silent on 12 % of cards, SIFT is slower than the OCR page read); the one
saving left is the thumbnail as a first pass, about 50 ms per page at best, if the card centres come without the OCR. Next to the 2.7–2.9 s the cards need
to stop (theme-pack-ocr.md, a.) that is under 2 %.
Not measured: pages the bot has not dealt (20 of the 94 packs never appear in the 112 pages), and cards read with a card count taken without the OCR.
