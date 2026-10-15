# 00 概觀

本章說明 `maalc` v1 的目的與範圍：v1 做什麼、不做什麼、延後到 v1 之後的功能、目標環境、技術選型，以及其餘各章的分工。細節規則寫在後面各章，本章只列結論並註明來源。

## 目的

`maalc` 是用 MaaFramework 自動化 Limbus Company 鏡牢的工具。v1 的目標是無人看管、連續跑困難鏡牢，並在多支隊伍之間輪替。（#1）

本規格把各 ticket 的定案改寫成規範式條文，可以直接交給人或 agent 開工；「為什麼」連到 ADR，不在規格裡重寫。（#19）

## v1 做什麼

| 項目 | 內容 | 來源 |
|---|---|---|
| 鏡牢 | 普通與困難，第 1–5 層；難度可以逐層切換 | #1、#8、#9 |
| 隊伍與輪替 | 隊伍數量不限，依清單順序輪替，用途不符就跳過 | #9、#19 |
| 戰前編隊 | 依出戰順序方案重選出戰順序 | #9、#16 |
| 開局 | 依星光方案購買星光；依主要體系選初始飾品；觀測飾品一律 Refuse | #9、#19 |
| 戰鬥 | 只按勝率加開始；處理全滅、陣亡與戰鬥中的事件 | #1、#16 |
| 飾品、商店、合成 | 精簡版：依主要體系挑選與購買，3 個非主要體系的飾品合成一個 | #10 |
| 主題包與事件 | 依主題包方案挑主題包；事件用通用規則加事件覆寫表；依每隊順序選獎勵卡 | #11 |
| 地圖尋路 | 只看相鄰一欄，依權重貪婪選擇 | #12 |
| 困難模式 | Boss 後的選擇計入試煉風險（1.117.0 起普通局也有）；Super Shop | #17、#28 |
| 結算 | 五層全部通過才依每週獎勵設定切開關並 Claim；否則放棄獎勵 | #8、#17、#19 |
| 中途接續 | 從任何畫面啟動都能接手，以畫面為準 | #8 |
| 卡住處理 | 偵測卡住，分三級恢復，必要時重啟遊戲；停止時保存證據並發 webhook | #14 |
| 設定 GUI | 自製設定 GUI（`gui/`）編輯所有使用者設定：執行選項、具名方案、隊伍、事件與試煉風險覆寫；介面提供繁中與英文，預設繁中。執行仍在 MXU／MFAAvalonia | #1、#18、#19 |

驗收標準是無人看管、連續 10 局困難鏡牢、0 次停止；累計 30 局標記為穩定。詳見 [07-assets-and-testing.md](07-assets-and-testing.md)。（#14）

## v1 不做什麼

### Out of scope

以下功能不在 `maalc` 的規劃內：（#1）

- 無限鏡牢（Parallel Superposition，第 6–10 層），一律不開啟。（#17）
- 日常任務：經驗本、紐本、領獎、狂氣換體、腦啡肽模組。v1 只做鏡牢。
- 安裝程式與自動更新。v1 只用 GitHub Actions 產出一個 zip：bot、resource、MFAAvalonia、設定 GUI 的執行檔放在同一個發佈目錄（做法參考 MaaPracticeBoilerplate 的 workflow）。（#1、#4、#19，2026-10-14 定案）
- Windows 原生客戶端（Win32 控制器）。
- 中文或其他語言的遊戲畫面辨識。
- 戰鬥防禦選項、技能配置與配卡決策。
- 必買／必棄清單、第二體系等進階飾品策略。

### Deferred（v1 之後）

以下功能已決定延後，最終要做：（#1）

| 功能 | v1 的替代做法 | 來源 |
|---|---|---|
| 激進合成與固定配方合成 | 3 個非主要體系的飾品合成一個主要體系的飾品 | #10 |
| 飾品升級 | 不升級，錢優先用於購買與刷新 | #10 |
| 依 HP 判斷治療 | 預設有人陣亡才復活 | #10 |
| 依主題包掉落飾品的體系評分 | 只依主題包方案挑選 | #11 |
| 依體系挑飾品卡（需 OCR 卡片文字） | 依每隊的獎勵卡順序挑選 | #11 |
| 尋路往前看兩欄並加總權重 | 只看相鄰一欄 | #12 |
| 觀測飾品（E.G.O Gift Search） | 一律 Refuse | #19 |

## 目標環境

