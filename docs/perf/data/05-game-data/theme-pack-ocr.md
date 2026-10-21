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
| `World Lake`, `Abyss Crawling`, `WONr Abyss Crawling` | 3 | two-line title read in reverse order (likely the tilted card; unverified) | no | `lake`, `abyss` |
| `HellOBus`, `HellBus`, `aHelIOBis` | 7 | stylized title art; a floor 2 card, likely Hell's Chicken (unverified) | no | no |
| `Mirac inDistrict niiaco m uistir` | 1 | stylized title art | no | no |
| `WalpurgisN The Noon of` | 1 | stylized title art, last word lost | no | no |
| `Emotio` | 1 | title cut | no | no |
| `Time` beside `Timekilling Time` | 2 | one title split into two cards | no | would read it as Timekilling Time |
| `Line` | 2 | Line 1–5 alike | shares their weight | — |
