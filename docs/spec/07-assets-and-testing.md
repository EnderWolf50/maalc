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

以下是 2026-10-13 困難鏡牢實機探測得到的做法，是實作指引，不是規則；括號裡的數字是實測值，門檻仍依上一節驗證。截圖以檔名列出，逐張說明在 [captures-2026-10-13.md](captures-2026-10-13.md)，截圖本身只留在本機。

- **勝率按鈕**：位置隨技能格數左右移動（實測每多一格右移約 38–40 px，x 從 966 到 1194；只派 1 人、只有 1 格時約 740，#52），所以用模板在夠寬的 ROI 裡找，不用固定座標；模板在各關卡都穩定命中（實測分數約 0.99）。開始圓盤固定在勝率按鈕左下方的同一個偏移。（實機：captures/53_battle_winrate_pressed.png、captures/56_battle_wait.png）
- **開始圓盤亮起**：用圓盤中心一小塊的亮度判斷（實測 HSV V 亮起約 254、未亮 128–142，門檻 160）。圓盤只要選到一格就亮；每格都選好、開始鍵可按，要看圓盤上方掛著的 `START` 牌子（`Battle/BattleStart.png`，只取牌子內的字，不含背景；roi 從圓盤位置推算，門檻 0.5）：2026-10-18 在 431 張各層截圖（含雪地）裡，有牌子 0.58–1.0（0.58–0.66 是牌子剛擺進來時），沒有 0.20–0.35（#145）。牌子在拖完放手 0.53–0.7 秒才擺進來，開始鍵在那之前就能按。下面說的雪地失效是另一個整塊字樣的舊模板。大半罪人 Stagger、只剩一格能選時，可以開打的圓盤只有約 189（`START` 牌子已經出現，tests/screens/BattleTurnStagger.png，#69）。字樣模板在明亮的雪地關卡失效，迴圈空轉 80 次。（實機：captures/180_f3abno_battle_map.png、captures/182_abno_winrate_tap.png）
- **回合開場動畫**：動畫還在播時點勝率可能沒效果或把自動配卡切回關閉；改用亮度確認後，約 100 個回合中有 13 次要重試，全部自動恢復，沒有誤開始。所以每次點完都要重新確認狀態。
- **地圖頁錨點**：左上的 `Exploring Floor` 標題會被節點蓋住，錨點改用右側的圖示欄與齒輪；標題只在看得到時讀樓層。（實機：captures/202_f4ev_stuck.png）
- **地圖選路**（#26，2026-10-15 普通鏡牢實機）：地圖靜止時 Bus 固定在同一位置，相鄰一欄的三格在 Bus 右方 255 px、上下相隔 213 px。只有可走的連線上有灰色箭頭（chevron），用它判斷相鄰格能不能走。最上一格的徽章被頂端資源列蓋住，所以先把地圖往下拖約 70 px，並把 Bus 拖到畫面最左邊（x 50），好讀到後面四欄（#111；拖完重新找 Bus，`MapBus` 的 ROI 從 x 0 起）。節點類型看與主題包無關的標記：Cost 硬幣、飾品箱、Focused 的橘色 WARNING 環、Boss 的紅光（範圍內的紅色像素至少 1000 個：紅色主題包的「?」節點也有 388–506 個，三個 Boss 是 1530–1783，實機 2026-10-18）；事件與商店的圖示隨主題包變色，用 FeatureMatch（灰階形狀）比對。六角形的 Focused 環用顏色模板在橘色主題包只有 0.67，也改用 FeatureMatch。
- **戰前編隊的順序標記**（#27）：卡片上的數字直接 OCR 會把 4、6、9 讀錯。先用顏色切出數字（HSV V > 200 且 S > 120，橘色 `SELECTED` 與青色 `BACKUP` 都符合），變成白底黑字，再對每張卡片的數字區只做文字辨識（`only_rec`），實機截圖 22 個數字全對。陣亡者的卡片是灰的（平均 S 約 2，活著的卡片 65 以上）。編隊頁會記住「Details」檢視（技能與 E.G.O），那個檢視沒有順序標記，要先點按鈕左端的 `»` 切回卡片檢視。（實機：captures/206_formation_with_dead_sinner.png、captures/50_formation_collapse_details.png、captures/48_formation_normal_view.png）
- **勝率按鈕的兩種狀態**（#27）：勝率生效後按鈕底色變紅，同一張模板只剩約 0.70，所以用「未按」與「已按」兩張模板（命中 ≥ 0.845，其他畫面 ≤ 0.59）。按鈕的 y 固定，只有 x 會移動；圓盤中心在模板左上角的 (−66, +26)。
- **事件按鈕**：`SKIP`、`Proceed`、`Continue`、`Commence` 都在右下同一個紅色按鈕，沒作用時變灰，可用顏色判斷是否可點。成功率等級（Very High … Very Low）的文字顏色各不相同。（實機：captures/132_event_entered.png、captures/149_ev2_check.png）
- **罪人列座標**：商店與事件頁的罪人列頭像間距不同，不能共用一組座標。（實機：captures/213_revive_selected.png、captures/137_event_check_after_tap.png）
- **數量會變的卡片**：獎勵卡 1–4 張、飾品選擇頁 1 或 4 張，都置中排列，要先找出卡片再點，不用固定格位。（實機：captures/154_focused_unknown.png、captures/197_f3boss_rewards_card.png）
- **捲動手勢**（#56，實機觀察 (2026-10-16)）：捲動清單、格子或地圖一律用 `agent/actions.py` 的 `scroll`，不用 swipe。遊戲會吃掉拖曳的第一步移動，手指放開時還在移動就會繼續滑。做法（#114，2026-10-18 校正）：按下、先移 10 px（被吃掉的那步）、停 0.1 秒（停 0.05 秒時約 200 次有 1 次下一步也被吃掉、少 20 px；不停時 10 次有 2–3 次）、再每 10 ms 移 20 px 到終點、停 0.55 秒再放開。放手後滑多遠只看手指放開前的速度，而這個速度在手指停住時很快衰減（約 e^(−10 x 停留秒數)），所以手指快、停久比慢慢移再停更省時。地圖、隊伍列表、觀測頁格子共 126 次 50–300 px：誤差都 ≤ 1 px，每次 0.62–0.77 秒（停 0.05 秒時量的；停 0.1 秒多 0.05 秒；之前 0.73–1.25 秒）；減速到終點反而因第一步變大而少走（數字見 [docs/perf/2026-10-18-drag-experiments.md](../perf/2026-10-18-drag-experiments.md)）。以下是 #56 的舊參數（按下、停 0.1 秒、每 20 ms 移 10 px、在終點停 0.5 秒）量到的：觀測頁實測 10 次 150–300 px：每次都只多 1 px；改前 1 秒的 swipe 多 55–120 px（1.36–1.40 倍）。停 0.4 秒仍偶爾差 8 px，0.3 秒多 9 px，0.1 秒多約 80 px。地圖拖 40–90 px 誤差 ±1 px（改前 0.78 倍補償的 swipe 差到 5 px）。拖過頭尾的清單放開後會彈回，要等約 0.5 秒再截圖。選技能的連線（`battle.guard_chain`）不是捲動，照舊在最後一格一到就放開（手指速度上限見 [03](03-decisions.md#8-戰鬥) 開局連續防禦）。
- **淡出中的頁面**：確認後頁面淡出的期間仍可能比對到舊畫面；處理完要等畫面換掉再判斷，避免重複點擊。

