# 2026-10-17 驗收局時間分析（#34）

唯讀分析，沒有動模擬器也沒有改程式。目標：看一局約 105 分鐘的牆鐘時間花在哪、自家動作裡有多少是固定等待、能省多少。

## 資料與方法

- 對象：2026-10-17 本地 14:05–19:32 的 3 局連續 bot 全程通關（`install/logs/runs.jsonl` 是 UTC，本地 = +8）。A = 14:05:23–15:50:30，B = 15:50:54–17:50:49，C = 17:51:11–19:32:39。
- 來源：`install/debug/debug/maafw.bak.2026.10.17-15.58.02.915.log`、`...-17.57.54.998.log`、`maafw.log`（依大小輪替，三個檔接起來剛好覆蓋 14:05–19:32，共約 8 億位元組）。agent 的 stdout（`run6.log`）沒有時間戳，只用來對照 shop 的行為。
- 做法：逐行解析 maafw.log 的毫秒時間戳。
  - 每個 pipeline step = 相鄰兩個 `Node.PipelineNode.Succeeded` 的間隔，歸給比對到的節點（這個事件在 action 與 post_delay 之後才發出，所以間隔含「等它出現 + 動作 + 延遲」）。
  - 自訂動作的耗時取 `CustomAction::run` 的 enter/leave；動作內部拆成 agent 呼叫（`handle_context_run_recognition` = OCR / 模板比對、`handle_controller_wait` = 截圖與點擊完成、`post_click` 等）與呼叫之間的空檔。
  - 「固定等待」= 動作內相鄰兩次 agent 呼叫之間超過 0.2 秒的空檔（`tap(..., wait=)`、`time.sleep`）。殘差（Python 運算等）每局只有 10–15 秒，可忽略。
- 注意：
  - B 含一次 L3 重開遊戲（17:12，`stuck: battle over 20 min`，約 2.5 分鐘恢復加約 1 分鐘 Connecting／Loading），所以 B 不算乾淨。
  - C 的第 5 次商店（447 秒，8 次開融合頁）是離群值。
  - 以下「可省」都是估計，需要實機驗證；標「未驗證」的是推論。
- 分析腳本留在 主 checkout 的 `.local/probe/prof/`（`parse2.py`、`an4.py` 等），位於 gitignored 私有資料夾。

## 1. 各階段時間（每局，分鐘）

| 階段 | A | B | C | 平均 | 說明 |
|---|---:|---:|---:|---:|---|
| 戰鬥演出（`BattlePause` steps） | 63.4 | 68.4 | 53.9 | **61.9** | 遊戲在播回合，每回合約 42 秒（前兩層約 30 秒，第 4–5 層約 60 秒）；含每回合約 1 秒的偵測延遲 |
| 商店（5 次造訪） | 13.8 | 14.1 | 19.1 | **15.6** | 每次 2.5–3 分鐘，C 有一次 7.5 分鐘；90% 是固定等待 |
| 戰鬥：`BattleTurn` step | 11.0 | 12.6 | 10.0 | **11.2** | `PlayTurn` 6.5 分鐘（每回合 4.3 秒）+ 回合結束到出現 BattleTurn 的轉場與輪詢 4.7 分鐘（每回合 3.1 秒） |
| 事件 | 3.7 | 4.8 | 5.2 | **4.6** | 約 98 次 Event step，每次 2.7 秒（動作 1.7 秒 + hub 1.1 秒） |
| 地圖導航（`RouteMap`） | 4.3 | 4.9 | 4.5 | **4.6** | 約 30 次，每次約 8.7 秒 |
| 戰鬥其他（Formation、Victory、Wipe） | 3.1 | 4.3 | 3.1 | **3.5** | Formation 約 1.6 分鐘，Victory step 5.3 秒 x 15 |
| 讀取畫面（Loading） | 2.2 | 4.7 | 2.5 | **3.2** | 約 137 個 step，每個 1.4 秒；遊戲本身的時間 |
| 獎勵／飾品挑選（GiftGet、GiftChoice、RewardCard） | 2.2 | 2.6 | 1.6 | **2.1** | GiftGet 約 26 次 x 2.2 秒 |
| 起手（隊伍／星光／起始飾品／觀測，到第 1 層主題包前） | 0.8 | 1.0 | 0.8 | **0.9** | 約 48 秒，其中 GiftSearch 8 秒、起始飾品 6 秒、選隊 4 秒 |
| Connecting／重試彈窗 | 0.0 | 1.1 | 0.2 | 0.4 | B 的重開遊戲 |
| 層起點（主題包） | 0.3 | 0.4 | 0.3 | 0.4 | |
| 恢復／導航 | 0.0 | 0.7 | 0.0 | 0.2 | 僅 B |
| 結算（`Settle`） | 0.1 | 0.1 | 0.1 | 0.1 | 另有局間約 24 秒（Claim 後 Loading、導航回入口），不在 runs.jsonl 的時長內 |
| **合計** | 105.1 | 119.9 | 101.5 | **108.8** | |

