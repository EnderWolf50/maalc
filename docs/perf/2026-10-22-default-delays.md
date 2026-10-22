# 預設 pre_delay／post_delay 與 MirrorEntryPaused 的 timeout（#258、#269）

接在 `docs/perf/2026-10-22-fixed-waits.md`（#254、PR #256）之後：那份處理有寫 `post_delay` 的節點，這份處理沒寫的（MaaFramework 預設各 200 ms）。

## 資料與方法

- 來源：2026-10-22 第 1 輪測試局六局的 `maafw.log`（八個檔，局的邊界會切檔），一份 `run*.log` 的 `<節點>: screen changed after <秒> s` 行，一段錄影（逐格看按 Enter 之後的畫面）。原始 log 與錄影只留在本機。
- `uv run python tools/action_gaps.py <logs> --nodes ...`（新）算出下表，輸出在 `data/2026-10-22-default-delays/action_gaps.md`。**pre**、**post** 是命中前後 MaaFramework 的 sleep，**action** 是 `CustomAction::run` 進出，**to next** 是動作結束到下一個畫面命中的秒數，**short** 是少於 1 s 的動作數（動作馬上交回 hub）。

| 節點 | 命中 | pre | action | post | to next | short | 下一個畫面 |
|---|---:|---:|---:|---:|---:|---:|---|
| `Event` | 346 | 0.20 | 1.16 | 0.20 | 0.38 | 112 | Event 260、MirrorMap 55、Connecting 27 |
| `BattleTurn` | 232 | 0.20 | 7.41 | 0.20 | 0.26 | 0 | BattlePause 223、Connecting 5、BattleTurn 3 |
| `MirrorMap` | 205 | 0.20 | 2.91 | 0.20 | 0.41 | 3 | Formation 89、Event 59、Shop 29 |

## #269：MirrorEntryPaused 的 timeout

- 量測（verified，六局的 `screen changed after` 行）：3.9、3.8、3.8、3.7、3.6、3.9 s。這一步已經是「等畫面變化」：`TapUntil` 點 Enter 後每 0.2 s 看選隊頁（`TEAMS`）或 Resume 對話框，哪個先出現就結束；只有 timeout 太近。所以不需要 #256 的 `gone` 參數；這個 PR 疊在 #256 上只因為 `tools/action_gaps.py` 用它的 `tools/hit_gaps.py`，加上 `tests/test_pipeline.py` 裡它的測試要跟著改。
- 這 3.6–3.9 s 是遊戲的鎖鏈動畫加黑畫面，bot 無法縮短。錄影逐格（verified）：按 Enter 後約 3 s，入口頁、`F1` 字樣和 Enter 鈕一直在畫面上（鎖鏈與 `Exploring!` 蓋在中間），再黑約 1 s，才是選隊頁。
- 逾時後的行為（推論，未實機驗證）：`TapUntil` 逾時就回傳成功，hub 下一輪還讀得到 `F\d`，會再命中 `MirrorEntryPaused`，再點一次 Enter。這次 Enter 落在鎖鏈動畫上，或黑畫面之後的選隊頁右側（`1030,470` 一帶），後者會點到什麼沒有證據。第 1 輪六局每次進入都只命中一次 `MirrorEntryPaused`（六局都在 timeout 內），所以沒有逾時重點的實機實例；Enter 被點兩次「不會出錯」**沒有證據**。
- 改法：`timeout` 4 → 8 s（最慢一局 3.9 s 的兩倍以上）。等待在頁面出現的當下就結束，所以拉長不花時間，只讓真的卡住時晚 4 s 才交回 hub。測試 `test_mirror_entry_paused_outwaits_the_chains` 要求 `timeout >= 2 × 3.9`。
- 沒有做：不另外防重複點。8 s 之內遊戲到不了選隊頁，代表它不在預期的流程裡（斷線、更新對話框），hub 反而需要再看一次。

## #258：逐個節點

每個決定都看「動作前面有沒有自己的把關」，以及「動作回來之後，hub 太早再看一次會發生什麼」。

### `MirrorMap`：`pre_delay` 0、`post_delay` 0（改）

