# 07 素材、測試與驗收

本章規定模板素材怎麼截圖、裁切、命名與驗證門檻，OCR 與模板的分工，換季時怎樣找出失效的素材，測試截圖的存放與授權，離線與實機的測試分工，v1 的驗收條件與量測方式，以及驗收用的參考環境。卡住與恢復的行為見 [06-recovery.md](06-recovery.md)。

## 截圖與裁切

- 截圖必須經過 MaaFramework 控制器，縮到短邊 720 後再裁切。規則只限定截圖方式，不限定工具。（#13）
- MaaFramework 控制器預設 `image_target_short_side_=720`，不需另外設定；模擬器跑任何 16:9 解析度都會得到 1280×720 的截圖。（#4、#7）
- 推薦工具：VS Code 擴充 Maa Pipeline Support，或 MaaPipelineEditor（網頁版，截圖時要啟動它的本機服務）；MaaFramework 的 ImageCropper 當備用。（#4、#13）
- 不得在開啟 HDR 或色彩自動管理的狀態下截圖。（#13）
- 素材一律自製，不複製 AGPL 專案的圖片與模型。（[ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md)）

### ROI 與遮罩

- 每個節點必須設緊湊的 `roi`，盡量不做全畫面搜尋。（#13）
- `green_mask` 只用在圖示中間透出動態背景的情況，而且只遮那一塊。（#13）

## 命名與目錄

- 路徑格式：`resource/base/image/<功能>/<名稱>.png`。（#13）
- 用 PascalCase，`<名稱>` 和使用它的節點名稱相同。（#13）
- 同一元素有不同狀態時加後綴，例如 `Hover`、`Disabled`。（#13）
- 目錄名稱不得以 `_` 開頭。（#13）
- 之後若支援其他語言，加一層 `resource/<語言>`，只放和 `base` 不同的圖。v1 不做。（#13）

## 門檻驗證

- 每個 TemplateMatch 節點至少準備一張應該命中的截圖，和一張容易混淆、應該不命中的截圖，用 `maa-tools test` 驗證。（#13）
- 門檻取在「命中截圖的最低分」和「不命中截圖的最高分」的中間，最低不得低於 0.8。（#13）
- 改動模板、ROI 或門檻後都必須重跑。（#13）
- `maa-tools test` 找不到圖片時只會警告，不會失敗，所以必須另外檢查每個測試引用的圖片都存在。（#13）
- 參考數據：同一模板比對 1080p 縮成的 720p 截圖，分數最低約 0.93（小字、半透明元素）。（#7）

## 辨識方法的實機經驗

以下是 2026-10-13 困難鏡牢實機探測得到的做法，是實作指引，不是規則；括號裡的數字是實測值，門檻仍依上一節驗證。截圖路徑相對於探測目錄 `~/.cache/maalc-probe/`。

- **勝率按鈕**：位置隨技能格數左右移動（實測每多一格右移約 38 px，x 從 966 到 1194），所以用模板在夠寬的 ROI 裡找，不用固定座標；模板在各關卡都穩定命中（實測分數約 0.99）。開始圓盤固定在勝率按鈕左下方的同一個偏移。（實機：captures/53_battle_winrate_pressed.png、captures/56_battle_wait.png）
- **開始圓盤亮起**：用圓盤中心一小塊的亮度判斷（實測 HSV V 亮起約 254、未亮約 133），不要用 `START` 字樣的模板。字樣模板在明亮的雪地關卡失效，迴圈空轉 80 次。（實機：captures/180_f3abno_battle_map.png、captures/182_abno_winrate_tap.png）
- **回合開場動畫**：動畫還在播時點勝率可能沒效果或把自動配卡切回關閉；改用亮度確認後，約 100 個回合中有 13 次要重試，全部自動恢復，沒有誤開始。所以每次點完都要重新確認狀態。
- **地圖頁錨點**：左上的 `Exploring Floor` 標題會被節點蓋住，錨點改用右側的圖示欄與齒輪；標題只在看得到時讀樓層。（實機：captures/202_f4ev_stuck.png）
- **事件按鈕**：`SKIP`、`Proceed`、`Continue`、`Commence` 都在右下同一個紅色按鈕，沒作用時變灰，可用顏色判斷是否可點。成功率等級（Very High … Very Low）的文字顏色各不相同。（實機：captures/132_event_entered.png、captures/149_ev2_check.png）
- **罪人列座標**：商店與事件頁的罪人列頭像間距不同，不能共用一組座標。（實機：captures/213_revive_selected.png、captures/137_event_check_after_tap.png）
- **數量會變的卡片**：獎勵卡 1–4 張、飾品選擇頁 1 或 4 張，都置中排列，要先找出卡片再點，不用固定格位。（實機：captures/154_focused_unknown.png、captures/197_f3boss_rewards_card.png）
- **淡出中的頁面**：確認後頁面淡出的期間仍可能比對到舊畫面；處理完要等畫面換掉再判斷，避免重複點擊。

## OCR 與模板的分工

| 用 | 對象 |
|---|---|
| OCR | 事件選項、主題包標題、飾品名稱；Cost、HP、樓層、金錢這類數字 |
| 模板 | 圖示、按鈕、畫面的固定標記 |

- OCR 比對時用 `expected` 對照遊戲資料檔（見 [05-game-data.md](05-game-data.md)）。（#13，[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）
- OCR 模型預設用 `ppocr_v6/small`。散佈時必須附上 Apache-2.0 授權文件和出處。（#13）

