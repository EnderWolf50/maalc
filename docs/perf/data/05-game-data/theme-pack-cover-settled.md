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
a match counts as good under the ratio; a card is read as the cover with the most good matches).

Each card (a 260 px wide column of the 720p page around its centre) is read five ways:

- **A** the whole card, against all 94 covers.
- **B** the whole card, against the covers of the page's floor only.
- **C** the title strip (card rows 300–500), against the covers' title rows (38–88 % of the height), all 94.
- **D** the title strip, floor covers only.
- **D+colour** D's five best, re-ranked by good matches × the intersection of the HSV (16 × 8 hue/saturation) histograms of the card art and the cover art.
- **thumbnail** `pack_cover.read_cover` as the bot runs it (12 × 16 colour thumbnail, correlation ≥ 0.5, lead ≥ 0.1), nothing else.

The floor of a page: from the folder of the capture (`run N / floor N`); the difficulty of a run is not in its file names, so it is the one
under which most of the run's cards are packs of their floor (`theme_packs.yaml`) (inferred). The 62 cards of pages without such a folder (the repo's `tests/screens/` pages and a fixture) have none; their floor is the (difficulty, floor) with the fewest packs that holds all the page's cards (inferred, so
B and D are a little generous on them). In 3 cards of 531 the true pack is not among the floor's covers (Miracle in District 20 on a
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

Against the swing-window numbers of [theme-pack-ocr.md](theme-pack-ocr.md) (A 84.2 %, 449 ms; D 88.5 %, 43 ms on 459 swinging cards of the recordings): on a settled card
A rises to 100 % and D to 99.2 %, at the same cost. The seven-sin packs, which the old covers could not tell apart, are all right in A, C and
D (0 wrong of their cards in A, C, D+colour; D's four misses are Miracle and Line 4). The colour step changes D by one card (the Line 4 - Section #3 card is then right), and no sin pack needed it: **colour is not needed on settled cards**.

## Against the OCR path

`actions.ocr` on the card strip `PACK_TITLES` takes **116 ms per page** (112 pages, second pass, median 107, 90th percentile 158, max 189; MaaFramework, no
emulator) and names 531 of 531 cards together with the keyword and cover paths. Pages hold 4.7 cards on average:

| way to read a page | per page | cards right |
|---|---|---|
| OCR (the bot now) | 116 ms | 531 / 531 (with keyword and thumbnail cover) |
| thumbnail only | 15 ms | 467 / 531, 64 silent; all cards of a page read on 64 of 112 pages |
| D, SIFT title strip, floor covers | 199 ms | 527 / 531 |
| A, SIFT whole card, 94 covers | 1973 ms | 531 / 531 |

- The only reader faster than the OCR is the thumbnail, and it leaves 64 cards (12 %) silent, so a page it reads whole (57 %) is still followed by the
  OCR on the other 43 % of pages. The OCR also gives where the cards are: the thumbnail reads the card at a centre `x`, which the OCR boxes supply.
  A cover-first pass that skips the OCR needs the card count and positions another way; a fixed grid from the card count is not measured here.
- SIFT (D, 199 ms per page) costs more than the whole OCR (116 ms), and A (1.97 s) is 17 times more. Neither saves time as a first pass; as a
  second pass after the OCR they only add time.
- SIFT reads 527–531 of 531, as the OCR path does (531), so it could replace the text only for accuracy's sake, not for speed. It could not do so for the
  floor-candidate readings (B, D) unless `theme_packs.yaml`'s floor lists are right for every dealt pack (3 misses here).

Conclusion on these 531 cards: a cover-first pass saves no time over the current OCR path; the thumbnail is the only faster reader and it is silent on 12 % of cards.
Not measured: pages the bot has not dealt (20 of the 94 packs never appear in the 112 pages), and cards read with a card count taken without the OCR.