| 項目 | 規範 | 來源 |
|---|---|---|
| 模擬器 | 驗收以 MuMu 12 為準（實測版本 MuMu Player Global 6.8.3.0）；其他 ADB 模擬器只要求能用 | #1、#7 |
| 連線 | ADB；截圖與輸入方式交給框架自動偵測，能連上、能點擊即可，不指定 `EmulatorExtras` | #7、#22 |
| 解析度 | 任何 16:9 解析度；MaaFramework 預設把截圖縮到短邊 720，素材以 720p 製作 | #1、#7 |
| 遊戲 | Android 版 Limbus Company，套件名 `com.ProjectMoon.LimbusCompany`，實測版本 1.116.2 | #2、#7 |
| 遊戲語言 | 只支援英文客戶端。官方語言只有韓、日、英，沒有中文 | #1、#2 |
| 輸入 | 戰鬥只用觸控；`P`／`Enter` 按鍵不保證有效，不依賴 | #2、#16 |
| 遊戲設定 | 使用者必須在遊戲設定裡關掉戰鬥中的旁白等待 | #16 |

非 16:9 解析度的行為未驗證，不在支援範圍。（#2）

## 技術選型

| 項目 | 選擇 | 來源 |
|---|---|---|
| 框架 | MaaFramework 5.x（Python 綁定 `maafw`，實測 5.14.3） | #4、#7 |
| 架構 | 流程寫在 Pipeline 的 `MirrorHub`，決策寫在 Python Agent（[ADR 0002](../adr/0002-pipeline-hub-and-agent-decisions.md)） | #8 |
| Agent | Python，由 `interface.json` 的 `agent.child_exec`／`child_args` 啟動 | #1、#4 |
| 專案骨架 | 以 MaaPracticeBoilerplate（MIT）為起點，手動搬入所需檔案，保留其版權聲明 | #4 |
| 執行介面 | ProjectInterface V2，只放控制器、資源與鏡牢任務，沒有使用者選項；MXU 與 MFAAvalonia 都必須能跑，開發時用 MXU。不依賴只有其中一邊支援的功能 | #1、#6、#19 |
| 設定 GUI | Tauri 2 + React/TypeScript，放在 `gui/`，是 v1 新增的交付物。第一階段只編輯設定，不執行 bot（[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)） | #19 |
| 設定 | 使用者設定全部放在 `<root>/config/settings.json`，由設定 GUI 寫入、Agent 讀取，格式由 `settings.schema.json` 描述（[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)）；遊戲資料放資料檔（[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)） | #9、#11、#19 |
| 辨識 | 文字與數字用 OCR（`ppocr_v6/small`），圖示與按鈕用自製模板；地圖節點先找 Bus 再比對相鄰格位，不用整張地圖的偵測模型 | #3、#13 |
| 授權 | MIT。AGPL 專案（AALC、MaaLimbus、Lix）可以讀、不能抄，程式碼、圖片和模型都不複製；不用 Ultralytics 訓練模型（[ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md)） | #1、#3 |

## 用語

規格中的領域用語以 repo 根目錄的 [GLOSSARY.md](../../GLOSSARY.md) 為準。遊戲名詞（罪人名、體系、主題包、飾品、星光加成、按鈕文字）保留英文原文，和英文版遊戲畫面一致。（#18、#19）

## 各章分工

| 章 | 內容 |
|---|---|
| [00-overview.md](00-overview.md) | 本章：目的、範圍、環境、技術選型 |
| [01-architecture.md](01-architecture.md) | `MirrorHub`、導航、全域彈窗、Pipeline 與 Agent 分工、中途接續、一局的流程 |
| [02-screens.md](02-screens.md) | 畫面清單與每個畫面讀什麼、做什麼 |
| [03-decisions.md](03-decisions.md) | Agent 的決策規則：輪替、飾品、商店、主題包、事件、尋路、Boss 後選擇 |
| [04-settings.md](04-settings.md) | 設定檔結構：執行選項、方案、隊伍、覆寫、檢查 |
| [05-game-data.md](05-game-data.md) | 資料檔格式：主題包清單與預設方案、事件覆寫表、尋路權重、Cost 對照表與商店數字、試煉風險表 |
| [06-recovery.md](06-recovery.md) | 卡住偵測、三級恢復、停止與通知 |
| [07-assets-and-testing.md](07-assets-and-testing.md) | 素材製作、測試、驗收 |

（#19）