- 動作 `RouteMap` 第一件事是 `still()`：畫面還在淡入淡出就交回 hub，不點任何東西。所以 `pre_delay` 不是防誤點，只是讓 `still()` 少失敗。有 200 ms 的 `pre_delay` 時，205 次命中只有 3 次動作少於 1 s：2 次是 GET! 視窗蓋在地圖上（`GiftGet` 接著命中），1 次是地圖還沒靜止。沒有 `pre_delay` 時失敗會多一些，每一次的代價是 hub 再看一輪（約 0.3–0.5 s），比省下的 0.2 s 大不了多少；失敗率要高過約 40% 才會打平，而現在是 1.5%。
- `post_delay`：`enter_node` 點完 Enter 後等節點面板消失，再等地圖淡出（最多 3 s）才回來，所以下一個命中不會是還在淡出的地圖。
- 預估節省（估計，未實機量）：每局約 34 次（205 ÷ 6）× 0.4 s ≈ 14 s，一局 30 分鐘的 0.7%。

### `BattleTurn`：兩個都留 200 ms（不改，明確寫出）

- `PlayTurn` 一開頭也有 `still()`，所以 `pre_delay` 看起來同樣可以拿掉；`post_delay` 不行：log 裡 232 次命中有 **223 次** 的下一個畫面是 `BattlePause`（動作結束後 0.26 s），只有 3 次是 `BattleTurn`。`hold_turn` 在回合最初的幾格就因為 Win Rate 標籤還讀得到而回來（`hold_turn` 的註解也這麼說）；這是推論，log 只顯示結果的 223 比 3，回合開始後 `BattlePause` 才出現。0.2 s 的 `post_delay` 剛好讓 hub 的下一次看到的是 `BattlePause`；早 0.2 s 看就可能再次命中 `BattleTurn`，`PlayTurn` 把同一回合算成第二次送出（`same_turn`），又點一次 Win Rate（推論：Win Rate 是開關，第二下會把剛選好的技能清掉）。
- `pre_delay` 單獨拿掉大概也安全（`still()` 擋住），省約 8 s 一局，但它同樣把動作往回合最初的移動畫面推 0.2 s，我沒有證據量它；這個機制要實機才看得到，所以兩個一起留。寫出 200 讓之後的人看得出是決定，不是漏寫。

### `Event`：兩個都留 200 ms（不改，明確寫出）

- `Event` 一次命中就是一步（346 次命中，260 次下一個還是 `Event`，112 次動作少於 1 s）；兩個 delay 占兩次動作之間 0.6 s 中的 0.4 s，是三個節點裡最大的一塊（#254 估一局 109 次 × 0.4 = 43.6 s）。
- 但動作沒有 `still()`：一開頭就 `screen()` 讀紅按鈕與文字，所以 `pre_delay` 讓頁面淡入（半透明的 Choices 頁讀錯選項，或把半透明的按鈕當成亮著）。`post_delay` 的角色在選項分支：點了選項之後 `until` 只等到「面板跟點之前不一樣」就回來，頁面還在淡出；0 的話 hub 下一輪讀到仍在淡出的 Choices 頁，會再點一次同一位置。紅按鈕分支已經等淡出（`advance(pressed_at)`），不受影響。
- 沒有實機證據能證明這些風險在實際遊戲裡會發生，也沒有證據說它們不會；依「只改證據充分的節點」的要求先不動。**下一步**（建議另開 issue）：讓 Choices 分支在點完之後等頁面真的換掉（標題 `Choices` 消失）、`Event` 一開頭加 `still()`，再把兩個 delay 設 0；那是改動作，不是改 pipeline 數字。

## 沒評估的節點

`Formation`（#255 在改）、`ProgressPanel`、`BattleMenu`（#261）、商店（#260、#265）依指示不動。`RewardCard`（45 次，to next 0.46）、`GiftChoice`（33 次）、`MapNodePanel` 次數少、動作內容沒讀，沒有評估；`Shop` 的動作 39 s，兩個 delay 占不到 1%。

## 實機驗收（未做：這次不用模擬器）

- 跑一局 NORMAL（#269 還要一次暫停的局：To Window 後 Resume）。
- `uv run python tools/action_gaps.py <maafw logs> --nodes MirrorMap` 的 pre、post 應為 0.00；`MirrorMap` 的 short（少於 1 s 的動作）與 `to next` 跟上表比：short 不該明顯增加，`to next` 約少 0.4 s。
- `MirrorMap` 命中之後沒有同一張圖的重複 `map: take ...`、沒有 `no node took a tap`。
- `MirrorEntryPaused: screen changed after <秒> s` 在 3.6–3.9 s，沒有 `no change`；`no change` 出現的話，看它之後 hub 是否又命中 `MirrorEntryPaused`（重複點 Enter）。
