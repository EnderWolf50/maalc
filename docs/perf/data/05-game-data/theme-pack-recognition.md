# Theme pack recognition, offline (#274, 2026-10-23)

The numbers in [05-game-data.md](../../../spec/05-game-data.md) section 2 ("every pack recognised") come from here. Run:

```
uv run python tools/pack_stats.py tests/screens/ThemePack*.png <captures> --glob "*raw*.png" --csv theme-pack-recognition-cards.csv
```

on 112 distinct theme pack pages: the six `tests/screens/ThemePack*.png` and the card pages of the six live runs of 2026-10-22
(each `floor N packs` reading's screenshot, pages with the same pixels counted once). The captures other than `tests/screens/`
stayed on the developer's machine; every card of them is listed in
[theme-pack-recognition-cards.csv](theme-pack-recognition-cards.csv) (a capture by the hash of its file) with its OCR lines, its pack,
the path that read it and two independent verdicts. The OCR runs in a MaaFramework task on the still image (`actions.ocr` on
`PACK_TITLES`), the cover art on the same image.
Rerun on 2026-10-25 on the same 112 pages after the covers' boss layer was fixed (the boss picture sat 5 to 14 px low): the OCR
readings are unchanged; the cover verdicts and the gate table below are the new covers'. Rerun again the same day after the
signature took the title band beside the picture (`pack_cover.BANDS`): cover verdicts and the gate table changed, nothing else.

## Truth, and what it does not show

- A card's truth is the pack the full reading (`+cover`) names. That is the reading under test, so each card also gets two verdicts
  that do not rest on the whole-title match: the cover art alone agrees on 509 of the 531 cards, is silent on 21 (boss silhouettes, look-alike
  covers and others; not classified card by card) and disagrees on 1: a HARD card of Timekilling Time BokGak, the re-run copy with
  its own boss picture, which has no cover here (the pack list leaves the BokGak copies out) and is read as Miracle in District 20;
  its title names it Timekilling Time. The keyword alone agrees on 526 and is silent on 5. Every card is confirmed by one
  of the two (0 of 531 by neither). The keyword reads the same OCR text as the title match, the cover reads the pixels. No card was
  checked by eye one by one: a pack both of them misread the same way would pass (unverified).
- The captures show **74 of the 94 packs** of the season; the 20 never dealt in them (The B.E., The Evil Defining, The
  Heartbreaking, La Manchaland Re-opening, Textbook, Storefront Campout, An Anarchy of Colors, Creed of Preservation, Readvent of
  Gluttony, Line 4 - Section #4, Crushers & Breakers, Unbound Wrath, Inert Sloth, Excessive Gluttony, Sunk Gloom, Pitiful Envy,
  Burning Haze, Dizzying Waves, Spring Cultivation, Mnestic Experience) are only covered by the per-pack table below: a pack's own
  name, its own cover pasted on a page and single words of its name, not a capture. "Every pack recognised" on a live page is not
  shown for them.
- The cover's threshold (`pack_cover.MIN_SCORE`, `MIN_LEAD`) was picked on these captures, not on held-out pages: the gate table
  below is the sweep (at 0.5 / 0.1, 510 cards read and 1 wrong, the BokGak card above; at a lead of 0.05, 3 wrong). The picture
  alone gave 490 read and 0 wrong at 0.5 / 0.1, 5 wrong at 0.05.
- A card that has no OCR box at all is lost: none of the 112 pages shows one.
- `S.E.A.` has no keyword of its own (`sea` is inside `Mountain of Corpses, Sea of Blood`); the keyword of its art title (`Hello Bus`, keyword `hello`) names its cards (10 keyword verdicts agree), and so does its cover.

## Readings

`main` main's `pack_titles` (boxes with a lowercase letter, columns within 80 px); `#270` PR #270's `pack_cards` (the same filter,
boxes within 15 px one card, a capitals-only card kept from 80 px wide); `list, no span` `pack_cards` now with the `CARD_SPAN` rule
off, the filter alone; `list` `pack_cards` now: only a box reading exactly a word of `NOT_TITLE` (`LIMBUS`, `COMPANY`, `LIMBUS
COMPANY`, `CAUTION`, `CLEAR BONUS`, `LV`) or nothing is dropped, texts within `CARD_SPAN` of each other are one card, name and title
art match; `+key` adds the keyword path, `+cover` the cover path (what `PickThemePack` runs); `#270+all` the #270 cards with both new
paths. "listed, no pack": the card is in the ranking but no pack names it (it takes the plan's unlisted weight, or the weight its
alike titles share); "not listed": no card of the reading stands within `CARD_SPAN` of it, so the bot cannot pull it; "extra
cards": cards of the reading with no card of the truth.

Where the cards were lost, by step (from the same run): `main` leaves out Line 1's capitals `MADNESS` three times (grouping: the card
is not listed) and cannot name `Line` twice (Line 1 and Line 5, name matching: Line 1-3, 5 alike), Miracle in District 20 twice (OCR:
art title read `InDistrict` / `miiracle` among noise) and Four Houses and Greed once (name matching: the `LImBUS` logo above the
title, which the new filter drops by name, and the title's lines read out of order). `#270` fixes the three capitals and leaves the other five. `list` leaves Miracle in District 20 three
times (the third is the card with capitals between its lines, which #270 named by name) and Line 5 once (`ROLIND` is capitals under noise); `+key` names Miracle (keyword `miracle`), `+cover` Line 5.

## The two filters

The 112 pages hold 1191 OCR boxes; 453 have no lowercase letter, which the #270 filter dropped unless the card's capitals stood 80 px
wide. The new filter drops 94: `LIMBUS` 83 times (the logo, also read `LImBUS`), `LV` twice (the level badge), 9 reads of nothing.
`COMPANY`, `LIMBUS COMPANY`, `CAUTION` and `CLEAR BONUS` appear 0 times (listed from the card's look: they sit behind and below the title
strip); the logo's second word reads as noise (185 distinct texts among the no-lowercase boxes, most of them such misreads: `WOPIS`,
`CIMPINS`), which the old filter dropped and now stays a line of its card: the name match reads past it when it comes before the title, but noise between the title's lines (one Miracle in District 20 card: `inDistrict`, `OROAOZO`, `中R电`, `0`, `miracle`) makes the whole-title match fail, and the keyword names the card. The capitals the old filter threw away that are
part of a title: `MADNESS` (Line 1), `THE DUSK OF AMBER`, `DUSK OF AMBER`, `OF AMBER`, `AMBER`, `MURDER`, `ON THE`, `WARP EXPRESS`, `LINE 2`,
`TIMKILLING`, `VIOLET`, `HATRED`, `S.E.A`, `ROLIND` (Merry-Go-Round, Line 5) and the Chinese art title of Nocturnal Sweeping. A lone
noise box (`M`, the badge's `IV`, `2`) is a card of its own without the lowercase rule: the `list, no span` row shows it, 3 extra
cards, so texts nearer than `CARD_SPAN` (105 px) by centre are one card. With that rule the filter alone gains a card over #270 (527
against 526); without it, it loses one (525).

## Results

112 pages, 531 cards, 74 of 94 packs seen

| reading | right | wrong | listed, no pack | not listed | extra cards | right of all |
|---|---|---|---|---|---|---|
| main | 523 | 0 | 5 | 3 | 3 | 98.5 % |
| #270 | 526 | 0 | 5 | 0 | 0 | 99.1 % |
| list, no span | 525 | 0 | 6 | 0 | 3 | 98.9 % |
| list | 527 | 0 | 4 | 0 | 0 | 99.2 % |
| +key | 530 | 0 | 1 | 0 | 0 | 99.8 % |
| +cover | 531 | 0 | 0 | 0 | 0 | 100.0 % |
| #270+all | 531 | 0 | 0 | 0 | 0 | 100.0 % |

| reading | name | title_art | keyword | cover |
|---|---|---|---|---|
| main | 509 | 14 | 0 | 0 |
| #270 | 509 | 17 | 0 | 0 |
| list, no span | 508 | 17 | 0 | 0 |
| list | 510 | 17 | 0 | 0 |
| +key | 510 | 17 | 3 | 0 |
| +cover | 510 | 17 | 3 | 1 |
| #270+all | 509 | 17 | 3 | 2 |

per pack (the keyword; cards among the captures; its own cover pasted on a page; single words of its name read alone):

| pack | keyword | cards seen | own cover | words by title | words by title or keyword |
|---|---|---|---|---|---|
| The B.E. | theb | 0 | read | 0/1 | 1/1 |
| The Forgotten | forgotten | 8 | read | 1/2 | 1/2 |
| The Outcast | outcast | 15 | read | 1/2 | 1/2 |
| Flat-broke Gamblers | flat | 22 | read | 0/3 | 1/3 |
| Automated Factory | factory | 14 | read | 0/2 | 1/2 |
| The Unloving | unloving | 16 | read | 1/2 | 1/2 |
| Nagel und Hammer | nagel | 15 | read | 0/3 | 1/3 |
| Faith & Erosion | faith | 15 | read | 0/2 | 1/2 |
| The Unconfronting | unconfronting | 8 | read | 1/2 | 1/2 |
| Nest, Workshop, and Technology | workshop | 15 | read | 0/4 | 1/4 |
| Falling Flowers | falling | 11 | read | 0/2 | 1/2 |
| Tearful Things | things | 9 | read | 0/2 | 1/2 |
| The Unchanging | unchanging | 1 | read | 1/2 | 1/2 |
| Lake World | lake | 10 | read | 0/2 | 1/2 |
| Crawling Abyss | abyss | 9 | read | 0/2 | 1/2 |
| The Evil Defining | evil | 0 | read | 0/3 | 1/3 |
| Dregs of the Manor | dregs | 13 | read | 0/3 | 1/3 |
| A Certain World | certain | 11 | read | 0/2 | 1/2 |
| The Heartbreaking | heartbreaking | 0 | read | 1/2 | 1/2 |
| La Manchaland Re-opening | opening | 0 | read | 0/2 | 1/2 |
| The Infinite Procession | infinite | 1 | read | 0/3 | 1/3 |
| The Dream Ending | dream | 1 | read | 0/3 | 1/3 |
| Four Houses and Greed | four | 5 | read | 0/4 | 1/4 |
| The Surrendered Witnessing | witnessing | 3 | read | 0/3 | 1/3 |
| Charm, Wander, Doubt | charm | 8 | read | 0/3 | 1/3 |
| Textbook | textbook | 0 | read | 1/1 | 1/1 |
| Blade and Artwork | blade | 1 | read | 0/3 | 1/3 |
| The Unsevering | unsevering | 1 | read | 1/2 | 1/2 |
| Storefront Campout | campout | 0 | read | 0/2 | 1/2 |
| An Anarchy of Colors | colors | 0 | read | 0/2 | 1/2 |
| Creed of Preservation | creed | 0 | read | 0/2 | 1/2 |
| Readvent of Gluttony | readvent | 0 | read | 0/2 | 1/2 |
| Line 1 | ine1 | 4 | read | 0/1 | 0/1 |
| Line 2 | ine2 | 2 | read | 0/1 | 0/1 |
| Line 3 | ine3 | 2 | read | 0/1 | 0/1 |
| Line 4 - Section #3 | ion3 | 2 | silent | 0/2 | 0/2 |
| Line 4 - Section #4 | ion4 | 0 | silent | 0/2 | 0/2 |
| Line 5 | ine5 | 1 | read | 0/1 | 0/1 |
| Slicers & Dicers | dicers | 6 | read | 0/2 | 1/2 |
| To be Cleaved | cleaved | 18 | read | 0/1 | 1/1 |
| Piercers & Penetrators | piercers | 7 | read | 0/2 | 1/2 |
| To be Pierced | pierced | 22 | read | 0/1 | 1/1 |
| Crushers & Breakers | crushers | 0 | read | 0/2 | 1/2 |
| To be Crushed | crushed | 19 | read | 0/1 | 1/1 |
| Repressed Wrath | repressed | 2 | silent | 0/2 | 1/2 |
| Unbound Wrath | unbound | 0 | silent | 0/2 | 1/2 |
| Emotional Repression | repression | 6 | read | 0/2 | 1/2 |
| Addicting Lust | addicting | 10 | read | 1/2 | 1/2 |
| Tangling Lust | tangling | 3 | read | 1/2 | 1/2 |
| Emotional Seduction | seduction | 9 | read | 0/2 | 1/2 |
| Treadwheel Sloth | treadwheel | 9 | read | 1/2 | 1/2 |
| Inert Sloth | inert | 0 | read | 0/2 | 1/2 |
| Emotional Indolence | indolence | 5 | read | 0/2 | 1/2 |
| Devoured Gluttony | devoured | 15 | read | 0/2 | 1/2 |
| Excessive Gluttony | excessive | 0 | read | 0/2 | 1/2 |
| Emotional Craving | craving | 3 | read | 0/2 | 1/2 |
| Degraded Gloom | degraded | 10 | read | 0/2 | 1/2 |
| Sunk Gloom | sunk | 0 | read | 0/2 | 1/2 |
| Emotional Flood | flood | 7 | read | 0/2 | 1/2 |
| Vain Pride | vain | 12 | read | 0/2 | 1/2 |
| Tyrannical Pride | tyrannical | 1 | read | 1/2 | 1/2 |
| Emotional Subservience | subservience | 7 | read | 0/2 | 1/2 |
| Insignificant Envy | insignificant | 5 | read | 1/2 | 1/2 |
| Pitiful Envy | pitiful | 0 | read | 0/2 | 1/2 |
| Emotional Judgment | judgment | 9 | read | 0/2 | 1/2 |
| Burning Haze | haze | 0 | read | 0/2 | 1/2 |
| Season of the Flame | flame | 3 | read | 0/3 | 1/3 |
| Trickled Sanguine Blood | trickled | 1 | read | 0/3 | 1/3 |
| Mountain of Corpses, Sea of Blood | corpses | 3 | read | 0/4 | 1/4 |
| Dizzying Waves | waves | 0 | read | 0/2 | 1/2 |
| Abnormal Seismic Zone | zone | 3 | read | 0/3 | 1/3 |
| Crushing External Force | force | 2 | read | 0/3 | 1/3 |
| Unrelenting Might | might | 3 | read | 1/2 | 2/2 |
| Sinking Pang | pang | 2 | read | 0/2 | 1/2 |
| Sinking Deluge | deluge | 4 | read | 0/2 | 1/2 |
| Deep Sigh | deep | 1 | read | 0/2 | 1/2 |
| Poised Breathing | poised | 1 | read | 0/2 | 1/2 |
| Rising Power Supply | power | 2 | read | 0/3 | 1/3 |
| Thunder and Lightning | thunder | 4 | read | 0/3 | 1/3 |
| Hell's Chicken | chicken | 11 | read | 0/2 | 1/2 |
| S.E.A. | - | 11 | read | 0/0 | 0/0 |
| Miracle in District 20 | miracle | 7 | read | 0/2 | 1/2 |
| Yield My Flesh to Claim Their Bones | yield | 10 | read | 0/5 | 1/5 |
| Timekilling Time | time | 8 | read | 1/2 | 2/2 |
| Murder on the WARP Express | warp | 7 | read | 0/4 | 1/4 |
| The Noon of Violet | violet | 3 | read | 0/3 | 1/3 |
| Full-Stopped by a Bullet | full | 2 | read | 0/3 | 1/3 |
| LCB Regular Check-up | check | 6 | read | 0/3 | 1/3 |
| Nocturnal Sweeping | sweeping | 6 | read | 0/2 | 1/2 |
| Walpurgis Night: Hatred and Despair | hatred | 9 | read | 0/5 | 1/5 |
| Spring Cultivation | spring | 0 | read | 0/2 | 1/2 |
| The Dusk of Amber | dusk | 9 | read | 0/3 | 1/3 |
| Twining Threads | twining | 5 | read | 0/2 | 1/2 |
| Mnestic Experience | mnestic | 0 | read | 0/2 | 1/2 |

the cover's gate (MIN_SCORE, MIN_LEAD), on every card against its truth:

| best correlation at least | lead over the next at least | cards read | read wrong |
|---|---|---|---|
| 0.5 | 0.05 | 516 | 3 |
| 0.5 | 0.1 | 510 | 1 |
| 0.5 | 0.15 | 480 | 0 |
| 0.6 | 0.1 | 510 | 1 |
| 0.7 | 0.1 | 507 | 1 |

cover art alone against the truth: {'agree': 509, 'silent': 21, 'DISAGREE': 1}; keyword alone: {'agree': 526, 'silent': 5}; confirmed by neither: 0 of 531 (0 packs)
