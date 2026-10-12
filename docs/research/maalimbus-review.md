# MaaLimbus 架構與踩坑紀錄

對應 ticket：[maalc#5](https://github.com/EnderWolf50/maalc/issues/5)。

- 研究對象：[sairaisaika/MaaLimbus](https://github.com/sairaisaika/MaaLimbus)，AGPL-3.0-or-later。
- 固定版本：`fd78ca83f9e8395fddfaba3a4868825ba442ac17`（2026-10-13 shallow clone）。下文連結全部釘在此 SHA。
- 授權界線：依 [ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md)，本文只記錄想法與事實，全部用自己的話改寫，沒有複製任何程式碼、素材或模型。門檻值、ROI 這類參數屬於事實，可以引用，但 maalc 要在自己的素材上重新量測。
- 讀法：MaaLimbus 的 `PROJECT.md`（約 226 KB）、`docs/acceptance.md`（約 104 KB）是逐小時的開發日誌，篇幅極大。本文抽的是反覆出現的結論，不是逐筆摘要。

## 1. 一句話結論

MaaLimbus 的 Pipeline 其實只是外殼。真正的決策在 Python 裡「一次看一頁、只送一個輸入、驗證下一頁」的迴圈。這讓它很抗版本變動，但也很慢、很重。對 maalc 有用的是它的**安全規則與踩坑清單**，不是它的檔案結構。

## 2. 架構

### 2.1 Pipeline 的組織

- 只有一個檔案 [`assets/resource/base/pipeline/mirror.json`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/assets/resource/base/pipeline/mirror.json)，792 個節點。其中約 600 個是 `Global_global_team_N_*` 這種「把 GUI 選項寫進設定」的佔位節點，其餘才是流程節點。
- 辨識方式幾乎全是 `DirectHit`（754 個），`Custom` 辨識只有 38 個。動作 691 個是 `DoNothing`，`Custom` 動作約 100 個，原生 `Click` 只有 24 個、`Swipe` 2 個。換言之，MaaFramework 的模板／OCR 辨識幾乎沒用在 Pipeline 層，辨識都包在 Python 的自訂辨識 `limbus_scene` 裡。
- 入口節點 `MirrorHard` 是 `DirectHit` 加自訂動作 `limbus_preflight`，`next` 列出十幾個候選畫面節點（安全、過期、敗北、教學、進場確認、隊伍設定、星光、HOME、Drive、Enter…），`on_error` 指向 `LimbusUnknown`。
- 節點命名：PascalCase 描述動作或畫面，如 `MirrorHome`、`MirrorEnter`、`LimbusExpired`、`LimbusDefeat`。`Limbus*` 開頭的是終止或安全節點，`*Start` 結尾的是各子流程入口。
- 終止節點 `LimbusUnknown` 用自訂動作 `limbus_terminal` 結束，理由字串為「未知畫面或有界轉場已耗盡」。

### 2.2 「整輪」其實在 Agent 裡

[`docs/agent-loop.md`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/agent-loop.md) 說明：`MirrorLoop` 節點是 `DirectHit` 加 `Custom`，一擊中後在**同一個 action 內**跑完整座鏡牢，由自己的時間預算（預設 1.5 小時）而非節點 `timeout` 停止。

- 迴圈本體是純函式庫 `MirrorRunner`（[`src/maalimbus/runner.py`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/runner.py)），螢幕與輸入都以介面注入：`Device`（screencap／click／swipe／key）與 `Observer`（觀察一頁，回傳 JSON 紀錄）。有真機版、重播存檔幀版與假裝置版，因此可離線測。見 [`docs/runner.md`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/runner.md)。
- 一個 `step()`：觀察一頁，判定場景，規劃「唯一一個」輸入，送出，等畫面穩定，紀錄。規劃表是 [`window.py`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/window.py) 的 `plan_step(page, ...)`：頁面對應動作，每筆附 `expect`（下一頁允許的集合）。
- 在自訂動作內不能用 `tasker.post_task` 跑子節點（框架是單一 worker，會卡死自己），必須用 `Context.run_task` 同步執行。它因此包了一個代理物件，讓 observer 以為自己有 tasker。
- 偵測「目前畫面」：靠自訂辨識 `limbus_scene`，用 OCR 文字加正規化座標 ROI 判斷，**不用封面圖或背景**（[design.md 執行邊界](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L291-L316)）。頁面錨點登記在 `anchors.json`（實測 45 頁），並有 `tools/verify_anchors.py` 對存檔幀自檢。
- 斷點接續：靠持久化帳本，不靠 Pipeline。`RunStore`（[`storage.py`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/storage.py#L126)）存「進行中的 run」、輪替位置、收據。每個有副作用的輸入都先寫「意圖」再送，重啟時只看後繼畫面，不重送。設計文件的原則是「Resume in-progress runs without discarding them」。

### 2.3 Python Agent 內容

- [`agent/main.py`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/agent/main.py) 只負責註冊：1 個自訂辨識 `limbus_scene`，約 17 個自訂動作（preflight、terminal、team、各種 `*_proof`、`*_observe`、`mirror_loop`、`global_settings`、`main_task`）。附 `--self-test` 做載入與資源自檢，不碰控制器。
- [`agent/recognition.py`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/agent/recognition.py)（94 KB）是膠水層。邏輯在 `src/maalimbus/` 約 90 個模組，大致分「vision（讀畫面）、transaction（有副作用的流程）、policy（選擇）」。transaction 模組各自帶持久化意圖與收據：商店、獎勵、星光、飾品、部署、主題包、遊戲啟動。
- 場景切得很細：`window.py` 的頁面碼包括 HOME、DRIVE、MIRROR_ENTRY、DUNGEON_TEAM、PRE_BATTLE_TEAM、STAR_GRACES、INITIAL_GIFTS、THEME_PACKS、MAP、NODE_PANEL、REWARD_CARD、GIFT_PICK、GIFT_GET、SHOP、EVENT_*、BATTLE_*、EXPIRED_SESSION、TUTORIAL、DEFEAT、UNKNOWN 等。

### 2.4 interface.json

[`assets/interface.json`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/assets/interface.json)（3.5 MB，`interface_version: 2`）：

- `controller`：4 個，3 個 Win32（`windows-window`、`windows-background`、`windows`）與 1 個 `mumu-adb`（Adb，`display_long_side: 1920`）。Win32 以 `class_regex ^UnityWndClass$`、`window_regex ^LimbusCompany$` 綁視窗。
- `resource`：`en`、`jp`，路徑為 `base` 加語系覆蓋層（`resource/en`、`resource/jp` 只放 locale）。`languages`：`zh_cn`／`en_us`／`ja_jp` 三份 i18n。
- `agent`：`child_exec: python`，`child_args: ../agent/main.py`。
- `task`：6 個（`open_game`、`mirror_loop`、`experience`、`thread`、`rewards`、`stamina`）。`mirror_loop` 掛十個選項（隊伍模式、星光來源、初始飾品關鍵字、商店政策、跑圈界限、戰鬥配置…）。
- `option`：711 個，絕大多數由程式產生。**40 組全域隊伍**（`global_team_1..40`），每組有名稱、體系、12 格出戰順序，用 `select` 搭配 `saved`／`edit` 兩個 case，`edit` 時才展開子選項，並以 `pipeline_override` 的 `attach` 把值灌進 `Global_global_team_N` 節點。
- 隊伍輪替設定：隊伍模式有 saved／single／rotation 三種；輪替清單引用全域隊伍編號；實際輪替位置不在 interface，而在執行期帳本 `config/user-run-ledger.json`（`team_slots`、`rotation`、`completed_runs`、`active`、`receipts`）。
- 副作用：interface.json 長到 3.7 MB，超過自家 2 MiB 的上限檢查，打包失敗過一次（[PROJECT.md 十月十二日段](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/PROJECT.md#L1382-L1425)）。

### 2.5 docs／.research／tests

- `docs/design.md`：需求與事實帳本，條目導向（每節一個踩坑加規則）。`docs/acceptance.md`：附幀檔名、時間戳、座標、分數的實機驗收證據。`docs/native-control.md`：控制器組合，以及「後台視窗訊息是否被遊戲接受，必須以操作後的實際頁面變化證明」。`docs/handover-2026-10-08.md`：交接文件，坦承帳本與使用者實際看到的隊伍不一致。
- [`.research/horizon-scan-limubs-automation.md`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/.research/horizon-scan-limubs-automation.md)：對 AALC／LALC／SRA 等專案的橫評，與 maalc 已有的 AALC 研究重疊，不重述。
- tests：約 130 個檔案、近千個測試。離線重播存檔幀驗證辨識；`test_pipeline_spec` 確認節點引用的自訂 hook 都有註冊（避免到裝置上才發現）；`test_asset_hygiene` 檢查 anchors.json 的「已證實」與「待辦」不重疊，且每頁都有證據。

## 3. 記錄下的 Limbus 踩坑

按 maalc v1 範圍（鏡牢困難、Android、英文）整理，標明來源。

### 3.1 畫面轉場與等待

1. **UNKNOWN 不一定是動畫。** 有些畫面（如勝利結算）要按 Confirm 才會前進，但 OCR 把 `EX-CLEAR` 讀成 `EX-GLEAR`，被判成 UNKNOWN 並當作動畫等下去，永遠卡住（[acceptance.md L355-L363](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/acceptance.md#L355-L363)）。對策：用多個獨立證據（勝利字樣加右下 Confirm），不依賴單一小字。
2. **有些頁面會自己消失，不能點。** `WAIT_PAGES` 為 UNKNOWN／BATTLE_RESULT／DEFEAT：規劃器沒有控制可送，driver 等畫面變化而不是結束。DEFEAT 橫幅出現時後面的失敗對話框還沒畫完，過早停下會誤判（[`window.py` L76](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/window.py#L76) 的註解）。
3. **教學 overlay 蓋住真正的頁面。** 在 overlay 底下的文字上按 Enter 無效，還會吞掉一步。規則：看得到 overlay 的繼續鈕就優先認 overlay，不認底下標籤。教學書每張卡不同，右邊緣固定框會點空白；先點左上角書籤箭頭可整本關閉，勝過一頁一頁翻（[`resolve_overlay`，window.py L79](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/window.py#L79)）。
4. **每次輸入要有「預期的下一頁集合」。** 點擊後的畫面不在集合內就記為 `unexpected_successor` 並停下。用 `ANY` 哨兵處理「後繼未知，但原頁面必須消失」的關閉類操作。
5. **觀察節點可能回傳舊畫面。** 打包版跑到一半，部署人數從 2/12 比較，因為 observer 把點擊前的舊頁交給迴圈。修法是 observer 在節點沒有紀錄新頁時重跑並停止，而不是回傳舊事件（PROJECT.md 十月十二日段）。
6. **「Maa 回報成功」不代表遊戲收到點擊。** 缺 helper binary 時 MaaFramework 靜默退回 `adb shell input tap`，日誌顯示 `Controller.Action.Succeeded` 但遊戲忽略，表現為 `unexpected_successor`（[`adb_preflight.py` 開頭註解](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/adb_preflight.py)）。同一次實測：缺 helper 時卡住，補上 Maatouch 後連走六頁。

### 3.2 隨機延遲與點擊

- 點擊座標在「辨識到的框往內縮」的矩形內取樣；拖曳（選主題包）用 480–680 ms 的隨機時長；點擊前延遲約 180–480 ms，日誌中的實測值如 481／689／712 ms（[design.md 執行邊界](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L291-L316)、[acceptance.md L885-L892](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/acceptance.md#L885-L892)）。這些數字是它自己量的，maalc 要自己定。
- 每次送出前都**重新檢查頁面與資源政策**，不信任前一次觀察。
- 抖動是「擬人化」，不是正確性的來源。真正影響正確性的是後驗證。

### 3.3 未知畫面處理

- 預設是**取證後停下**，不是亂點：保留幀與 JSON 再停止（`LimbusUnknown`；README 的「Unknown pages still retain evidence and stop」）。
- 2026-10-12 之後放寬為有界探索（[`docs/bounded-exploration.md`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/bounded-exploration.md)）：先觀察載入／動畫幀；只嘗試獨立辨識到的導覽鍵（標題列 Close／Back／Return 需 OCR 唯一且 0.95，箭頭模板 0.92）；同一個未解決的導覽事件最多嘗試 3 個不同控制；每個輸入送出前先持久化保留，重啟後觀察後繼而不重送；不盲點重複座標。
- 自動產生的轉場候選資料標為 `reviewed=False`、`training_eligible=False`，要人審才能當訓練真值。
- 進入有副作用的交易（購買／選擇／收據）後，未解決狀態由各自的後繼規則先處理，再談探索；「場景轉場永遠不等於花錢許可」。
- 禁止點擊清單：Halt Exploration、獎勵卡的 Cancel、禮物 Refuse、技能檢定的 SKIP（等於放棄擲骰）、Give Up Rewards、每週重置通知的 Confirm（會丟掉進行中的 run）、過期 session 的 Cancel（獎勵領不到）。它們仍登記為錨點（用來辨識頁面），但規劃器拒絕把它們當目標（[`FORBIDDEN_CONTROLS`，window.py L50](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/window.py#L50)）。

### 3.4 斷點接續與遊戲啟動

- **每週重置會讓進行中的 run 過期**，進鏡牢時彈出「前一場 session 已過期，請領獎」。只有 Confirm 能把獎勵領出來，Cancel 會留著不領（`window.py` 的 `EXPIRED_SESSION` 註解，附證據幀編號）。
- 進場後出現「已有進行中 run」的提示要接受（commit `efe626b`，見 handover 文件）。
- 啟動遊戲：先檢查前景是否已是遊戲，是就**不重播標題／選單**；啟動意圖先持久化，未確認前拒絕第二次啟動（[`game_launch.py`](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/game_launch.py)）。套件名與 Activity 在 `session_flow.py`（`com.ProjectMoon.LimbusCompany`）。
- **它刻意不做「卡住就重啟遊戲」。** 設計文件寫明：錯誤時停止排程、寫出證據，之後才可選擇性關閉綁定的遊戲程序；關閉從來不是復原手段，也不是成功證明（[design.md L328-L334](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L328-L334)）。這與 maalc v1「卡住時重啟遊戲」的目標不同，maalc 需要自己設計。

### 3.5 隊伍輪替

- 輪替只在「五層通關、領獎收據、回到入口頁」都獨立證實後前進一次（`RunStore` 文件字串）。只有點擊 Confirm 不算領到獎勵（[design.md L358-L370](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L358-L370)）。
- 帳本與隊伍清單不符時**拒絕覆蓋**；已有紀錄的帳本不可重新播種，因為位置此時是證據而不是猜測。放棄一場 run 要明確呼叫 `abandon`，輪替位置保持原處，下次同一隊再來。
- **實際踩坑：帳本說要用 team 2，遊戲裡跑的是 team 1。** 它只送「點出戰位第 N 格」，沒有任何證據證明「第 N 格就是第 N 支存檔隊」。待做的校驗：把出戰位頁選中格子的 OCR 名稱，與之後預備戰鬥頁的 `Preset #N` 及 12 張身份卡對照（[handover §0](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/handover-2026-10-08.md)）。遊戲實際有 **40** 個隊伍格，它原先假設 20 個，後來改成 40（[team22-validation.md](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/team22-validation.md)）。
- 部署順序：每張已部署卡會印出順位，所以隊伍不必每場重排；已繼承正確順序時不要按 Clear Selection。要重設時，遊戲會先問 Reset Deployment Order，之後只有 0／容量才算完成（[design.md L183-L198](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L183-L198)）。人數計數器用固定 ROI 單行辨識，連續三幀讀不到「8 / 12」，改成較大 ROI 加偵測，並用 `\d{1,2}\s*/\s*\d{1,2}` 規則後才穩（PROJECT.md 十月十二日段）。

### 3.6 困難鏡牢細節

- 難度（Hard／Normal）不由封面色或圖案判定。困難模式要用模式標題、Refresh、Pack Search 三個獨立 ROI 才給出「HARD」，且相反的模式證據一律否決（[design.md L92-L113](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L92-L113)）。
- 地圖頁判定只用文字：左上「Exploring Floor N」加主題包行；節點美術、季節圖示、貨幣數字都不是錨點。樓層數字缺失時，標題可能被 OCR 拆成 `Exploring` 與 `Floor` 兩筆，兩種切法都要接受。
- 主題包：用 Swipe 往下拖已正向辨識的卡片；拖完之後新的地圖頁出現且包名相符才算成功。曾發生拖曳後第一個後繼幀還是舊頁，因此早到的舊地圖不允許觸發第二次拖曳。
- **路徑辨識至今沒解決。** 一次 GUI 實跑在 17 次點擊後以 `unexpected_successor` 停下，原因是 `current_position_not_proven`；每次失敗還重新計重試次數而不是共用預算，造成約 2.4 分鐘一次的活鎖（[PROJECT.md 十月十二日段末](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/PROJECT.md#L1552)）。它只在「單一當前位置標記加剛好一個未走候選」成立時才規劃下一節點，且節點身份至今標為未證實（[design.md L199-L231](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L199-L231)）。相較 AALC 用 YOLO／權重表尋路，這是 MaaLimbus 最弱的一環。
- 困難 boss 需要 clash／存活證據，「只靠勝率自動」沒有被驗證為困難通關策略（[design.md L326](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L326)）。它的 README 只宣稱「一次困難五層、領獎、換隊重入」有真機證據。
- 戰鬥 HUD：有些一般戰鬥沒有 WAVE，必須 TURN 加 Win Rate／Damage 兩個控制同時存在才認，缺了就拒絕，不能假設 1/1。回合動畫不是勝利。送出 START 後可以等最多 120 秒的不明戰鬥動畫，不再次送 START（bounded-exploration.md）。
- **開始鈕的圓盤要認「亮」的，不認「暗」的。** 回合尚未配置時盤面是暗的，按了無效；一次實跑對暗盤點了 7 次、回合數不動。按下勝率（Win Rate）自動配置後圓盤才點亮並出現 START。它改用形狀判定（面積、寬高比、填充率）取亮盤，並排除技能板上寬而淺的暖色干擾塊（[acceptance.md L436-L470](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/acceptance.md#L436-L470)）。該視窗 1103 個戰鬥幀中只有 2 幀讀得到 START 字樣，所以用圓盤形狀當後備是必要的。
- Android 控制器不能走 Windows 的 `P` 鍵戰鬥規劃；MaaLimbus 在 Android 上用 Win Rate 與 START 的觸控（design.md L232-L246）。這與 maalc 把戰鬥定為「`P` 加 `Enter`」的前提有出入，見 §5。

### 3.7 領獎與花費

- 「確認」是輸入，不是收據。付費領獎要同時有：獨立辨識的貨幣圖示（模板 0.95）、扣款符號、兩個數字裁切（0.9 且互相一致）、每週加成計數；任一缺失就拒絕。曾有一次把減號一併裁進數字，讀成 -5 而拒絕，結論是「修裁切範圍，不降門檻」（[design.md L63-L74](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L63-L74)）。
- 領獎動作的每個控制都持久化意圖，重啟後不能重複點。花費預算綁定明確範圍（run），換了 run 就回報預算待定。
- 隱藏的餘額視為未知，不推論；Net Amount 是算出來的，不是錢包（design.md L358-L370）。
- 付款頁辨識只針對保留過的英文 1920x1080 版面（5 模組零週、6 模組一週），其他版面視為未知。

### 3.8 商店、飾品、事件

- 飾品選擇與敵人強化分開評分；層級飾品需綁定「單一標題、Mounting Trials、敵人等級增加、可支援的數值效果」，缺任何一項就拒絕，不猜（[design.md L115-L166](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/docs/design.md#L115-L166)）。它用的權重是明講的啟發式（等級 30、攻擊 90、防禦 10…），不宣稱最佳解。
- 事件：只有精確的對話加兩個唯一高信心按鈕才處理；已知的 garden 事件固定選 Refuse；其他 Accept／Refuse 事件一律停下。工廠事件的簡短 Yes／No 才是選項，說明文字不是（design.md L168-L182）。
- 商店買入與刷新、技能替換在 2026-10-12 仍未接進主迴圈：實跑進商店什麼都沒買就離開。購買後的「E.G.O Gift GET!」通知要確認一次，但它是輸入錨點、不是收據；只有回到貨架後，金額差與該商品消失才算購買完成。

### 3.9 模擬器與控制器

- 驗收環境：MuMu 12，ADB `127.0.0.1:16416`；截圖空間固定 1920x1080（`display_long_side: 1920`、`set_screenshot_target_long_side(1920)`），`post_click` 吃的是此空間座標（handover §1）。
- 實測可用的輸入組合：`AdbShell|MinitouchAndAdbKey|Maatouch`；截圖用 `EmulatorExtras`（MuMu 自帶，acceptance.md L665 附近）。Maatouch／minitouch 的 helper 要隨附到 `MaaAgentBinary` 目錄，否則靜默退回 `adb shell input tap`（見 §3.1 第 6 點）。
- 它同時支援 Windows 原生客戶端。後台視窗訊息輸入是否被遊戲接受，必須用操作後頁面證明；遊戲 HIGH 權限、Maa MEDIUM 權限時輸入被擋、截圖失敗。這些與 maalc v1 無關（Win32 在範圍外）。
- 另有控制器租約（單一控制器鎖）與 `adb_preflight`：前景套件檢查先於任何輸入。

## 4. 值得採用

1. **一次一個輸入，先預期後驗證。** 每個頁面對應動作時附帶「預期後繼頁集合」，後繼不在集合就停下。這是它最核心也最便宜的安全網。maalc 的 Pipeline 可用 `next` 列表達同樣的事，並在 Agent 加上全域的「連續未預期」計數。
2. **意圖先持久化，再送輸入；重啟只看後繼不重送。** 對有副作用的動作（購買、領獎、啟動遊戲、確認進場）尤其重要，也是斷點接續能做對的前提。
3. **確認不等於成功。** 領獎、購買、輪替前進都要獨立的收據證據。把「點了」與「發生了」分成兩個狀態。
4. **禁點清單。** 保留 Halt／Give Up／Cancel／SKIP／每週重置 Confirm 等為錨點但禁作目標，由規劃層最後一關統一攔截，不要靠每個節點各自記得。
5. **用文字加正規化 ROI 辨識頁面，不用封面或背景。** 與 maalc 的「只做英文」「素材自製」相容，且抗賽季換封面。
6. **未知畫面：取證、有界探索、停下，不盲點。** 取證包含原始幀、雜湊與時間；探索只用獨立辨識到的導覽鍵，每個事件次數有上限。
7. **把輸入層與觀察層做成可注入介面（Device／Observer）**，用存檔幀加假裝置離線測迴圈。對 maalc 的驗收（連續 N 輪）特別有價值，因為真機驗收昂貴。
8. **控制器預檢**：啟動前確認 helper binary（Maatouch）存在，並把「靜默退回 shell tap」變成一行明確的日誌。
9. **隊伍輪替的帳本設計**：版本號、隊伍清單綁定、`active`／`receipts`／`abandoned`，位置只在收據後前進，不一致時拒絕覆蓋。
10. **契約測試**：Pipeline 引用的自訂 hook 必須都有註冊；anchors 的「已證實／待辦」不得重疊且需有證據。
11. **每個座標、門檻都標註來源幀。** maalc 的素材需自製，這個習慣可以直接移植成素材來源紀錄。
12. **小細節**：玩家隊伍格是 40 個不是 20；難度與人數計數用多個獨立 ROI 交叉確認；勝負頁面用多證據避免單一小字 OCR 失誤；亮暗圓盤用形狀而非單一顏色閾值。

## 5. 應避免

1. **別把 Pipeline 做成空殼加巨型 Python。** 792 節點中 95% 是 `DirectHit`、87% 是 `DoNothing`，辨識與決策全在 `window.py`／`recognition.py`。結果是 MaaFramework 的模板、OCR、ROI 管線與除錯工具（Pipeline 編輯器、節點回放）幾乎用不上，且 3.5 MB 的 interface.json 還超過自己的上限。maalc 應讓 Pipeline 承擔「畫面識別加單步動作」，Agent 只處理 Pipeline 表達不了的邏輯（尋路、配隊、評分）。
2. **別用生成的 700 個選項灌 interface.json。** 40 隊乘 12 格順序展開成數百個選項。maalc 應改為單一結構化設定，不用 PI 選項表達整張表。
3. **別讓每個畫面都有交易模組與持久化。** 它有約 90 個模組，每個小事件都有獨立交易與收據，開發日誌因此變成數百 KB 的流水帳，且大量功能「只有離線驗證」。maalc 只對**真正花資源或不可逆的動作**（領獎、購買、進場、輪替前進）做交易，其餘靠後驗證即可。
4. **別重現它的路徑缺口。** 它拒絕在節點身份未證實時規劃路線，最後活鎖在 floor 2。maalc 必須在規格階段就決定尋路方案（見 #8 的相依），不能延到最後。
5. **別假設隊伍格就是第 N 支隊。** 要對照名稱或預備戰鬥頁的資訊，否則會悄悄帶錯隊伍。
6. **別把「卡住」等同「停止」。** maalc 的目標含卡住時重啟遊戲，MaaLimbus 沒有這個設計可抄，它刻意不重啟。maalc 要自己設計重啟的觸發條件（連續 K 次未知、時間預算）、重啟後的重進流程，以及「重啟不算成功」的規則。
7. **別直接採它的戰鬥假設。** 它在 Android 以觸控按 Win Rate 與 START，並指出只靠勝率不能保證困難 boss 通關。maalc 規格寫「`P` 加 `Enter`」，那是鍵盤輸入；它的文件只說 Windows 的 `P` 鍵規劃在 Android 控制器上不執行，沒有驗證 Android 鍵碼能否觸發。maalc 需自行實測。
8. **別承襲它的授權包袱。** 它的 gift 圖示與目錄含 Lix 來源的 AGPL 素材，README 自承這點；maalc 不可碰這類資源（ADR 0001）。它的文件也大量引用 Lix／LALC 的值，使用前要確認只取事實。
9. **別把重點放在 Win32、GUI 打包、自動更新。** 這些佔了它大量篇幅，全在 maalc v1 範圍外。
10. **別照抄日誌式文件。** 逐小時的 continuation 紀錄不利接手；交接文件甚至要自己標「猜測都標了未核實」。maalc 用 ADR、規格、驗收清單即可。

## 6. 與 maalc v1 的對照

| maalc v1 項目 | MaaLimbus 的狀態 | 可借的想法 |
| --- | --- | --- |
| 普通／困難鏡牢五層 | 困難五層一次真機通過，之後路徑活鎖 | 轉場規則、禁點清單、領獎收據 |
| 配隊與隊伍輪替 | 40 格存檔隊、帳本輪替、曾帶錯隊 | 帳本結構、收據才前進、對照隊伍身份 |
| 戰鬥（`P` 加 `Enter`） | Android 用 Win Rate 與 START 觸控 | 亮暗圓盤判定、START 後有界等待 |
| 飾品／商店／合成 | 評分有，商店買入未接通 | 交易加「通知只是錨點」的規則 |
| 尋路 | 未解 | 反面教材，見 #8 |
| 斷點接續 | 帳本加意圖持久化 | 概念可完整借用 |
| 卡住時重啟 | 刻意不做 | 無可借，自行設計 |
| MuMu 12 | 真機證據齊全 | 1920x1080 截圖空間、helper binary 預檢 |

## 7. 未查證或不確定之處

- 沒有執行它的測試，也沒有實機；所有「實測」都是它自己日誌的聲稱。
- `PROJECT.md` 與 `acceptance.md` 太長，只讀了開頭、近期段落與以關鍵字檢索到的部分；較早期段落可能有本文遺漏的踩坑。
- 隨機延遲的具體區間只在日誌看到「180..480 ms」「480–680 ms」與幾個實測值，未在原始碼確認常數位置。
- 它的 JP 流程、日常任務、經驗本、紐本、Lux、Enkephalin 轉換都沒讀，也不在 maalc v1 範圍。
