# Android 版 Limbus Company 的客戶端事實

> 對應 ticket [maalc#2](https://github.com/EnderWolf50/maalc/issues/2)。AALC 引用一律固定在 [b0f4393](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0)。查證日期 2026-10-13。
> 標記：**已驗證**＝有一手來源；**間接**＝只能從 AALC 行為推得；**未驗證**＝沒找到一手來源，不可當事實寫進規格。

## 摘要

| 問題 | 答案 | 狀態 |
|---|---|---|
| 套件名稱 | `com.ProjectMoon.LimbusCompany` | 已驗證 |
| Launch activity | 查不到類別名稱。AALC 不指定 activity，用 launcher intent 啟動 | 未驗證（activity 名稱） |
| 遊戲語言 | 官方站只列 KR／JP／EN，沒有中文；英文是否預設未驗證 | 部分已驗證 |
| 首次啟動／更新畫面 | 一手來源沒有；只能從 AALC 的處理邏輯推得「標題頁、清快取確認、連線重試」 | 間接／未驗證 |
| 解析度／長寬比 | 一手來源沒有；AALC 假設 16:9，高度 720～2160 | 間接 |
| `P`／`Enter` 鍵 | `input keyevent 44`／`66` 在 AALC 實際使用，但 AALC 有「按鍵失效就改點擊」的備援，所以不能保證 | 間接 |

## 1. 套件名稱與 activity

- 套件名稱 `com.ProjectMoon.LimbusCompany`：
  - Google Play 商店網址 `https://play.google.com/store/apps/details?id=com.ProjectMoon.LimbusCompany`，官方站首頁（[limbuscompany.global](https://limbuscompany.global/)）的 Google Play 按鈕連到同一個 id（已驗證，2026-10-13 直接抓取兩個頁面）。
  - AALC 也寫死同一字串：[simulator_control.py:L133](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/simulator_control.py#L133)、[mumu_control.py:L273](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/mumu_control.py#L273)。
- Launch activity：**未驗證**。沒有取得 APK。AALC 的啟動方式都不需要 activity 名稱：
  - 一般模擬器：`monkey -p <pkg> -c android.intent.category.LAUNCHER 1`（[simulator_control.py:L253-L262](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/simulator_control.py#L253-L262)）。
  - MuMu：`device.app_start(<pkg>)`（[mumu_control.py:L332](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/mumu_control.py#L332)）。
  - 判斷前景：`dumpsys activity activities` 比對 `mResumedActivity:.*\s<pkg>/`，只比對套件，不比對 activity（[simulator_control.py:L244-L249](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/simulator_control.py#L244-L249)）。
- 規格建議：`StartApp`／`StopApp` 先填套件名稱；MaaFramework 是否接受只填套件名稱，以其文件為準（本研究未查）。要拿 activity 名稱，需在已安裝的裝置上執行 `adb shell cmd package resolve-activity --brief com.ProjectMoon.LimbusCompany`。

## 2. 遊戲語言

- 官方站首頁語言選單只有 KR、JP、EN（連到 limbuscompany.kr／.jp／.com）（已驗證，[limbuscompany.global](https://limbuscompany.global/) 原始碼）。
- Steam（PC）支援語言為 English、Japanese、Korean，標星號者有完整語音（[Steam appdetails 1973530](https://store.steampowered.com/api/appdetails?appids=1973530&l=english)）。這是 PC 版，Android 版是否相同**未驗證**。
- Google Play 說明：「All dialogue in the main story comes fully voiced in Korean.」（已驗證，[Google Play](https://play.google.com/store/apps/details?id=com.ProjectMoon.LimbusCompany&hl=en)）。Play 頁面沒有列出介面語言。
- **沒有官方中文**：以上三個一手來源都沒有中文。社群本地化以疊加層存在（例：[LimbusScreenTranslator](https://github.com/kimght/LimbusScreenTranslator) 在遊戲上方顯示翻譯，不改遊戲檔案），不可依賴。這支持 map 的「只辨識英文」前提。
- 英文是否為預設、遊戲內語言設定的位置、重啟後是否保留：**未驗證**（需要實機）。AALC 在非模擬器模式靠 Windows 登錄檔讀遊戲設定（[script_task_scheme.py:L221](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/script_task_scheme.py#L221)），Android 沒有對應機制，AALC 也沒有在模擬器上設定語言的程式碼。

## 3. 首次啟動與更新的畫面

一手來源（Play 頁面、官方站）沒有描述啟動流程。以下只是 AALC 處理過的畫面，用來推測存在這些畫面，細節**未驗證**，需要實機錄一次：

- 連線中（`base/connecting_assets.png`）、重試按鈕與倒數（`retry.png`、`retry_countdown.png`、`try_again.png`）：[retry.py:L161-L176](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L161-L176)。
- 標題頁：有「清除所有快取」按鈕與更新確認對話框（`clear_all_caches_assets.png`、`update_confirm_assets.png`）。模擬器上點標題頁要避開帳號和清快取區域，AALC 輪流點三個比例座標 (0.86,0.80)、(0.74,0.83)、(0.91,0.58)，15 秒內只點一次：[retry.py:L55-L72](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L55-L72)、[retry.py:L177-L181](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L177-L181)。
- 載入中（`waiting_assets.png`、`waiting_2_assets.png`）、週年活動彈窗（`close_anniversary_event_assets.png`）：[back_init_menu.py](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py)。
- 登入：AALC 完全沒有處理登入或帳號畫面，代表它假設帳號已綁定並自動登入。首次安裝的資源下載、使用者條款、帳號選擇 AALC 都沒涵蓋。Play 頁面說明：「User game profiles, including guest profiles, can be linked to an external (Apple/Google) account of choice.」（已驗證）。
- 資源下載大小：**未驗證**（未找到一手數字）。
- 規格含意：maalc 應把「首次安裝後的人工前置步驟」（登入、下載資源、選英文）列為使用者前置條件，自動化負責「已登入、已更新」後從標題頁到主選單。每次版本更新是否出現公告或強制更新畫面，需要下次更新時實測。

## 4. 解析度與長寬比

- 官方沒有公布 Android 解析度需求（官方站與 Play 頁面皆無）：**未驗證**。
- AALC 的假設：高度為 720、900、1080、1440、1800、2160 時自動套用，並假設寬度 = 高度 × 16/9（[mumu_control.py:L880-L912](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/mumu_control.py#L880-L912)、[retry.py:L66-L68](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L66-L68)）。這與 map 的「16:9 任意解析度」前提一致，但不能證明遊戲在非 16:9 時加黑邊或拉伸。
- AALC 對 720p 在 PC 模式警告「可能導致識別錯誤或卡死」（[script_task_scheme.py:L372](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/script_task_scheme.py#L372)），只在非模擬器分支。素材以 720p 製作時，小字模板要特別驗證。
- 需實測：模擬器設非 16:9 時的表現、遊戲內渲染比例／畫質設定（PC 有 `_renderingScale`，見 script_task_scheme.py:L205-L240；Android 是否有未驗證）。

## 5. `P`／`Enter` 在 Android 的有效性

- AALC 在一般 ADB 模擬器送 `input keyevent <code>`，`p`=44、`enter`=66、`esc`=111（keycode 表 [simulator_control.py:L34-L75](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/simulator_control.py#L34-L75)，發送 [L613-L623](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/simulator_control.py#L613-L623)）。這些對應 Android `KEYCODE_P`／`KEYCODE_ENTER`／`KEYCODE_ESCAPE`（見 [Android KeyEvent](https://developer.android.com/reference/android/view/KeyEvent)；本次未逐一開頁核對數值）。
- MuMu 12 走原生 IPC 的 key down／up，用 Linux 掃描碼（`p`=25、`enter`=28、`esc`=1）：[mumu_control.py:L1061-L1064](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/mumu_control.py#L1061-L1064)。MaaFramework 的 `ClickKey` 在 ADB 控制器用 Android keycode（見 [maafw-feasibility.md](maafw-feasibility.md)）。
- 戰鬥流程為 `P`、間隔 0.5 秒、`Enter`（[battle.py:L176-L178](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L176-L178)）。
- **按鍵不保證有效。** AALC 按完後等 1 秒檢查暫停圖示 `battle/pause_assets.png`，沒出現就把 `mouse_click_rate` 設為 True，改為點擊勝率卡片：座標為卡片位置偏移 (+50, -50)×(解析度/1440)，再點 `battle/gear_right.png`（[battle.py:L180-L191](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L180-L191)，另見 L413-L418）。可見在部分環境按鍵無效，觸控是備援。
- 觸控按鈕（AALC 使用的模板名稱，僅供定位概念）：勝率＝`battle/win_rate_card.png`（及 `win_rate_assets.png`、`gear_left.png`）；開始＝`battle/gear_right.png`。座標需用自己截的 720p 圖量，AALC 的圖不可複製（ADR 0001）。
- 結論：沒有一手證據證明 Android 版遊戲處理鍵盤事件。規格應把按鍵當先試路徑，並在 Pipeline 內加「按完檢查暫停圖示，失敗則點擊勝率與開始按鈕」的觸控備援節點；驗收時在 MuMu 12 實測。

## 未驗證清單（需要實機或 APK）

1. Launch activity 類別名稱。
2. 遊戲內語言設定的位置與預設值。
3. 首次安裝的資源下載（大小、畫面）、條款、登入流程。
4. 每次更新出現的畫面（公告、強制更新、差異下載）。
5. 非 16:9 時的行為、Android 畫質／渲染比例設定。
6. `P`／`Enter` 在 MuMu 12 的實際效果，以及各觸控按鈕的 720p 座標。
7. Play 頁面原始資料中出現版本 `1.113.1`，更新日期 Oct 2, 2026；未能確認該版本號是否為目前版本。