## OCR 與模板的分工

| 用 | 對象 |
|---|---|
| OCR | 事件選項、主題包標題、飾品名稱；Cost、HP、樓層、金錢這類數字 |
| 模板 | 圖示、按鈕、畫面的固定標記 |

- OCR 比對時用 `expected` 對照遊戲資料檔（見 [05-game-data.md](05-game-data.md)）。（#13，[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）
- OCR 模型預設用 `ppocr_v6/small`。散佈時必須附上 Apache-2.0 授權文件和出處。（#13）

## 換季後找出失效的素材

- CI 每次都跑截圖測試。PR 只改文件（`docs/`、根目錄的 `*.md`、`LICENSE`）或只改 `gui/` 時不跑，其他變更和 main 的每個 commit 都跑。（#13）
- 每季更新遊戲資料檔時，重截約 20 個關鍵畫面加進測試。清單在實作素材時再列。（#13、#19）
- 命中分數與門檻的餘裕小於 0.05 的節點，標出來人工檢查。（#13）
- 執行時開著 `save_on_error`，讓實機辨識失敗留下繪圖。（#13）

## 測試截圖的存放與授權

- 測試截圖放在主 repo 的 `tests/`。格式為 720p PNG，以 oxipng 壓縮，必須遮掉三個身分區域：UID 欄、帳號 e-mail、主畫面左下 LV 面板上方的玩家名稱。（#13）
- 2026-10-13 困難鏡牢的探測截圖（[02-screens.md](02-screens.md) 的「實機截圖」欄，逐張說明在 [captures-2026-10-13.md](captures-2026-10-13.md)）只留在本機，還沒遮蔽；實作時依上一條處理後搬進 `tests/`，作為第一批測試截圖。（#13）
- 直接傳給 `post_recognition`／`run_recognition` 的圖不會被縮放，所以測試截圖必須已經是 720p。（#4）
- 測試截圖一直放主 repo 的 `tests/screens`，探測截圖那批也一樣，不搬去 testset repo。（#13，2026-10-19 使用者確認）
  - 原本的規則是總量超過約 50 MB 就搬。2026-10-19 量到 `tests/screens` 的工作目錄有 57 MB（`du`），git 歷史裡的截圖 blob 約 62 MB（`git cat-file` 的磁碟大小）。沒有搬，原因有三：
    - 已提交的截圖留在 git 歷史裡，搬走也不會讓 clone 變小。
    - CI 每個 shard 都要用到全部截圖（`maatools.config.mts`）。
    - 放在主 repo，`tests/test_screens_privacy.py` 會在加入截圖的同一個 PR 檢查遮蔽。放到另一個公開 repo 的話，推上去就公開了，要等到更新 submodule 的 PR 才會檢查。
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
| 批次 OCR 名稱 | pytest（`tests/test_pipeline.py`） | 同一個 next 清單裡沒有兩個 OCR 用同一個名字（內嵌 OCR 都要有自己的 `sub_name`） | #149 |

