# 2026-10-22 pipeline 的固定等待：改成看畫面（#254）

範圍：`assets/resource/base/pipeline/mirror_dungeon.json` 裡的 `post_delay`。`popups.json`、`navigation.json`、`recovery.json` 的固定等待這次沒動，見最後。

## 資料與方法

- 來源：2026-10-21、10-22 的九份實機 `maafw.log`（HubText 與 `rate_limit` 300 之後的版本）。全部表格用 `uv run python tools/hit_gaps.py <logs>` 算出，完整輸出在 `data/2026-10-22-fixed-waits/hit_gaps.md`。原始 log 與錄影只留在本機。
- **命中** = log 的 `reco hit [result.name=X]`，hub 找到畫面 X。**固定等待** = 一次命中到下一次命中之間的 `TaskBase::sleep` 秒數（節點的 `pre_delay` 加 `post_delay`）。**首次 → 下一個** = 同一畫面第一次命中到另一個畫面第一次命中的秒數，**最後 → 下一個** 同理從最後一次命中算起。
- 「下一個畫面」是 hub 看到的時間：含固定等待、hub 一輪（約 0.15–0.3 s）和辨識，不是遊戲換畫面的時間。遊戲實際何時換畫面，log 看不出來，只有錄影或改成看畫面之後的 `TapUntil` log 看得出來（見「未驗證」）。
- 錄影：`Victory` 的畫面停留取自 2026-10-19 A/B 實機的 60 FPS 錄影（11 場，逐格模板分數對 log）：VICTORY 字樣出現 1.43–1.50 s，出現到 hub 命中 0.00–0.23 s。錄影是較早的版本、不是上面九份 log 的那幾局。

## MaaFramework 預設值（v5.14.3，查證）

出處：上游 tag v5.14.3 的 `docs/en_us/3.1-PipelineProtocol.md` 與 `source/MaaFramework`（`Resource/PipelineTypes.h`、`Task/TaskBase.cpp`、`Task/PipelineTask.cpp`）。fork 的 v5.14.3-maalc.2 只改 OCR 細條重辨識，沒看它的原始碼，這點未驗證。

| 項目 | 值 |
|---|---|
| `pre_delay`、`post_delay` 預設 | 各 200 ms（`PipelineData`）；`default_pipeline.json` 的 `Default` 可覆蓋，repo 沒有這個檔 |
| 順序 | `pre_wait_freezes` → `pre_delay` → action → `post_wait_freezes` → `post_delay` |
| `Node.PipelineNode.Succeeded` | 在 `post_delay` 之後才發 |
| Custom action | 一樣套用兩個 delay |
| `pre_wait_freezes`／`post_wait_freezes` | 預設 0（不等）。物件形式的 `time` 沒寫時為 0，等於不等；畫面本來就靜止也不會立刻返回，至少睡 `time` |
| next 清單 `rate_limit`／`timeout` | 預設 1000 ms／20000 ms（repo 的 MirrorHub 設 300／60000） |

實機 log 也看得到：`Victory` 命中後 `sleep 200ms`、action、`sleep 500ms`；沒寫 delay 的節點兩個都是 200。

為什麼不用 `post_wait_freezes`：它等的是「畫面停止變動」。點下去後遊戲還沒開始換畫面的那一瞬間，畫面也是靜止的，會立刻返回，擋不住 hub 對淡出中的對話框再點一次。repo 已有的 `TapUntil`（#115）是點完逐 0.2 s 看畫面，這次沿用並加一個「等字消失」的條件。

## 量測

下表是九份 log 合計（`fixed` 是每次命中固定睡的秒數，中位數）。

| 畫面 | 命中 | 固定 | 首次 → 下一個（中位數、p90） | 最後 → 下一個 | 下一個畫面 |
|---|---:|---:|---:|---:|---|
| `Victory` | 115 | 0.7 | 0.88、2.00 | 0.86 | Loading 57、Connecting 31 |
| `ProgressPanel` | 1 | 1.7 | 1.81 | 1.81 | MirrorMap |
| `RunVictory` | 10 | 2.2 | 2.44、2.54 | 2.44 | ExplorationComplete |
| `ExplorationComplete` | 10 | 2.2 | 2.45、2.57 | 2.45 | ExplorationReward |
| `ClaimPopup` | 10 | 2.2 | 2.42、2.48 | 2.42 | Loading |
| `ResumeDialog` | 8 | 3.2 | 3.45、3.46 | 3.45 | Loading |
| `RewardCardForgo`、`GiftRefuseDialog`、`DefeatScreen`、`MirrorEntryUnclaimed` | 0 | | | | 九份 log 都沒出現 |

讀法：

- `RunVictory`、`ExplorationComplete`、`ClaimPopup` 的「首次 → 下一個」只比固定的 2.2 s 多 0.22–0.25 s，剛好是 hub 一輪。下一個畫面在睡完之前就已經在了，2.0 s 的 `post_delay` 加 0.2 s 的 `pre_delay` 全是等待。
- `Victory` 命中後 0.86 s 就看到 Loading／Connecting，其中 0.7 s 是固定睡。VICTORY 字樣停留 1.43–1.50 s（較早版本的錄影），比 0.86 s 長，推論 Loading／Connecting 是疊在字樣上出現的；這是推論，兩邊不是同一局。
- **`ProgressPanel` 不是每層都出現**：九份 log 只有 1 次。issue 寫的頻率與實機不符；改法照做，但省的時間可以忽略。
- 同一份 log 裡 `RewardCardForgo`、`GiftRefuseDialog`、`DefeatScreen`、`MirrorEntryUnclaimed` 都沒出現（它們只出現在 10-18、10-19 的離線重播 log）。這四個只能靠單元測試與 pipeline 測試保護，沒有實機次數。

