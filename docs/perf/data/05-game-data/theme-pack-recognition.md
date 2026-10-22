# Theme pack recognition, offline (#274, 2026-10-23)

The numbers in [05-game-data.md](../../../spec/05-game-data.md) section 2 ("every pack recognised") come from here. Run:

```
uv run python tools/pack_stats.py tests/screens/ThemePack*.png <captures> --glob "*raw*.png" --base <captures' parent> --csv theme-pack-recognition-cards.csv
```

on 112 distinct theme pack pages: the six `tests/screens/ThemePack*.png` and the card pages of the six live runs of 2026-10-22
(each `floor N packs` reading's screenshot, pages with the same pixels counted once). The captures other than `tests/screens/`
stayed on the developer's machine; every card of them is listed in
[theme-pack-recognition-cards.csv](theme-pack-recognition-cards.csv) with its OCR lines, its pack and the path that read it.
The OCR runs in a MaaFramework task on the still image (`actions.ocr` on `PACK_TITLES`), the cover art on the same image.

## Truth, and what it does not show

- A card's truth is the pack the full reading (`+cover`) names. Where the cover art reads (467 of 531 cards) it agrees with that
  pack on every one (0 disagree); the other 64 are cards the cover stays silent on (a boss silhouette or a look-alike cover, see
  below), whose pack is the title OCR read. No card was checked by eye one by one: unverified where the cover is silent.
- The captures show **74 of the 94 packs** of the season; the 20 never dealt in them (The B.E., The Evil Defining, The
  Heartbreaking, La Manchaland Re-opening, Textbook, Storefront Campout, An Anarchy of Colors, Creed of Preservation, Readvent of
  Gluttony, Line 4 - Section #4, Crushers & Breakers, Unbound Wrath, Inert Sloth, Excessive Gluttony, Sunk Gloom, Pitiful Envy,
  Burning Haze, Dizzying Waves, Spring Cultivation, Mnestic Experience) are only covered by the per-pack table below: a pack's own
  name, its own cover pasted on a page and single words of its name, not a capture. "Every pack recognised" on a live page is not
  shown for them.
- The cover's threshold (`pack_cover.MIN_SCORE`, `MIN_LEAD`) was picked on these captures (precision first: 0 wrong of 485 cards
  at 0.5 / 0.1, 425 read; 4 wrong at a lead of 0.05), not on held-out pages.
- A card that has no OCR box at all is lost: none of the 112 pages shows one.

## Readings

`main` main's `pack_titles` (boxes with a lowercase letter, columns within 80 px); `#270` PR #270's `pack_cards` (the same filter,
boxes within 15 px one card, a capitals-only card kept from 80 px wide); `list` `pack_cards` now: only a box reading exactly a word
of `NOT_TITLE` (`LIMBUS`, `COMPANY`, `LIMBUS COMPANY`, `CAUTION`, `CLEAR BONUS`, `LV`) or nothing is dropped, name and title art
match; `+key` adds the keyword path, `+cover` the cover path (what `PickThemePack` runs); `#270+all` the #270 cards with both new
paths. "listed, no pack": the card is in the ranking but no pack names it (it takes the plan's unlisted weight, or the weight its
alike titles share); "not listed": no card of the reading stands within `CARD_SPAN` of it, so the bot cannot pull it; "extra
cards": cards of the reading with no card of the truth.

## The two filters

The 112 pages hold 1191 OCR boxes; 453 have no lowercase letter, which the #270 filter dropped unless the card's capitals stood 80 px
wide. The new filter drops 94: `LIMBUS` 83 times (the logo, also read `LImBUS`), `LV` twice (the level badge), 9 reads of nothing.
`COMPANY`, `LIMBUS COMPANY`, `CAUTION` and `CLEAR BONUS` appear 0 times (listed from the card's look: they sit behind and below the title
strip); the logo's second word reads as noise (185 distinct texts among the no-lowercase boxes, most of them such misreads: `WOPIS`,
`CIMPINS`), which the old filter dropped and now stays a line of its card, read past by the name match. The capitals the old filter threw away that are
part of a title: `MADNESS` (Line 1), `THE DUSK OF AMBER`, `DUSK OF AMBER`, `OF AMBER`, `AMBER`, `MURDER`, `ON THE`, `WARP EXPRESS`, `LINE 2`,
`TIMKILLING`, `VIOLET`, `HATRED`, `S.E.A`, `ROLIND` (Merry-Go-Round, Line 5) and the Chinese art title of Nocturnal Sweeping. A lone noise box (`M`, the badge's `IV`, `2`) is a card of its own without the lowercase rule: 3 pages show it, so
texts nearer than `CARD_SPAN` (105 px) by centre are one card.

## Results

112 pages, 531 cards, 74 of 94 packs seen

| reading | right | wrong | listed, no pack | not listed | extra cards | right of all |
|---|---|---|---|---|---|---|
| main | 523 | 0 | 5 | 3 | 3 | 98.5 % |
| #270 | 526 | 0 | 5 | 0 | 0 | 99.1 % |
| list | 527 | 0 | 4 | 0 | 0 | 99.2 % |
| +key | 530 | 0 | 1 | 0 | 0 | 99.8 % |
| +cover | 531 | 0 | 0 | 0 | 0 | 100.0 % |
| #270+all | 531 | 0 | 0 | 0 | 0 | 100.0 % |

| reading | name | title_art | keyword | cover |
|---|---|---|---|---|
| main | 509 | 14 | 0 | 0 |
| #270 | 509 | 17 | 0 | 0 |
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

cover art against the truth: {'agree': 467, 'silent': 64}
