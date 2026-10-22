# Live-test scripts: inventory and the tools that replace them

Every live test used to write its own scripts under `.local/scratch/<task>/` and `.local/probe/`, the same job many times over. This page sorts those scripts by what they do, says which category became a tool in `tools/live/`, and which old scripts that tool replaces. The old scripts stay where they are.

## Scope

Taken on 2026-10-22: every `.py`, `.sh` and `.ps1` under `.local/`, leaving out source trees that are not one-off scripts: the fork source `probe/fork157`, `probe/src-maafw`, `probe/.venv`, `scratch/review213` (two checkouts of the repo, `head/` and `old/`), every `site-packages`, `node_modules`, `__pycache__` and `.git`. That leaves 1664 files. 435 more are copies of the repo's own trees (an `install/`, `install-bak*/`, `agent/`, `tests/` or `assets/` folder a task copied, a review checkout's `copy/`, `base/`, `after/`), which leaves **1229 scripts**. The counts below add up to it; a script sits in one category. Each was sorted by its first lines, and by the file itself when they did not settle it; the per-file table stays local, in `.local/scratch/live-tools-1afd/cls.tsv`.

## Categories

| Category | Scripts | Most complete | Taken | Replaced by |
| --- | ---: | --- | --- | --- |
| Log to evidence-annotate events: taps, drags, `[maalc]` captions | 23 | `scratch/combined-verify/mkclip.py` (`tap_events`), `scratch/top-live-video4/mkevents.py` | yes | `evidence.py events`, `evidence.py steps`; maafw.log stays with `maafw_events.py` |
| Cut a clip | 13 | `scratch/combined-verify/mkclip.py`, `packclip.py` | yes | `evidence.py clip`, `map --clip`, `packs --clip` |
| Frames at wall times | 19 | `scratch/top-live-video4/grabframes.py`, `scratch/combined-verify/common.py` (`frames`) | yes | `evidence.py frames` |
| Recording against the log | 29 | `scratch/combined-verify/common.py` (`locate`), `scratch/video-align/fit_block*.py` | yes | `--video PATH@START` of `evidence.py`; the offset fits are `tools/video_align.py` already |
| Map: stitched floor, every node marked | 24 | `scratch/combined-verify/route.py` | yes | `evidence.py map` |
| Pack page: names, weights, pick, settle time | 41 | `scratch/combined-verify/packs.py` | yes | `evidence.py packs` |
| Identity masks | 8 | `scratch/top-live-video4/mask85.py`, `scratch/retry-capture/mask_still.py` | yes | `evidence.py mask` (the templates of `.local/evidence/masks.json`, not fixed boxes) |
| Start the bot, run the tasker | 94 | `scratch/combined-verify/tasker.py`, `tsrun.py`, `start_game.py` | yes | `bot.py run`; `device.py start` |
| adb screenshot, tap, freeze the bot | 109 | `scratch/combined-verify/shot.py`, `tap.py`, `freezer.py` | yes | `device.py shot`, `tap`, `key`, `freeze` |
| Log statistics | 102 | `scratch/top-live-video4/loadspans.py`, `scratch/170-parchment/maafw_timeline.py`, `scratch/*/gaps.py` | already tools | `tools/wait_spans.py`, `tools/maafw_timeline.py`; `gaps.py` (4) is not taken: PR #256 adds `tools/hit_gaps.py` for it |
| Test install settings, keeping the screen on | 34 | `scratch/zoom194/prep.py`, `scratch/top-live-video2/keepawake.ps1` | yes | `bot.py prep`, `bot.py awake` |
| Recording by adb screenrecord, scrcpy or OBS | 26 | `scratch/shop-speed/adbrec.py`, `probe/obs/obsrec.py` | no | the `screen-record` skill only (MuMu window capture); the other ways were never agreed to |
| One-shot batch edits (`edit_*.py`, `fix*.py`, `resolve*.py`) | 251 | none: each edits one task's files once | no | |
| Other | 456 | none: many kinds, below | no | |

The settings and keep-awake scripts (34) were sorted out of the other rows by file name: 32 from Other, 1 each from the events and the start-the-bot rows.