## 換季後找出失效的素材

- CI 每次都跑截圖測試。（#13）
- 每季更新遊戲資料檔時，重截約 20 個關鍵畫面加進測試。清單在實作素材時再列。（#13、#19）
- 命中分數與門檻的餘裕小於 0.05 的節點，標出來人工檢查。（#13）
- 執行時開著 `save_on_error`，讓實機辨識失敗留下繪圖。（#13）

## 測試截圖的存放與授權

- 測試截圖先放在主 repo 的 `tests/`。格式為 720p PNG，以 oxipng 壓縮，必須遮掉 UID 和帳號名稱。（#13）
- 2026-10-13 困難鏡牢的探測截圖（`~/.cache/maalc-probe/captures/`，[02-screens.md](02-screens.md) 的「實機截圖」欄）目前放在 repo 外，還沒遮蔽；實作時依上一條處理後搬進 `tests/`，作為第一批測試截圖。（#13）
- 直接傳給 `post_recognition`／`run_recognition` 的圖不會被縮放，所以測試截圖必須已經是 720p。（#4）
- 總量超過約 50 MB 時，搬到獨立的 testset repo，用 submodule 引用。（#13）
- README 必須註明：遊戲素材 © Project Moon，不在 MIT 授權範圍內。（#13，[ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md)）

## 測試策略

### 離線（CI）

| 測試 | 工具 | 涵蓋 | 來源 |
|---|---|---|---|
| Pipeline 檢查 | `maa-tools check` | Pipeline 與 `interface.json` 的格式 | #4 |
| 畫面節點 | `maa-tools test`，每個畫面節點一份 | 節點命中與不命中 | #13、#14 |
| 設定檢查 | GUI 與 Agent 各自的單元測試，共用同一批範例設定檔 | `settings.schema.json` 的結構檢查與跨物件檢查；兩邊對同一份檔案必須給出相同的錯誤 | #19 |
| Agent 邏輯 | pytest，用 Python `CustomController` 餵截圖 | 輪替游標、地圖重試額度、選路、卡住偵測、恢復升級上限 | #4、#14 |
| 回歸 | `RecordController` 錄下驗收局，`ReplayController` 重播 | 整條流程；行為不符就失敗 | #4、#14 |

- `maa-tools test` 不跑 Agent；Agent 的部分由 pytest 涵蓋。（#4）
- 不使用官方 `DbgController`：pip wheel 沒附它的動態庫。（#4）
- 錄製檔容易隨改版失效。（#4）
- 錄製的重播檔不放主 repo，等 testset repo 建好再放。（#19）

### 只能實機

- 恢復流程：戰鬥中強制關遊戲、`To Window` 後 `Resume`。（#14）
- 維護公告與每週重置通知的彈窗。（#14）
- 驗收局本身。（#14）

## 驗收

### v1 通過條件

全部成立才算通過：（#14）

- 無人看管，連續 10 局困難鏡牢。只計算困難局（有一層是困難就算，見 [03-decisions.md](03-decisions.md) 第 2 節）；中間不能夾使用者手動跑的局。（#14、#19）
- 分至少 2 次執行（bot 啟動）完成。
- 每支輪替中的隊伍至少跑到 2 局。
- 0 次停止。
- 允許 L3 重啟遊戲，但每局最多 1 次。

驗收局大多是不用每週獎勵的困難局；用不用每週獎勵只差結算時的開關，流程相同。（#14、#17）

### 「穩定」標籤

累計 30 局符合上述條件（0 次停止、每局 L3 ≤ 1）才標為穩定；30 局不必連續。（#19）依據：連續 N 局都沒失敗，只能證明失敗率低於約 3/N；10 局約對應 30%，30 局約對應 10%。（#14）

### 量測

- 以 [06-recovery.md](06-recovery.md) 的 `runs.jsonl` 判定：逐行檢查難度、隊伍、結果與 L3 次數。（#14）

## 參考環境

驗收以下列環境為準；其他 ADB 模擬器只要求能用。（#1、#7）

| 項目 | 值 |
|---|---|
| 模擬器 | MuMu Player Global 6.8.3.0（MuMu 12 系列），Android 12 |
| ADB 位址 | `127.0.0.1:16384` |
| 模擬器解析度 | 1920×1080（任何 16:9 皆可；MaaFramework 縮成 1280×720） |
| 遊戲 | `com.ProjectMoon.LimbusCompany`，英文 |
| MaaFramework | `maafw` 5.14.3（Python） |
| 截圖方式 | `MuMuPlayerExtras`，約 7 ms |
| 觸控方式 | `MuMuPlayerExtras`，約 51 ms |

- `Toolkit.find_adb_devices()` 會自動找到 MuMu，回傳 `EmulatorExtras` 截圖方式與 MuMu 的路徑和實例 index。（#7）
- 輸入方式的 `Default` 不含 `EmulatorExtras`。要走 MuMu 專屬觸控，必須明確 OR 上 `EmulatorExtras`；直接沿用 Toolkit 找到的裝置 `input_methods`（已全開）即可。PI V2 的 controller 設定必須確認這點。（#7）
- 使用者必須在遊戲設定裡關掉戰鬥中的旁白等待。（#16）

## 未決

目前沒有未決項目。