- `maa-tools test` 不跑 Agent；Agent 的部分由 pytest 涵蓋。（#4）
- 不使用官方 `DbgController`：pip wheel 沒附它的動態庫。（#4）
- 錄製檔容易隨改版失效。（#4）
- 錄製的重播檔不放主 repo。第一批要進版本控制時，才建獨立的 testset repo，用 submodule 掛在重播檔自己的路徑，不和 `tests/screens` 混在一起。testset repo 的 CI 要對重播檔裡的畫面檢查同樣三個身分區域（`tests/test_screens_privacy.py`）。（#19，2026-10-19 使用者確認）
- Tasker 端記憶體：`tools/ocr_memory_check.py` 用 `tests/screens` 輪流餵 `MirrorHub` 跑幾分鐘、記下行程記憶體；最後一分鐘的中位數比第二分鐘多 300 MB 以上，或任何時候超過 6 GB，就失敗。要 OCR 模型，CI 不跑，改 pipeline 的 OCR 或升級 MaaFramework 時手動跑。（#149）

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
- 輸入方式的 `Default` 不含 `EmulatorExtras`，但 PI V2 的 ADB 控制器沒有輸入方式欄位，GUI 會沿用 Toolkit 找到的裝置 `input_methods`。不強制 `EmulatorExtras`，能連上、能點擊即可。（#7、#22）
- 使用者必須在遊戲設定裡關掉戰鬥中的旁白等待。（#16）
- 使用者必須把遊戲設定的 Change UI Design 維持 Default；Dark 未驗證。（#48）

## 未決

目前沒有未決項目。