What a category leaves out:

- **Map** (23 not taken): recognition experiments on map frames (`probe/archive/2026-10-18-shop-node-146/scripts/exp*.py`, `probe/p116/`, `probe/issue111/`) and hand-placed annotations (`scratch/top-live-video4/route_annot*.py`, `probe/live-all/annotate_map.py`), which `map` makes from the log.
- **Packs** (40 not taken): pack-title OCR and cover-matching experiments (`scratch/pack-ocr/`, `scratch/theme-covers/`, `scratch/aalc-240/pack_ocr.py`).
- **Start the bot** (59 copies of `tasker.py` and `tsrun.py`; the rest): scripts run inside a custom action (`probe/g54/probe.py`, `probe/g56/probe.py`) and one-segment drivers (`probe/s26/play26.py`, `scratch/popups85/popup_check.py`) stay with their experiments.
- **adb** (28 copies of `shot.py` and `tap.py`): the rest drive one experiment (`scratch/accept162/switcher.py`, `probe/exp/gtrial.py`, `probe/g56/measure*.py`).
- **Log statistics**: the per-arm summaries of A/B runs (`scratch/*/analyze.py`, `shop_breakdown*.py`) answer one experiment's question each.
- **Other**, by count: recognition tests 57, game-data unpacking 51, unit experiments 36, image comparisons 33, template crops 30, benchmarks 19, contact sheets 17, copies and snapshots of repo source 27, OCR probes 16, memory probes 12, and 66 kinds under 10 each (GUI tests, hook tests, window control, chart and report builders).

## Replaced

The old scripts stay in `.local/`, unchanged. These are replaced, every copy under any task folder:

- `tasker.py`, `tsrun.py`, `run.py` (headless MirrorDungeon) → `bot.py run`
- `prep.py`, `prep_config.py`, `prep_settings.py` → `bot.py prep`
- `keepawake.ps1`, `awake.ps1`, `wake.ps1` → `bot.py awake`
- `shot.py`, `tap.py`, `start_game.py`, `freezer.py` → `device.py`
- `scratch/combined-verify/`: `common.py`, `route.py`, `packs.py`, `mkclip.py`, `packclip.py` → `evidence.py`
- `scratch/top-live-video4/`: `mkevents.py`, `grabframes.py` → `evidence.py events`, `frames`; `loadspans.py` → `tools/wait_spans.py`; `mask85.py`, `mask197.py` → `evidence.py mask`
- `scratch/*/maafw_timeline.py` → `tools/maafw_timeline.py`

Not replaced: `scratch/combined-verify/mkclip248.py` (a clip joined from two pieces with time-ranged masks of the Play Store's avatar) and `adbrec.py`/`adbrec.sh` (adb screenrecord).

## Design

Three tools under `tools/live/`, one per thing they act on, each with subcommands; `--help` lists them, the `maalc-live-test` skill says when each runs.

- `evidence.py`, the evidence files: `events`, `steps`, `frames`, `clip`, `mask`, `map`, `packs`. Input is the bot's stamped `run.log` and the recording as `--video PATH@START`, START the wall time of its first frame (screen-record's `started`), once per piece, so no clock offset is needed. `map` and `packs` port `route.py` and `packs.py`; their image analysis runs on frames ffmpeg decodes into numpy arrays, so the tests drive it with synthetic frames. Every still and clip is masked with `.local/evidence/masks.json`; only template matching needs OpenCV (the probe group), as evidence-annotate's `annotate.py` does it the same way.
- `device.py`, the emulator through MaaFramework's adb controller: `shot`, `tap`, `key`, `start`, `freeze`. A single screenshot is its only capture; recording stays with screen-record.
- `bot.py`, the bot process: `run` (the old `tasker.py` and `tsrun.py` in one), `prep`, `awake`.

Paths come in as arguments; `.local/` is found through `tools/local_dir.py`. What the repo already had is extended, not redone: `evidence.py events` hands a maafw.log to `maafw_events.py`, and the queue, `backup.py`, `dialogs.py`, `tools/video_align.py`, `tools/wait_spans.py` and `tools/maafw_timeline.py` keep their jobs.