重點：戰鬥演出佔 57%，是遊戲的時間，bot 不能縮短（遊戲內是否有戰鬥加速選項：未驗證；戰鬥畫面只看到暫停與設定兩個鈕，見 `tests/screens/BattlePause.png`，建議在設定頁查一次）。每局 15–16 場戰鬥、80–100 回合。

### 時間預算（每局平均）

| 類別 | 約分鐘 | 比例 |
|---|---:|---:|
| 遊戲演出與讀取（BattlePause、Loading、Connecting、回合結束轉場約 2 秒 x 90） | 約 70 | 65% |
| 自家動作內的固定等待（見第 2 節） | 27.7 | 26% |
| pipeline 層的輪詢、pre/post_delay、rate_limit（扣掉遊戲轉場後） | 約 6 | 5% |
| OCR／模板比對（agent 呼叫）174 秒 + 截圖與點擊完成 79 秒 | 4.2 | 4% |

截圖約 10 毫秒（`post_screencap` 0 毫秒 + `wait` 9–11 毫秒），OCR 單次約 35–90 毫秒，都不是瓶頸；瓶頸是固定等待。

## 2. 自家動作內的時間

每局平均，自訂動作合計 1950 秒（32 分鐘），其中固定等待約 1660 秒（`tap(wait=)` 1492 + `time.sleep` 168）、OCR 174 秒、控制器 79 秒。

| 自訂動作 | 總時間 | 其中固定等待 | OCR／比對 | 次數／局 |
|---|---:|---:|---:|---:|
| Shop | 930 | 818 | 68 | 5 次造訪 |
| PlayTurn | 392 | 357 | 5 | 90 回合 |
| RouteMap | 250 | 165 | 67 | 31 |
| Event | 167 | 148 | 12 | 98 |
| Formation | 96 | 78 | 13 | 18 |
| PickGift / RewardCard / PickThemePack | 36 / 24 / 16 | 31 / 21 / 10 | | 8 / 8 / 5 |
| 起手動作（GiftSearch、PickStartingGift、SelectTeam、星光） | 約 27 | 約 24 | | 1 |

### 商店內部（15 次造訪合計，換算每局）

| 位置（`agent/actions.py`） | 每局固定等待 | 說明 |
|---|---:|---|
| `Shop.fuse` 逐格掃：點格子 `wait=1.2`（約 587 次 / 3 局） | 235 秒 | 每次融合頁把 15 格全點開、OCR 提示框 |
| `Shop.fuse` 關提示框 `tap(*FUSE_NEUTRAL)`（沒給 wait，預設 1.0；628 次 / 3 局） | 210 秒 | 只是關提示框，卻等 1 秒 |
| `Shop.buy_one` 點商品 `wait=1.5`（191 次 / 3 局） | 96 秒 | 每個商品都開購買視窗讀體系 |
| `PURCHASE_CANCEL`（預設 1.0）、`OUTSIDE`（1.0） | 40 + 15 秒 | |
| 融合頁開關與確認（`fuse_open`、`fuse_keyword_*`、`PAGE_OK`、`PAGE_CLOSE`、confirm） | 約 130 秒 | |
| 刷新、GET 確認、離開 | 約 60 秒 | |

