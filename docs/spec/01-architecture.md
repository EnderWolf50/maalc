# 01 架構

本章說明 `maalc` 的整體架構：`MirrorHub` 的結構、從主畫面到鏡牢入口頁的導航與入口頁的分流、Pipeline 與 Agent 的分工、中途接續與狀態檔、執行記錄 `runs.jsonl`、各畫面讀取的資訊，以及一局從頭到尾的流程。各畫面的細節見 [02-screens.md](02-screens.md)，決策規則見 [03-decisions.md](03-decisions.md)，卡住與恢復見 [06-recovery.md](06-recovery.md)。

## 分工：流程放 Pipeline，決策放 Agent

- 鏡牢的流程必須寫在 Pipeline。每種畫面的辨識必須各自寫在自己的 Pipeline 節點；不用單一 custom recognition 對全螢幕做分類。（#8）
- 需要判斷的選擇必須寫成 Agent 的 custom action 或 custom recognition，包括地圖節點、飾品、主題包、商店、星光、獎勵卡、事件選項、Boss 後的選擇、戰前的出戰順序。（#8、#9、#11、#17）
- 不採用把整局寫在程式碼迴圈裡的做法（MaaLimbus、AALC）。理由見 [ADR 0002](../adr/0002-pipeline-hub-and-agent-decisions.md)。（#8）
- 使用者設定由設定 GUI 寫進 `<root>/config/settings.json`，Agent 在任務開始時讀取並檢查；PI 不帶使用者選項（[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)）。格式見 [04-settings.md](04-settings.md)。（#6、#19，2026-10-14 定案）
- 遊戲資料（主題包清單與預設主題包方案、事件覆寫表、尋路權重、Cost 對照表與商店數字、試煉風險表）放在 `resource/base/data/` 的 YAML 資料檔，由 Agent 讀取（[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）。格式見 [05-game-data.md](05-game-data.md)。（#11、#12、#17、#19）

| 層 | 負責 | 不負責 |
|---|---|---|
| 設定 GUI | 編輯、檢查並寫入設定檔；重置某隊的時間記錄 | 執行 bot（第一階段） |
| Pipeline | 畫面辨識、畫面分派、固定的點擊序列、全域彈窗、導航、`max_hit` 與 `timeout` | 依設定或資料做選擇 |
| Agent | 依設定與資料做選擇、讀數字並核對結果、輪替游標、卡住偵測的計數、`runs.jsonl`、停止時的 webhook | 決定目前在哪個畫面 |

## MirrorHub

- `MirrorHub` 是鏡牢流程的分派節點。每種鏡牢畫面都必須列在它的 `next` 裡，並標上 `[JumpBack]`；每個畫面處理完就回到 hub，重新判斷畫面。（#8）
- `next` 的順序就是優先權。全域彈窗必須排在最前面（只有卡住偵測的 `Stuck` 節點排在它們之前，見 [06-recovery.md](06-recovery.md#實作31)），各子流程也引用同一組全域彈窗節點。（#8）
- 用 OCR 認的畫面不直接列在 `next`，而是依同樣的順序列在 `HubText` 裡：MaaFramework 會把同一個 `next` 清單裡的 OCR 合併成一次辨識，再把跨過 roi 邊緣的字框切成 1 px 細條重讀，戰鬥中一次就吃掉好幾 GB 記憶體。`HubText` 由 Agent 自己讀一次，只把可能的畫面排進它的清單，每個畫面再用自己的 OCR 確認；`next` 只剩 `Stuck`、`BattleHUD`（戰鬥畫面：回合或暫停鍵，伺服器彈窗仍先看）、`Connecting`、`HubText` 和幾個模板畫面。戰鬥中每輪都會先看的三個伺服器彈窗（`Connecting`、`RetryPopup`、`PopupButton`）都先比模板，模板沒中就不跑 OCR；`HubText` 只用 `And` 裡的 OCR 判讀，模板留給節點自己確認。（#157）
- 點下地圖節點之後出現什麼畫面，由 `MirrorHub` 依畫面判斷，不依預期的節點類型走分支；兩者不符時只記錄。（#12）
- 看到 `VICTORY` 就算戰鬥結束；Confirm 有出現才按，之後的畫面交給 `MirrorHub`。實機：`VICTORY` → 載入畫面（`Combat Tips`）→ 地圖頁；Focused、異想體戰與 Boss 之後先出現飾品選擇頁或獎勵卡頁。（#16、#19；實機：captures/63_battle_victory.png、captures/64_loading_combat_tips.png）
- `MirrorHub` 的 `timeout` 為 60 秒，逾時經 `on_error` 交給卡住處理；載入畫面另看畫面有沒有在動（不動 80 秒、最長 150 秒）。`on_error` 路徑裡 `[JumpBack]` 不生效，恢復後必須明確回到 `MirrorHub`。細節見 [06-recovery.md](06-recovery.md)。（#14）

### 全域彈窗

以下彈窗排在 hub `next` 的最前面：（#8、#14、#16）

| 彈窗 | 處理 | 來源 |
|---|---|---|
| Retry（連線失敗） | 按 Retry | #8 |
| 連線中 | 等待 | #8 |
| `i` 的說明頁（`HelpPager`） | 返回鍵關閉 | #8、#85 |
| 自己跳出的教學提示 | 待截圖確認（是不是同一種說明頁） | #8、#85 |
| 公告（`Notices`） | 返回鍵關閉 | #85 |
| 信箱（`Mailbox`） | 按 Close，不按 Claim All。例外：任務 `ClaimMail` 自己開信箱、按 Claim All，用的是它自己的節點（`mail.json`），全域的這一列不變 | #85、#372 |
| 設定選單（`SettingsMenu`） | 按 Return，不按 Quit Game | #85 |
| 每週重置通知 | 關閉 | #8、#14 |
| 無限鏡牢彈窗 | 不開啟無限鏡牢 | #8、#17 |
| 升級彈窗 | 關閉 | #16 |
| 維護公告 | 直接停止 | #14 |
| 標題畫面的資料下載對話框 | 按 Confirm，等下載完（卡住偵測暫停） | #86 |
| 單鈕彈窗（後備） | 畫面中央只有一個 Close／Confirm／OK 的彈窗，按它；有兩個按鈕的問句不按 | #85、#86 |

現狀（#85）：自己跳出的教學（`i` 打開的說明頁已做，自己跳出的還沒截到）、每週重置通知／舊局過期、升級彈窗（`Pass Level Up` 以外）還沒有專用節點，沒有截圖；`Recover` 在 `MirrorHub` 認不出畫面逾時時把畫面存到 `logs/unknown/`，下次遇到就有截圖可補。無限鏡牢彈窗（Cancel）已做，素材是遊戲說明頁裡的彈窗圖。

## 導航到鏡牢入口頁

- 從主畫面或其他畫面進入鏡牢入口頁的導航，必須另外做成一串節點，不放進 `MirrorHub`；做法仿照 MaaEnd 的 SceneManager。（#8）
- L2、L3 恢復之後也走這串導航回到入口頁。（#14）

### 回主畫面（`GoHome`）

- 日常任務的第一步和最後一步都走 `GoHome`（`navigation.json`），下一個任務因此一定從主畫面開始；PI 任務 `GoHome` 暫時用來單獨驗證。（#365）
- 一個 hub，依序處理：連線中、說明頁、全域彈窗（`HomeText`，讀法同 `HubText`，不進批次 OCR）、**到了主畫面**（Window 分頁亮起，`HomeReached`，任務成功結束）、標題畫面（`NavTitle`）、底部分頁列在但 Window 沒亮（點 Window 分頁，`HomeWindowTab`）、遊戲不在前景（`HomeGameAway`，`StartApp`，最多 3 次）、都不是就按返回鍵（`HomeBack`，最多 5 次）。
- 彈窗排在 `HomeReached` 前面：設定選單蓋著主畫面時 Window 分頁仍是亮的。其他分頁亮起、彈窗壓暗分頁列時，Window 模板的分數最多 0.80，門檻 0.9。
- 前景不是遊戲時直接啟動遊戲，不等 hub 逾時走 L3（`GameAway` 讀 `dumpsys window`，讀不到時不算）。
- 60 秒認不出畫面、或返回鍵用完仍沒到主畫面：走停止程序（存證據、webhook），任務失敗，client 的清單繼續；這個任務不結束整串清單。
- 日常任務的入口：入口節點（`TaskStart`）接 `GoHomeRun` 節點，它在 agent 裡用 `context.run_task("GoHome")` 跑完整個 `GoHome` 再接 hub（`[JumpBack]` 接 `GoHome` 做不到：`GoHome` 的結尾 `HomeReached` 沒有下一步，任務會在那裡結束）。結尾：動作做 `go_home()` 再 `done()`，hub 的 `TaskDone` 讓任務成功結束。`GoHome` 失敗時已自己走過停止程序，`GoHomeRun` 直接讓任務失敗。（#371）
- `ClaimMail`（`mail.json`）：`TaskStart` → `GoHomeRun` → hub：主畫面點右上信封（`MailOpen`）→ 信箱按 Claim All（`MailClaimAll`，最多 3 次）→ 再看到空信箱（`No mail in storage`，`MailEmpty`）就 `MailFinish`（`go_home()`，GoHome 的全域 `Mailbox` 按 Close 關信箱，再 `done`）。蓋在信箱上的彈窗先處理（`MailPopups`）。沒信時不按 Claim All，直接成功結束。Claim All 之後的確認／結果畫面還沒截到（unverified）。（#372）
- `ClaimPassMissions`（`pass_missions.json`）：主畫面的 Limbus Pass 橫幅（OCR 標題 `SEASON`）→ `Pass Missions` 分頁（模板，亮著時分數 0.92，門檻 0.97）→ Daily 分頁逐列點可領的列（`PassClaimable`，`agent/pass_missions.py`：金幣亮、沒有 CLEAR 章、進度條滿）→ Weekly 分頁同樣 → `PassFinish`（回主畫面、`done`）。沒有可領的就直接成功結束。可領那一列的畫面還沒截到，判斷是從已領、進行中兩種畫面推的（unverified）。
- 沒有鏡牢的卡住恢復階梯：日常頁只有返回鍵（L1）和重啟遊戲（L3）；L3 之後的接手還沒做（待實機看過再定）。

### 日常任務的骨架

開頭與結尾照上面「日常任務的入口」（`GoHomeRun`、`go_home()`、`TaskDone`，#371）。另外：（#366）

- **入口節點**的動作可以是 `TaskStart` 的子類別（例如 `ExpStart`：先 `TaskStart`，再讀這個任務的設定；設定不能用就走停止程序，不點任何東西），之後才接 `GoHomeRun`。
- **hub**：`next` 第一項是 `<任務>Stuck`（`StuckFlag` 加 `StopTask`：看門狗認定卡住就停止，日常頁還沒有恢復階梯），第二項是 `TaskDone`，其餘都標 `[JumpBack]`：伺服器彈窗與說明頁、OCR 畫面集中在自己的 `HubText` 子類別（不進批次 OCR，#157）、任務自己的畫面、最後是導航（`NavTitle`、`NavMainTabs` 這類）。`on_error` 接 `StopTask`：60 秒認不出畫面就停止，任務失敗，清單繼續。
- **記憶體**：任務自己的計數放 `RUN`（`TaskStart` 清空）；不放 `RUN["settings"]`，那是鏡牢一局的計畫，停止程序會依它寫 `runs.jsonl`。

### 經驗本（`ExpLuxcavation`）

- 從主畫面點 Drive（`NavMainTabs`）→ Luxcavation（`NavLuxcavation`）→ EXP 分頁（停在 Thread 分頁時點 EXP，`LuxExpTab`）→ EXP 分頁預設畫面最右邊的 Enter（`LuxExpEnter`，`ExpEnter`）。上鎖的卡顯示 KEEP OUT、沒有 Enter，所以最右邊的 Enter 就是最難的開放關卡。不改 Consecutive Battle、不按 Skip Battle。（#366）
- 分頁亮起看橘色邊框（ColorMatch）：亮和不亮的分頁對模板的分數差不多（0.93），分不開。
- 隊伍是 `luxcavation.exp.team` 指的 maalc 隊伍，戰鬥用它的 `guard_turns`（全員防禦 N 回合後按勝率，同鏡牢）。
- 開頭回主畫面後讀模組數，不夠 `count` 場就跳過（`ExpHome`）；按 Enter 之後回到 EXP 分頁，依這場的勝敗計次、再打或結束（`ExpEnter`，[spec 03 第 15 節](03-decisions.md)）。
- 現狀（#366）：按 Enter 之後的選隊、編隊、結算畫面沒有截圖，hub 不認得，60 秒後走停止程序（存證據）。這些畫面截到後再補選隊、編隊與勝敗判斷；模組檢查與計次（#367）已接上，戰敗訊號與戰敗重打待戰敗畫面的截圖。

### 紐本（`ThreadLuxcavation`）

照經驗本的做法：`ThreadStart`（`ExpStart` 的子類別，讀 `luxcavation.thread`）→ `GoHomeRun` → `ThreadHub`。`ExpStart`、`ExpHome`、`ExpEnter` 的計次、模組檢查與勝敗判斷共用（`battle_over`），只換任務名稱和每場的模組消耗；OCR 畫面共用 `ExpText`。（#368）

- 從主畫面點 Drive → Luxcavation（`NavLuxcavation`）→ Thread 分頁（停在 EXP 分頁時點 Thread，`LuxThreadTab`：Luxcavation 面板加上 EXP 分頁亮著）→ 今天唯一開放的異想體卡的 Enter（`LuxThreadEnter`，`ThreadEnter`）→ Level Select（`LuxThreadLevel`，`ThreadLevel`）→ 最下面那一列的 Enter。
- 開放的卡才有亮的 Enter 按鈕（對模板 1.0，其他天才開的卡最多 0.6）。清單從今天的卡開始排，所以進頁就看得到；但清單記得上次捲到哪裡，捲走後看不到亮的 Enter，這時往右滑（`LuxThreadSwipe`，`max_hit` 4）把左邊的卡帶進來。滑的方向沒實機驗證（unverified）。
- Level Select 一開啟清單就停在最底，最難的等級（Lust 是 Lv60）是最下面那一列；每級消耗 2 個模組（`luxcavation.THREAD_COST`），所以模組檢查是 2 × `count`。`ThreadLevel` 點畫面上最低的那個 Enter；按 Enter 本身不扣模組、不開戰。不改 Consecutive Battle、不按 Skip Battle。
- Level Select 之後接選隊頁：和經驗本同一個節點。目前這個節點（#366 的選隊頁）還沒合進整合分支，`ThreadHub` 先不列它；合併後它和 `ExpHub` 各加一行 `[JumpBack]ExpTeamSelect`。（#368）
- 打完一場回到 Thread 分頁（或停在 Level Select）就算一場：`battle_over` 依勝敗計次、再打或回主畫面結束。回到哪一頁沒實機驗證（unverified）。
- 隊伍是 `luxcavation.thread.team`。

### 入口頁的分流

入口頁讀取 `Exploring:` 欄位、Weekly Bonuses 與 `Unclaimed Rewards`，依畫面分流：（#8）

| 入口頁顯示 | 動作 | 來源 |
|---|---|---|
| `Exploring:` Before Entry | 開新局：依輪替游標選隊（見[一局的流程](#一局的流程)） | #8、#9 |
| 暫停中的局（例如 `… - F1` 與 `Automated Factory [NORMAL]`） | 按 Enter → Resume 對話框 → Resume，接續這局 | #8 |
| `Exploration Complete` 與 `Unclaimed Rewards` | 依[結算規則](#結算規則)處理上局沒領的獎勵，再開新局 | #8、#19 |
| 過期的局（每週重置後） | 依[結算規則](#結算規則)處理；畫面見[未決](#未決) | #8、#19 |

## 中途接續與狀態檔

- 中途接續必須以畫面為準，不讀存檔。理由見 [ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)。（#8）
- Agent 狀態檔只存**輪替游標**，記的是隊伍 id。（#8、#9、#19）
- 輪替游標只在 bot 親眼看到某隊完成一局並領到獎勵才前進。手動跑的局不影響輪替。選隊頁或戰前編隊頁顯示的隊伍和游標不同時，以畫面為準。（#8）
- 用途和這一局難度不符的隊伍跳過，但不推進游標；沒有任何可用的隊伍就以成功結束任務（#364）。（#9）
- 接續暫停中的局時，`Dungeon Progress` 不顯示隊伍。Agent 必須等下一次戰前編隊讀到 `TEAMS #N` 才得知隊伍；整局都沒讀到，就不推進輪替游標。（#8、#19）
- 「限制局數」只算這個任務開始後完成的局數，不存檔；清單裡第二個鏡牢任務從 0 局算起（#364）。「每週獎勵用完就停」的剩餘次數從畫面讀。（#8）
- 難度、每週獎勵用法這類策略屬於設定檔，不寫進狀態檔。（#8、#19）
- 刷新次數這類以層為單位的計數記在 Agent 記憶體，不存檔。（#10）
- 狀態檔必須放在 Agent 自己的子目錄 `<root>/state/`，避開 MXU 與 MFAAvalonia 的設定檔（`mxu-*.json`、`instances/`）；用暫存檔加改名的方式寫入；根目錄用 Agent 腳本自身的位置定位，不依賴工作目錄。（#6）

## 執行記錄 runs.jsonl

- Agent 必須為每局寫一行到 `<root>/logs/runs.jsonl`（`<root>` 是 Agent 的根目錄），欄位包括：起訖時間、隊伍 id、難度、有沒有用每週獎勵、通過幾層、結果（通關／停止／放棄）、L1／L2／L3 各觸發幾次。（#14）
- `runs.jsonl` 是唯讀的記錄，只用於驗收和計算每層時間上限，不得用於中途接續的判斷。時間上限每隊各自計算；設定 GUI 的「重置時間記錄」只附加一行該隊的重置標記，不刪舊記錄（[04-settings.md](04-settings.md#13-其他檔案)）。（#14、#19）

## 各畫面讀取的資訊

除了輪替游標，其餘狀態每次都從畫面重新讀取（2026-10-13 在 Limbus 1.116.2 確認）：（#8）

| 畫面 | 讀取 | 用途 | 來源 |
|---|---|---|---|
| 鏡牢入口頁 | `Exploring:`（Before Entry 或暫停中的局的層數、主題包、難度）、Weekly Bonuses 剩幾次、`Exploration Complete`／`Unclaimed Rewards` | 分流、自動難度、每週獎勵用完就停 | #8、#9 |
| 設定面板、Resume 對話框（`Dungeon Progress`） | 每一層的難度與進度，例如 `Floor 1 [NORMAL] 0/6`；不顯示隊伍 | 接續時得知各層難度 | #8 |
| 選隊頁 | 標題 `TEAMS #N` | 確認用的是哪個遊戲內隊伍欄位 | #8 |
| 主題包頁 | `SELECT FLOOR N THEME PACK`、右上角的本層難度（遊戲會記住上次的選擇） | 讀取並設定本層難度、挑主題包 | #8 |
| 地圖頁 | `Exploring Floor N`、主題包名稱、身上的飾品；不顯示難度 | 尋路、確認層數 | #8 |
| 戰前編隊頁 | 出戰順序標記、存活人數（`Total Participants <n>/<m>` 的 `<m>`，例如 `10/11` 表示 11 人存活） | 重選出戰順序、治療判斷、存活下限 | #9、#10、#16 |
| 結算視窗（Exploration Reward） | `Weekly Bonuses n/3` 與開關、最後到達的一層與進度（例如 `Floor 5 [HARD] 6/6`） | 判斷是否達到目標、依每週獎勵設定切開關 | #8、#9、#17 |

地圖頁不顯示難度，所以本層難度只能在主題包頁或 `Dungeon Progress` 讀取。（#8）

## 一局的流程

下面是一局從入口頁到領獎的順序。每一步都是 `MirrorHub` 分派到的一個畫面，處理完回到 hub；決策部分由 Agent 執行，規則見 [03-decisions.md](03-decisions.md)。

1. **入口頁**：依上面的分流表處理。開新局時，難度設為「自動」則讀 Weekly Bonuses，還有剩就跑困難，用完改普通。（#8、#9）
2. **選隊頁**：依輪替游標選出隊伍，點選它的遊戲內隊伍欄位（`TEAMS #N`）並確認。出現「隊伍平均等級低於建議等級」警告時按 Confirm 繼續。（#8、#9、#19）
3. **星光頁**：依隊伍的星光方案購買加成；方案要求時把剩下的星光換成 Cost。什麼都不選直接進入時，會再問 `Continue with selected effects?`。買不起時依全域選項停止或跳過（預設跳過）。（#8、#9、#19）
4. **初始飾品**：依隊伍有沒有要觀測的飾品切換 `Activate Gift Search`，再選隊伍主要體系那一欄，依序選滿可選數量。（#9、#19、#54）
5. **觀測飾品（E.G.O Gift Search）**：隊伍開啟觀測並選了飾品時，依清單順序選取、按 Select 並確認花費；否則 Refuse，在確認彈窗按 Confirm。（#8、#19、#54）
6. **每一層**（第 1–5 層）：
   1. **主題包頁**：讀取本層難度，依設定切換；再依隊伍的主題包方案挑主題包，卡片要往下拉才能選。（#8、#9、#11）
   2. **地圖頁**：依尋路規則選相鄰一欄的節點 → 等 Enter → 點 Enter。每次進入地圖頁時給一份重試額度，只在進入新一層的地圖時清除。（#12、#14）
   3. **節點內容**，由 `MirrorHub` 依畫面判斷：
      - **戰鬥**：戰前編隊依出戰順序方案重選，跳過陣亡的罪人 → 點勝率 → 點開始 → 看到 `VICTORY` 即結束（Confirm 有出現才按）→ 出現獎勵卡頁時依隊伍的獎勵卡順序選獎勵卡；有飾品可選時依飾品規則選。全滅時依重打次數處理。（#9、#10、#11、#16、#19）
      - **事件**：事件覆寫表有列出就照表，否則用通用規則。（#11）
      - **商店**：先治療，再循環「出售 → 購買與刷新 → 合成」，直到一整圈沒有動作或跑滿 10 圈。（#10、#19）
   4. **Boss**：Boss 只在它是唯一可走的節點時才走；每層 Boss 前一定有一家商店。（#12）
   5. **Boss 後選擇**：依「飾品分數 − 權重 × 試煉風險」評分，困難取前兩名（`Select 0/2`）；1.117.0 實機在普通局也看到這一頁（未見官方公告，待確認）（`Select 0/1`），規則相同（#28）。Super Shop 和一般商店同一套流程。（#17）實機：Boss 打完先出獎勵卡頁，再出 4 欄「飾品＋試煉」的選擇頁（`Select 0/2`），選完直接進入下一層的主題包頁，所有罪人 HP 回滿。（實機：captures/115_boss_unknown.png、captures/122_boss_gift_trials_page.png、captures/127_after_boss_gifts.png）
   6. 進入下一層，回到第 6.1 步。
7. **結算（Exploration Reward）**：依下面的[結算規則](#結算規則)處理。（#9、#17、#19）
8. **領到獎勵**：Claim 完成後，輪替游標前進到下一支隊伍，寫一行 `runs.jsonl`，回到入口頁開下一局。2026-10-15 實機：第 5 層 Boss 後依序是通關畫面（`Victory`）→ Exploration Complete 摘要 → Exploration Reward 視窗；Claim 後經載入畫面回到主畫面，再由導航回到入口頁。（#8、#14、#30）

任何一步卡住都交給 [06-recovery.md](06-recovery.md) 的卡住處理。（#14）

### 結算規則

結算前必須先判斷這一局有沒有達到目標。目標是五層全部通過：Exploration Reward 視窗顯示 `Floor 5` 且進度是 `n/n`（已通過數等於總數）才算達到。困難層的節點數不一定是 6：2026-10-16 實機第 5 層是 `Floor 5 [HARD] 7/7`（#67）。不看 Exploration Complete 摘要的逐層 `n/6`。（#8、#19，2026-10-14 定案）實機：Exploration Reward 視窗只顯示最後到達的一層（例如 `Floor 5 [HARD] 5/6`）。（實機：captures/252_exploration_reward_window.png）

- 達到目標：依每週獎勵設定把對應數量的開關切到 ON，再按 Claim。開關數量與剩餘次數從畫面讀。Claim 要花的腦啡肽模組不夠時，必須停止並通知（[06-recovery.md](06-recovery.md)）。（#9、#17、#19）
- 沒達到目標：按 GiveUpRewards 放棄獎勵，不花模組。（#19）
- 這條規則適用於一般結算、補領上局沒領的獎勵、每週重置後過期的局，以及全滅後重打次數用完、全域選項為「放棄這局」時，按 `Accept results` 回到地圖、再從設定面板 Forfeit 之後的結算（[03](03-decisions.md#9-全滅與陣亡)）。（#16、#19）

## 未決

- **過期的局的畫面**：每週重置後過期的局在入口頁長什麼樣，還沒有截圖；處理方式已依[結算規則](#結算規則)定案。（#8、#19）