一局完整 NORMAL（10-21 10:08–10:39，30.7 分）的固定等待：`Victory` 14 次 × 0.7 s ≈ 9.8 s；`RunVictory`、`ExplorationComplete`、`ClaimPopup` 各 1 次 × 2.2 s = 6.6 s。

## 改了什麼

| 節點 | 原本 | 現在 |
|---|---|---|
| `Victory` | `post_delay` 500（加預設 `pre_delay` 200） | `pre_delay` 0、`post_delay` 0。VICTORY 不用點，動作只清計數；hub 每 300 ms 看一次，畫面換了就走 |
| `ProgressPanel` | Click ＋ `post_delay` 1500 | `TapUntil`，點 Continue 後等 `^Continue$` 消失 |
| `RewardCardForgo`、`GiftRefuseDialog` | Click ＋ 1500 | `TapUntil`，等各自的標題字消失 |
| `RunVictory`、`DefeatScreen` | Click ＋ 2000 | `TapUntil`，等 `^Victory$`、`^Defeat$` 消失 |
| `ExplorationComplete` | Click ＋ 2000 | `TapUntil`，等 `Complete` 消失，或 Exploration Reward 視窗標題出現（摘要標題可能在視窗底下仍讀得到） |
| `ClaimPopup` | Click ＋ 2000 | `TapUntil`，等**點的當下讀到的那句**消失：`Rewards Acquired` 接 `Pass Level Up` 時，前一句消失就算換了 |
| `ResumeDialog` | Click ＋ 3000 | `TapUntil`，等 `^Resume$` 消失，逾時 4 s |
| `MirrorEntryUnclaimed` | Click ＋ 2000 | `TapUntil`，等 Exploration Reward 視窗標題 |

`TapUntil`（`agent/actions.py`）新增 `gone` 參數：`{"roi", "expected"}`，節點自己的 roi 與 expected；測試（`tests/test_pipeline.py`）要求兩者與節點一致。逾時預設 3 s（原本固定 1.5–2 s；`ResumeDialog` 原本 3 s，現在 4 s）；逾時就交回 hub，跟原本固定等待結束後的行為一樣。`TapUntil` 現在會記一行 log：`<節點>: screen changed after <秒> s`，之後實機驗收直接從 log 讀每個畫面實際花多久。

`pre_delay` 留著（200 ms，點之前讓頁面淡入），理由同 `docs/perf/2026-10-21-opening.md`。

## 預估節省

下面是估計，不是量測；量測要等實機驗收。

- `Victory`：固定的 0.7 s 是上限，每場省 0.3–0.7 s，一局 14 場約 4–10 s。
- 結算三步：#115 的 `TapUntil` 節點點完到下一頁 0.4–1.2 s（`MirrorEnterDialog` 0.39–0.65 s、`LevelWarning` 0.95–1.19 s，見 `data/2026-10-21-opening/after.csv`）。2.2 s 換成這個範圍，每步省約 1.0–1.8 s，一局約 3–5 s。
- `ResumeDialog` 只在重啟或接續舊局時出現（九份裡 8 次），每次約省 2–2.5 s。
- 合計一局約 7–15 s，約 0.4–0.8%。

## 沒寫 delay 的節點：預設 200＋200 ms

沒寫 `pre_delay`、`post_delay` 的節點，每次命中固定睡 0.4 s（見上面的預設值）。同一局（10-21 10:08–10:39）：

| 節點 | 命中 | 固定 | 合計 s |
|---|---:|---:|---:|
| `Event` | 109 | 0.4 | 43.6 |
| `BattleTurn` | 33 | 0.4 | 13.2 |
| `MirrorMap` | 30 | 0.4 | 12.0 |
| `Formation` | 15 | 0.4 | 6.0 |
| `GiftGet` | 21 | 0.4 | 8.4 |
| `RewardCard` | 8 | 0.4 | 3.2 |
| `GiftChoice` | 6 | 0.4 | 2.4 |
| `Shop` | 5 | 0.4 | 2.0 |
| 合計 | | | 90.8（占 30.7 分的 4.9%） |

這是上限，不是可省的量：多數節點的動作本身就要等畫面（`PlayTurn`、`Shop`），`pre_delay` 也讓頁面淡入。`Event` 最大（每次點擊一步），但那個動作自己每 0.15 s 點一次，額外的 0.4 s 很可能只是拖慢；`GiftChoice` 只有 6 次。這次沒改，建議另開 issue 逐個節點試 `pre_delay`／`post_delay` 設 0 並實機驗收。

## 沒動、沒驗證

- `popups.json`（`Connecting` 等 1000–2000 ms）、`navigation.json`（2000–3000 ms）、`recovery.json`（2000–10000 ms）還有固定等待。`Connecting` 一局 12 次 × 1.2 s ≈ 14 s，是下一個值得看的。
- `Settle`、`Wipe` 等動作裡有 `tap(..., wait=1.5)`、`time.sleep(1)`，不是 pipeline 的 `post_delay`，也沒動。
- 實機：本次沒跑模擬器。`gone` 在淡出畫面上的實際行為（字消失的時間點、OCR 讀不到的半透明字）還沒有實機證據；驗收看 `TapUntil` 的 `screen changed after` log，並確認沒有重複點同一個按鈕。
