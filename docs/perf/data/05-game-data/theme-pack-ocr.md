# Theme pack title OCR, offline (#240, 2026-10-22)

The numbers in [05-game-data.md](../../../spec/05-game-data.md) section 2 come from here. Run with the agent's own
`actions.pack_titles` and `run_start.match_card` at the PR #243 base, in a MaaFramework task on still images (no
emulator). The screenshots (two under `tests/screens/`, the rest live captures from 2026-10-13), the live run logs and
the one-off script stayed on the developer's machine. Each matched name was checked against its screenshot; 15, 19
and 22 are the same scene.

## Every card

| Page | Card | OCR lines | Matched | Correct |
|---|---|---|---|---|
| tests/screens/ThemePack.png | 1 | `To be Crushed` | To be Crushed | yes |
| tests/screens/ThemePack.png | 2 | `Nagel und Hammer` | Nagel und Hammer | yes |
| tests/screens/ThemePack.png | 3 | `To be Cleaved` | To be Cleaved | yes |
| tests/screens/ThemePackNormal.png | 1 | `Automated Factory` | Automated Factory | yes |
| tests/screens/ThemePackNormal.png | 2 | `enUPAm` / `The Outcast` | The Outcast | yes |
| tests/screens/ThemePackNormal.png | 3 | `The Unloving` | The Unloving | yes |
| tests/screens/ThemePackNormal.png | 4 | `Nagel und Hammer` | Nagel und Hammer | yes |
| tests/screens/ThemePackNormal.png | 5 | `The Forgotten` | The Forgotten | yes |
| live 11 | 1 | `Flat-broke Gamblers` | Flat-broke Gamblers | yes |
| live 11 | 2 | `eOPAnS` / `The Unloving` | The Unloving | yes |
| live 11 | 3 | `Nagel und Hammer` | Nagel und Hammer | yes |
| live 12 | 1 | `Nest, Workshop, and` / `Technology` | Nest, Workshop, and Technology | yes |
| live 12 | 2 | `To be Pierced` | To be Pierced | yes |
| live 12 | 3 | `LImBUS` / `The Forgotten` | The Forgotten | yes |
| live 15 | 1 | `LImBUS` / `Nest, Workshop, and` / `Technology` | Nest, Workshop, and Technology | yes |
| live 15 | 2 | `To be Pierced` | To be Pierced | yes |
| live 15 | 3 | `The Forgotten` | The Forgotten | yes |
| live 19 | 1 | `LImBUS` / `Nest, Workshop, and` / `Technology` | Nest, Workshop, and Technology | yes |
| live 19 | 2 | `To be Pierced` | To be Pierced | yes |
| live 19 | 3 | `The Forgotten` | The Forgotten | yes |
| live 22 | 1 | `Nest, Workshop, and` / `Technology` | Nest, Workshop, and Technology | yes |
| live 22 | 2 | `To be Pierced` | To be Pierced | yes |
| live 22 | 3 | `The Forgotten` | The Forgotten | yes |
| live 177 | 1 | `enu` / `Charm, Wander,` / `Doubt` | Charm, Wander, Doubt | yes |
| live 177 | 2 | `Insignificant Envy` | Insignificant Envy | yes |
| live 177 | 3 | `Walpurgis` / `Hatred and 'Despair` | Walpurgis Night: Hatred and Despair | yes |
| live 197 | 1 | `LCB Regular Check-up` | LCB Regular Check-up | yes |
| live 197 | 2 | `mBDS` / `Mountain of Corpses,` / `Sea of Blood` | Mountain of Corpses, Sea of Blood | yes |
| live 197 | 3 | `Poised Breathing` | Poised Breathing | yes |
| live 222 | 1 | `Mnestic Experience` | Mnestic Experience | yes |
| live 222 | 2 | `Tyrannical Pride` | Tyrannical Pride | yes |
| live 222 | 3 | `Sinking Deluge` | Sinking Deluge | yes |

## Past live logs: cards left unmatched

119 distinct `floor N packs:` log lines from earlier live runs, 353 cards, 21 left unmatched at the time:

| Reading | Times | Cause | Current matcher | AALC fragment |
|---|---|---|---|---|
| `Timekilling Time BokGak`, `Yield My Flesh to Claim Their Bones BokGak` | 2 | re-run suffix (older matcher) | matches | — |
| `LImBUS Rising Power Supply`, `mBU! Addicting Lust` | 2 | logo prefix (older matcher) | matches | — |
| `World Lake`, `Abyss Crawling`, `WONr Abyss Crawling` | 3 | two-line title read in reverse order (likely the tilted card; unverified) | matches since #240 (lines also read bottom up) | `lake`, `abyss` |
| `HellOBus`, `HellBus`, `aHelIOBis` | 7 | stylized title art: S.E.A.'s card says "The Magic Hello Bus" (#246, recordings; the guess Hell's Chicken was wrong) | `HellOBus`, `HellBus` match since #246 (`titles`) | no |
| `Mirac inDistrict niiaco m uistir` | 1 | stylized title art read mid-swing (#246) | no | no |
| `WalpurgisN The Noon of` | 1 | The Noon of Violet, "Walpurgis Night" above its name (#246, recordings) | matches since #246 (`titles`) | no |
| `Emotio` | 1 | read before the third card slid in: Emotional Judgment cut, Hell's Chicken missed (#246, recordings) | waits for the cards since #246 | no |
| `Time` beside `Timekilling Time` | 2 | one title line split into two boxes 81 px apart on a tilted card (#246, recordings) | waits for the cards since #246 | would read it as Timekilling Time |
| `Line` | 2 | Line 1–5 alike | shares their weight | — |

## Recordings: fixes compared (#246, 2026-10-22)

49 pack pages from the screen recordings of four live sessions (adb `screenrecord` segments and two window captures;
2026-10-19 to 2026-10-22, NORMAL and HARD), every frame scaled to 720p and read with the agent's own OCR node and matcher. Truth:
the card names read most often across a page's frames, checked by eye where they disagree (S.E.A., The Noon of Violet).
Baseline: the bot's own log lines for those pages. Swing window: from the first frame that reads every card to 300 ms
before the pull (1354 frames, 918 ms on average). "All right": every card named right; "pick": the default plan's pick
has the best true weight. The recordings, frames and scripts stayed on the developer's machine.

What the cards do: dealt cards slide in for ~0.6 s and then swing; per-card motion between frames 100 ms apart stays at
13–30 grey levels until ~2.6 s and drops under 0.4 at 2.7–2.9 s after the deal (two deals of one page: before and after
a difficulty switch). The bot read 0.6–1.1 s after the page header showed.

| Fix | Measured | Extra time | Complexity | Taken |
|---|---|---|---|---|
| Baseline (log) | 138/147 cards, 41/49 pages all right, pick 46/49 | — | — | — |
| Single frame in the swing window | cards 87.6%, all right 75.4%, pick 93.8% | — | — | — |
| a. Wait until the cards stop | still frames 43/43 all right (and #240's 12 stills, 32/32 cards); detector "card band alike to 0.2 s before, twice in a row" fired before the pull on 0 of the 47 other pages, at 2.9 s after the deal on the re-dealt page; once in a row fired mid-swing (2.3 s, cards still moving) | ~+2 s per floor | `still(runs=2)`, one call | yes |
| b. Vote 3 frames 100 ms apart | swing window: all right 83.0%, pick 98.6% (3×200 ms 80.1%, 5×150 ms 78.9%); no gain on still frames | +0.2–0.6 s | slots by index (cards slide >100 px) | no: a. makes it redundant |
| c. Regroup boxes: chain 110 px / join boxes ≤ 15 px apart on a row | all right 74.0% / 55.1% (slid-in cards touch) | 0 | small | no |
| d. Covers (#242), SIFT, ratio 0.6, scale 1.55 | 298/459 cards (64.9%) in the swing window: event art strong (S.E.A. 6/6, The Noon of Violet 7/7, LCB Regular Check-up 7/7, Hell's Chicken 6/6), sin packs weak (Addicting Lust 0/13, Treadwheel Sloth 0/10); grey template match at best 27.9% | ~116 ms per card for 94 covers (Python cv2) | covers in the bundle, a fallback for unmatched cards | later: needs #242 |
| e1. Title art reads (`titles`) | all right 78.9%, cards 88.9%; S.E.A. frames 4/51 → 42/51, The Noon of Violet 44/62 → 53/62 | 0 | two data lines | yes |
| e2. Only the floor's packs as candidates | no change (75.4%) | 0 | small | no |