每次造訪平均開 2.6 次融合頁（每局約 13 次），其中約 7 次什麼都沒融（`N non-main gifts on show, a fusion takes 3` 或 `not confirmed`：A 9 次、B 6 次、C 7 次）；沒買也沒融時持有飾品沒變，下一次掃一定同樣結果（#62 第 1 點已指出）。另有 `opened no purchase dialog` 每局 9／15／21 次，每次約 3.5 秒（點 1.5 秒 + `to_main` 迴圈）。

### 戰鬥內部

- `PlayTurn` 每回合 4.3 秒，其中：`time.sleep(1)`（開頭，每局 89 秒）、Win Rate 點擊 `wait=1.5`（每局約 84 次，126 秒）、START 後 0.5 秒輪詢（每局約 109 秒，這段本來就要等遊戲約 1.5 秒起演出，只是粒度粗）、護衛回合的 0.4／0.8／1 秒（每局約 20 秒）。
- 回合結束到 `BattleTurn` 被偵測：每回合 3.1 秒。實例（17:xx 的取樣）：BattlePause 消失後有 3 次失敗的 hub 輪詢（間隔約 1.0 秒 = `rate_limit` 預設 1000 毫秒）才比到 BattleTurn。其中約 2 秒是遊戲自己在轉場，我方可以省的約 1 秒（`rate_limit` 平均落後 0.5 + pre_delay 0.2 + 輪詢本身 0.2–0.5）。
- `Formation`：`TO_BATTLE` 後 `wait=3`（每局 53 秒）、重選時每張卡 `wait=1.2`（每局約 21 秒）。

## 3. Pipeline 層的開銷

每局約 2800 次 MirrorHub 輪詢，2550 個 step（其中 2080 個是 `BattlePause`），約 260 次失敗輪詢。

- **`rate_limit` 沒設，吃預設 1000 毫秒**：失敗輪詢之間的間隔實測 1.02–1.08 秒，而輪詢本身工作只有 0.12–0.25 秒。每次畫面轉場（約 390 個非 BattlePause step + 90 個回合）平均落後約 0.5 秒才被看到。
- **輪詢本身平均 515 毫秒**：`Stuck`（自訂辨識，agent 往返 + 截圖約 90 毫秒）+ 約 4 批 x 35 毫秒的 OCR（33 個 OCR 節點，批次預取），最後才輪到模板比對的 `BattleTurn`／`BattlePause`（各 2–4 毫秒）。戰鬥中 90% 的 step 都是這兩個，卻排在 38 個項目的最後面。把它們移到 `Stuck` 之後是否能略過 OCR 批次：未驗證（要看 MaaFramework 的 batch OCR 預取是在比對前整批做、還是惰性做）。
- **預設 pre_delay／post_delay 各 200 毫秒**：每個 step 都有一個 200 毫秒的 sleep（每局 2800 次、約 560 秒）。`BattlePause` 佔 2080 次，但那只影響偵測延遲，不累加成損失；非 BattlePause 的 step 約 390 個，約 80–150 秒。
- **明確寫了 post_delay 的節點**（`mirror_dungeon.json`、`navigation.json`、`popups.json`）：1000 毫秒 x 約 2260 次（幾乎全是 `BattlePause` 與 `Loading`）、1500 毫秒 x 約 26 次（`GiftGet`、`RewardCardForgo` 等）、2000 毫秒 x 約 21 次（`Victory`、`ClaimPopup`、`MirrorEnterDialog` 等）、3000 毫秒 x 5（`NavTitle`、`ResumeDialog`）。非戰鬥的明確延遲每局約 90 秒。
- **Loading／Connecting**：`Loading` 節點 `post_delay: 1000`，每個畫面結束平均多等約 0.7 秒，約 27 段 x 0.7 = 20 秒。
- **重複失敗的辨識**：沒有發現單一節點重複失敗到 step 層級（`NextList.Failed` 每局約 240–290 次，全是等轉場）。`RouteMap` 的地圖拖曳：每次呼叫都要把 Bus 從休息位 (446,248) 拉到 `BUS_HOME` (446,320)（差 72 像素），平均 1.3 次拖曳 / 呼叫（72 次呼叫 1 次、9 次 2 次、11 次 3 次），每次拖曳含 `hold=0.5` + `sleep(0.5)`。若 BUS_HOME 設成休息位附近，多數呼叫可免拖曳（未驗證，與 #61 的「地圖被拖離」不同，這是正常流程每次都拖）。
- **看門狗**：`Watchdog.see` 以「step」計數（`SAME_SCREEN = 5`），不是輪詢，所以降低 `rate_limit` 不會讓卡住判定變快；但縮短動作內的固定等待會讓連續 5 個相同 step 的牆鐘時間變短，需複核 Event、商店這類會重複同畫面的流程。

## 4. 熱點（每局，約略）

| # | 位置 | 現在 | 估計需要 | 可省 | 備註 |
|---:|---|---:|---:|---:|---|
| 1 | `Shop.fuse` 逐格掃（`wait=1.2` + `FUSE_NEUTRAL` 預設 1.0） | 445 秒 | 約 60 秒 | **350–420 秒** | 每局約 13 次、7 次白掃；C 的一次造訪 447 秒 |
| 2 | `Shop.buy_one`／`to_main` 點商品與取消 | 約 150 秒 | 約 50 秒 | **90–120 秒** | `wait=1.5`、`PURCHASE_CANCEL` 1.0；`opened no purchase dialog` 重點 |
| 3 | `PlayTurn` 固定等待 | 357 秒 | 約 190 秒 | **140–180 秒** | 開頭 `sleep(1)`、Win Rate `wait=1.5`、0.5 秒輪詢 |
| 4 | `RouteMap` 點節點 `wait=2` x 2 + 拖曳 | 165 秒 | 約 50 秒 | **100–130 秒** | 每次呼叫 7.5–11.5 秒 |
| 5 | MirrorHub `rate_limit` 預設 1000 + 排序 + pre_delay | 約 280 秒（BattleTurn 的非動作部分，扣掉遊戲轉場約 100 秒） | | **100–150 秒（估計）** | 影響每個轉場與每個回合 |
| 6 | `Event` 每步 `wait=1.5` | 148 秒 | 約 50 秒 | **90–100 秒** | hub 的下一輪還會再延遲 |
| 7 | `Formation` `TO_BATTLE wait=3`、卡片 `wait=1.2` | 78 秒 | 約 35 秒 | **35–45 秒** | |
| 8 | 明確 post_delay：`Victory` 2000、`GiftGet` 1500 等 | 約 90 秒 | 約 35 秒 | **40–60 秒** | Victory 動作本身什麼都不做 |
| 9 | `PickGift`／`RewardCard`／`PickThemePack`／起手動作的 `wait=1.5–2.5` | 約 90 秒 | 約 40 秒 | **40–50 秒** | |
| 10 | `Loading` post_delay 1000 的偵測落後 | 約 20 秒 | | **10–15 秒** | |

合計可省約 1000–1250 秒（17–21 分鐘，約 16–19%）。以上都是估計，要靠 #58 的逐處實機驗證；每處改成條件等待（輪詢截圖直到目標出現 / 畫面靜止，附逾時）後再量。

## 5. 建議（依每局可省秒數排序）

1. **商店融合：不要每次逐格掃**（約 350–420 秒；#62 第 1 點、#77）。三步由小到大：(a) `FUSE_NEUTRAL` 的 tap 補 `wait=0`（立刻省 200 秒以上，一行）；(b) 在 `visit` 記「持有飾品沒變就不重掃」（約 7 次白掃）；(c) #77 的讀圖掃描取代逐格點，格內點擊只留要選的。
2. **商店買／取消：條件等待與記住點過沒開窗的商品**（約 90–120 秒；#62 第 2、3 點、#76）。#76 的「從格子圖像讀 tier 與徽章」完成後，`buy_one` 不用為了讀體系每個都開窗；先做 `opened no purchase dialog` 記進 `visit`。
3. **`PlayTurn` 改條件等待**（約 140–180 秒；#58）。開頭 `sleep(1)` 改為「START 圓盤亮且穩定」；Win Rate `wait=1.5` 改為輪詢圓盤亮（0.2 秒粒度）；START 後的 0.5 秒輪詢改 0.2 秒。注意 `#69` 的「圓盤讀暗仍按」與 `SAME_SCREEN` 計數。
4. **`RouteMap`：點節點用條件等待、少拖曳**（約 100–130 秒；#58，與 #61 相關但不同）。`tap(wait=2)` 後直接輪詢 `MapNodePanel`；`BUS_HOME` 改為休息位附近，避免每次呼叫都拖 72 像素。
5. **新 issue：MirrorHub 的 `rate_limit` 與排序**（約 100–150 秒，估計）。`rate_limit` 設 300–400 毫秒；`BattleTurn`／`BattlePause` 移到 `Stuck` 之後（最常命中，且是便宜的模板比對）；`BattlePause` 的 pre_delay 設 0、post_delay 1000 降到 300–500。要實測 CPU／OCR 負載與看門狗行為。
6. **`Event` 每步 `wait=1.5` 降為 0.4–0.5**（約 90–100 秒；#58），hub 的下一輪輪詢本身就會再給 0.5–1 秒。
7. **`Formation`：`TO_BATTLE` 後輪詢 `participants` 是否消失，取代 `wait=3`；重選用條件等待**（約 35–45 秒；#58）。
8. **新 issue：pipeline 的明確 post_delay 重新盤點**（約 40–60 秒）。`Victory` 2000、`GiftGet` 1500、`ClaimPopup`／`LevelWarning`／`MirrorEnterDialog` 2000 這類，下一個畫面本來就會被 hub 再輪詢，延遲可砍半以上。
9. **其餘動作的固定等待（`PickGift`、`RewardCard`、`PickThemePack`、起手動作）**（約 40–50 秒；#58）。
10. **新 issue：查遊戲內是否有戰鬥加速選項**（若有，影響最大：戰鬥演出 62 分鐘 / 局）。目前 repo 沒有任何速度相關處理；是否存在、是否能由 bot 設定：未驗證。

另有一項與效能無關但在 B 看到：`stuck: battle over 20 min`（17:12，第 5 層 Boss，實際該場才進行約 5.6 分鐘）觸發了 L3 重開遊戲，損失約 3.5 分鐘；`RUN["battle_start"]` 疑似殘留（原因未查明，可能與 #80 的 Formation 重置有路徑漏洞），建議另開 issue 查。

## 對應既有 issue

- #58 條件等待：第 3、4、6、7、9 項直接屬於它；本報告提供各處「固定等待實際花了多少秒」，可排序。
- #62 商店太慢：第 1、2 項（對照 #62 描述，一次造訪 152 秒；本次 15 次造訪平均 186 秒，C 最多 447 秒）。
- #76／#77 商店掃描：第 1、2 項的根本解。
- #61 地圖恢復：與第 4 項的 Bus 拖曳不同（那是恢復流程，這是正常導航每次都拖）。
- 新 issue 建議：MirrorHub rate_limit／排序／post_delay（第 5、8 項）、戰鬥加速選項調查（第 10 項）、battle_start 殘留（B 的 L3）。
