# 02 畫面清單

本章列出 bot 會遇到的每一個畫面：用什麼辨識、看到後怎麼處理、之後可能出現哪些畫面。畫面依流程分組：導航與入口頁、開局、地圖、戰鬥、獎勵與事件、商店、困難模式與結算、全域彈窗，最後是誤觸才會進入的資訊面板。每個畫面都是 `MirrorHub` `next` 裡的一個 `[JumpBack]` 節點（入口頁之前的導航除外），處理完回到 hub 重新判斷（見 [01-architecture.md](01-architecture.md)）。決策的細節寫在 [03-decisions.md](03-decisions.md)，卡住與恢復寫在 [06-recovery.md](06-recovery.md)。（#8、#19）

## 總則

- 辨識方式依 #13 Q5 分工：文字與數字（標題、事件選項、主題包名稱、飾品名稱、Cost、HP、樓層、金錢、計數）用 OCR（`ppocr_v6/small`），比對時用 `expected` 對照資料檔；圖示、按鈕、畫面的固定標記用模板。模板門檻最低 0.8。（#13）
- 每個畫面節點必須設緊湊的 `roi`，盡量不做全畫面搜尋。具體的模板檔名、ROI、門檻在實作時決定。（#13、#19）
- 下表的「辨識方式」寫的是錨點：判定「現在在這個畫面」所用的標記。畫面中的其他資訊（例如計數、價格）在「處理」欄說明。
- 標題含有季名的畫面（例如 `Will you enter Mirror of Names and Spiders?`、`Grace of the Star of Names and Spiders`），錨點必須只用不隨季節改變的部分。這一季在 2026-10-15 結束。（#11）
- 所有輸入都用觸控；`P`／`Enter` 鍵盤在 Android 上不保證有效。（#2、#16）
- 「待截圖確認」表示這個畫面還沒有實機截圖，辨識方式是依 ticket 的描述暫定，截圖回來後要核對本章。已實機確認的畫面來自 2026-10-13 在 Limbus 1.116.2（MuMu 12，1280×720）上的一局普通鏡牢與一局困難鏡牢。（#7、#8、#19）
- 認不出畫面超過 60 秒（載入畫面 90 秒）、同一畫面連續處理 5 次，都交給卡住處理。（#14）
- 用 OCR 找文字再點的按鈕（`Skip`、`Continue`、`Proceed` 這類），每個畫面最多點 5 次。（#16、#19）

## 導航與入口頁

這一組是從遊戲啟動到鏡牢入口頁的導航，以及入口頁的分流。導航做成獨立的一串節點，不放進 `MirrorHub`。（#8）

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 標題畫面 | 模板：`Change Account`、`Clear all caches` 按鈕 | 點畫面中央進入遊戲 | 連線中（`CONNECTING`）、載入畫面、主畫面 | #2、#7 |
| 主畫面（Window 分頁） | 模板：底部分頁列（Window／Sinners／Drive／Theater／Extract／Dispense） | 點 Drive | Drive | #8 |
| Drive | 模板：`Mirror Dungeons` 入口按鈕 | 點 Mirror Dungeons | 鏡牢入口頁 | #8 |
| 鏡牢入口頁：Before Entry | OCR：`Exploring:` 欄位為 `Before Entry`；模板：右下 Enter 按鈕 | 讀 Weekly Bonuses 剩餘格數（全域難度「自動」與「每週獎勵用完就停」要用）；依輪替游標開新局，點 Enter | 進入確認對話框 | #8、#9 |
| 鏡牢入口頁：暫停中的局 | OCR：`Exploring:` 欄位為 `<季名> - F<N>`，下一行是 `<主題包> [NORMAL]` 或 `[HARD]` | 點 Enter 接續 | Resume 對話框 | #8 |
| 鏡牢入口頁：Exploration Complete | OCR：`Exploring:` 欄位為 `Exploration Complete`，卡片中央 `Unclaimed Rewards` | 點 Enter，依結算規則處理上局沒領的獎勵（[01](01-architecture.md#結算規則)） | Exploration Reward 視窗 | #8、#19 |
| 鏡牢入口頁：過期的局（待截圖確認） | 未知 | 依結算規則處理（[01](01-architecture.md#結算規則)） | 未知 | #8、#19 |
| 進入確認對話框 | OCR：`Will you enter`；模板：Cancel／Enter 按鈕 | 點 Enter | 選隊頁 | #8 |
| Resume 對話框 | OCR：標題 `Dungeon Progress`，按鈕 `Resume`、`Halt Exploration`、`Cancel` | 讀每層的難度與進度（例如 `Floor 1 [NORMAL] 0/6`）。接續時點 Resume；放棄這局時點 Halt Exploration | 地圖頁或這局停下時的畫面；放棄確認對話框 | #8、#14 |
| 放棄確認對話框 | OCR：`Forfeit previous exploration progress?` | 點 Confirm | Exploration Reward 視窗 | #8 |

入口頁上的 `Parallel Superposition Mode` 必須保持 OFF，bot 不點 `INFINITY MIRROR`。（#17）

## 開局

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 選隊頁 | OCR：左側 `TEAMS` 清單（`TEAMS #1`–`#40`）；模板：右下 Confirm | 選輪替游標指到的隊伍所設定的遊戲內隊伍欄位，點 Confirm（[03](03-decisions.md) 輪替） | 等級警告對話框、星光頁 | #8、#9 |
| 等級警告對話框 | OCR：`lower than the recommended level`、`Current Avg. Level`、`Recommended Level` | 點 Confirm 繼續 | 星光頁 | #8、#19 |
| 星光頁（Grace of Stars） | 模板：右側 `Select All Graces`、`Enter`；OCR：右上 `Owned` → `Available` → Cost 三個數字 | 依隊伍的星光方案逐張點 Grace 的等級（基礎／+／++），讀可用星光；買不起時依全域選項停止或跳過（[03](03-decisions.md) 星光）。完成後點 Enter | 星光確認對話框 | #8、#9 |
| 星光確認對話框 | OCR：標題 `Select Grace of Stars`、`Continue with selected effects?`；模板：`Convert Starlight to Cost` 勾選框 | 依星光方案切換 `Convert Starlight to Cost`，點 Confirm | 初始飾品頁 | #8、#9 |
| 初始飾品頁 | OCR：`Selected E.G.O Gift`、`Select 0/1`；模板：10 個體系櫃（Burn、Bleed …） | 點隊伍主要體系的櫃子，依序選滿 `Select n/m` 的可選數量，點 Select（[03](03-decisions.md) 初始飾品） | 飾品獲得視窗 | #9、#10、#19 |
| 初始飾品拒絕確認 | OCR：`Continue without selecting an E.G.O Gift?` | bot 不按 Refuse Gift；誤入時點 Cancel | 初始飾品頁 | #8 |
| 飾品獲得視窗 | OCR：`E.G.O Gift GET!`；模板：Confirm | 點 Confirm | E.G.O Gift Search 頁、主題包頁、地圖頁、商店 | #8 |
| E.G.O Gift Search 頁 | OCR：標題 `E.G.O Gift Search`、`Select 0/3`、右上 `Owned` 星光 | v1 一律點 Refuse Gift | 觀測拒絕確認 | #8、#19 |
| 觀測拒絕確認 | OCR：`Forgo E.G.O Gift Search?` | 點 Confirm | 主題包頁 | #8 |
| 主題包頁 | OCR：標題 `SELECT FLOOR <N> THEME PACK`、卡片標題列；模板：右上難度切換（`NORMAL ◀ ▶`／`◀ ▶ HARD`）、`Refresh` | 先讀難度並切到這一層該用的難度（遊戲會記住上一次的選擇，地圖頁不顯示難度）。依主題包方案挑主題包，必要時用 Refresh；把選中的卡片往下拉。Pack Search 不使用（[03](03-decisions.md) 難度、主題包） | 載入畫面、地圖頁 | #8、#9、#11 |

主題包頁出現的提示 `Unused Starlight have been added to the Clear Rewards.` 不需要處理。（#8）

## 地圖

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 地圖頁 | OCR：左上 `Exploring Floor <N>` 與主題包名稱、右上 Cost；模板：Bus、右上齒輪 | 進入新一層時重設地圖的重試額度。找 Bus，對相鄰一欄的固定格位做模板比對，用節點上的 Cost 交叉確認（Cost 相同的類型不交叉確認，事件用 `?` 圖示分辨），依權重點節點；失敗時走後備順序（[03](03-decisions.md) 尋路）。只有和 Bus 以亮線相連的節點能點，點不可走的節點沒有反應 | 節點選取面板 | #3、#8、#12、#14、#19 |
| 節點選取面板 | 模板：右側 `Enter` 按鈕；OCR：面板上的節點 Cost | 點 Enter。點空白處會關閉面板 | 戰前編隊頁、事件頁、商店、載入畫面 | #12 |
| 設定面板 Dungeon Progress | OCR：標題 `Dungeon Progress`、按鈕 `Progress`／`Forfeit`／`Continue`／`To Window`／`Config` | 讀每層難度與進度。L2 恢復時點 To Window；其他情況點 Continue 回地圖。面板上的 Parallel Superposition 開關不碰 | 暫停確認對話框、地圖頁、放棄確認（待截圖確認） | #8、#14、#17 |
| 暫停確認對話框 | OCR：標題 `Pause Exploration`、`Save your progress and return to the Main Menu?` | 點 Confirm | 主畫面（再經導航回入口頁 Resume） | #14 |
| 載入畫面 | OCR：`NOW LOADING`；模板：右下 `Combat Tips` | 等待，逾時 90 秒 | 地圖頁、戰鬥、戰前編隊頁 | #14 |

## 戰鬥

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 戰前編隊頁 | 模板：`Chain To Battle!`、`Clear Selection`；OCR：`Total Participants <n>/12` | 讀存活人數並記到進商店（治療用）；存活少於隊伍設定的 K 人就停止。讀卡片上的順序標記，和出戰順序方案不符就 Clear Selection，等計數歸零後依序點選，跳過陣亡的罪人，確認每點一次計數加一。點 Chain To Battle! | 載入畫面、戰鬥 | #9、#10、#16 |
| 戰鬥（等待輸入） | 模板：右下 `Win Rate` 按鈕；OCR：左上 `TURN <n>`、`WAVE <n>/<m>` | 點 Win Rate → 確認開始圓盤（`START`）亮起，最多試 2 次 → 點圓盤 → 3 秒內確認戰鬥動畫或暫停圖示出現。Win Rate 已經生效時再點會取消自動配卡，所以重點前必須先確認狀態。送出 3 次後回合數不變就交給卡住處理 | 戰鬥（演出中）、Victory、DEFEAT | #2、#16 |
| 戰鬥（演出中） | 模板：右上暫停圖示 | 等待；60 秒內什麼都認不出來就交給卡住處理，每場上限約 20 分鐘 | 戰鬥（等待輸入）、Victory、DEFEAT、戰鬥中對話 | #16 |
| 戰鬥中對話與事件（待截圖確認） | OCR：`Skip`、`Continue`、`Proceed` 文字；選擇題同事件頁 | 用 OCR 找到文字再點，每個畫面最多 5 次，不盲點畫面中央。選擇沿用事件的通用規則。前提是使用者關掉遊戲設定裡的戰鬥旁白等待 | 戰鬥 | #16 |
| 戰鬥暫停選單（待截圖確認） | OCR：`Resume` | 點 Resume | 戰鬥 | #16 |
| Victory | OCR：`VICTORY` 文字 | 看到 `VICTORY` 就算戰鬥結束；Confirm 有出現才點，之後交給 hub。不用 EX-CLEAR 標章判斷勝利。打贏後這場的重打計數歸零。實機上打贏後經過載入畫面直接回到地圖 | 載入畫面、獎勵卡頁、飾品選擇頁、地圖頁 | #16、#19 |
| DEFEAT 對話框（待截圖確認） | OCR：`Remaining Units: 0/12`；按鈕 `Return to Stage Select`、`Retry Stage`、`Accept results` | 同一場最多 Retry Stage N 次（預設 2）；用完依全域選項停止（預設）或放棄這局。只有放棄這局時才點 `Accept results`，之後依結算規則處理（[01](01-architecture.md#結算規則)） | 戰前編隊頁或戰鬥、停止、Exploration Reward 視窗（待截圖確認） | #16、#19 |

## 獎勵與事件

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 獎勵卡頁（待截圖確認） | 模板：5 種卡（Cost、Cost & Keyword Gift Chance、E.G.O Resource、Random E.G.O Gift、Starlight）；OCR：`Selectable <n>/<m>` | 依隊伍的獎勵卡順序選；比對不到任何類型就選第一張。按 Confirm 前讀 `Selectable n/m`，永遠不按 Cancel（[03](03-decisions.md) 獎勵卡） | 飾品獲得視窗、地圖頁 | #11 |
| 飾品選擇頁（戰後、事件、Boss 後；待截圖確認） | OCR：飾品名稱、`0/1` 或 `0/2` 計數；模板：體系圖示、`Owned` 標籤 | 依「主要體系 > 其他 > 已擁有」選，計數允許多選時依同一順序繼續選；沒有任何候選時選第一個（[03](03-decisions.md) 飾品） | 飾品獲得視窗、地圖頁 | #10 |
| 事件頁：選項（待截圖確認） | OCR：問題文字與選項文字 | 先查事件覆寫表（問題文字用模糊比對，依選項文字選）；沒有就用通用規則：「獲得主要體系 E.G.O」> 其他獲得 E.G.O 的選項 > 第一個選項（[03](03-decisions.md) 事件） | 技能判定頁、事件結果頁、飾品選擇頁、戰前編隊頁 | #11 |
| 事件頁：技能判定（待截圖確認） | OCR：罪人的成功率等級（Very High … Very Low） | 選等級最高的罪人，同等級選最左邊；讀不到就選第 1 位，不盲點 | 事件結果頁 | #11 |
| 事件頁：結果（待截圖確認） | OCR：`Continue`、`Proceed`、`Skip` 這類文字 | 點該文字 | 事件頁、飾品選擇頁、地圖頁、戰前編隊頁 | #11、#16 |

## 商店

商店流程是先治療，再循環「出售 → 購買與刷新 → 合成」，直到跑完一圈都沒有動作或跑滿 10 圈才離開。細節見 [03-decisions.md](03-decisions.md) 商店。（#10、#19）

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 商店主畫面（待截圖確認） | 模板：兩個刷新鈕、各格的體系圖示；OCR：各格價格、目前 Cost | 依循環處理，最多 10 圈：只買主要體系、點之前先讀價格、買完核對 Cost 有沒有正確扣掉。刷新以層計數，優先用定向刷新，錢不夠時改用普通刷新；所有花費都要保留預留金額 | 治療頁、出售畫面、合成畫面、定向刷新對話框、飾品獲得視窗、地圖頁 | #10 |
| 治療頁（待截圖確認） | 未定；需確認有沒有 HP、復活與單人治療選項 | 依隊伍的治療方式：不治療／錢 ≥ 100 + 預留時全體治療／有罪人陣亡時復活（預設）。復活也不得花到預留金額 | 商店主畫面 | #10 |
| 出售畫面（待截圖確認） | 模板：重複飾品標記（`Sale & Fusion-only`）；OCR：飾品名稱 | 只在想買的飾品買不起時出售；只賣無法湊滿 3 個的非主要體系飾品，以及 `Sale & Fusion-only` 的重複飾品 | 商店主畫面 | #10 |
| 合成畫面（待截圖確認） | 模板：體系選擇、結果預覽 | 非主要體系的飾品每 3 個合成一個，指定主要體系 | 飾品獲得視窗、商店主畫面 | #10 |
| 定向刷新對話框（待截圖確認） | 模板：體系選項 | 指定主要體系；條件是錢 ≥ 定向刷新費用 + 120 | 商店主畫面 | #10 |
| Super Shop（困難；待截圖確認） | 同商店主畫面，另加區分 Super Shop 的標記 | 和一般商店同一套流程；規則不依賴格數，每格都從畫面讀價格和體系 | 同商店主畫面 | #17 |

## 困難模式與結算

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| Boss 後的選擇與試煉（困難；待截圖確認） | OCR：選項上的飾品名稱、試煉名稱或等級（讀哪一個等截圖決定） | 每個選項評分 = 飾品分數 − 權重 × 試煉風險，查不到的試煉當最高風險（5）；取最高分，同分選風險較低者（[03](03-decisions.md) 困難模式） | 飾品獲得視窗、主題包頁 | #17 |
| Exploration Reward 視窗 | OCR：標題 `Exploration Reward`、`Weekly Bonuses <n>/3`、每層結果（例如 `Floor 1 [NORMAL] 0/6`）；模板：三個 ON／OFF 開關、`GiveUpRewards`／`To List`／`Claim` | 依結算規則（[01](01-architecture.md#結算規則)）：讀逐層結果，五層都是 `6/6` 才依每週獎勵設定（不用／普通／困難、每局一次或全用）把對應數量的開關切到 ON，數量和剩餘次數從畫面讀，再點 Claim；Claim 要花的腦啡肽模組不夠就停止並通知。沒達到目標就點 GiveUpRewards。Claim 完成後輪替游標前進 | 入口頁、結束確認（不領獎）、結算後的獎勵畫面（待截圖確認） | #8、#9、#17、#19、ADR 0003 |
| 結束確認（不領獎） | OCR：`End expedition without claiming rewards?` | 依結算規則放棄獎勵時點確認；其他情況誤入時點 Cancel | 入口頁（待截圖確認）、Exploration Reward 視窗 | #8、#19 |

輪替游標前進的理由見 [ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)。

## 全域彈窗

全域彈窗排在 hub `next` 的最前面，各子流程也引用同一組節點。（#8）

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 |
|---|---|---|---|---|
| 連線中 | OCR：`CONNECTING` | 等待 | 前一個畫面、Retry 彈窗 | #7、#8 |
| Retry 彈窗（待截圖確認） | OCR：`Retry` 按鈕文字 | 點 Retry | 連線中、前一個畫面 | #8 |
| 教學提示（待截圖確認） | 模板：關閉按鈕 | 關閉 | 前一個畫面 | #8 |
| 每週重置通知（待截圖確認） | OCR：通知文字 | 關閉，當成一般全域彈窗 | 前一個畫面、主畫面 | #8、#14 |
| 無限鏡牢彈窗（待截圖確認） | 模板：彈窗的關閉按鈕 | 關閉，不開啟無限鏡牢 | 前一個畫面 | #8、#17 |
| 升級彈窗（待截圖確認） | OCR：升級文字；模板：關閉或 Confirm | 關閉 | 前一個畫面 | #16 |
| 維護公告（待截圖確認） | OCR：公告文字 | 直接停止，保存證據並發 webhook | 停止 | #14 |

## 資訊面板（誤觸才會進入）

以下面板不在流程裡，是點錯位置時才會出現。看到時關閉並回到前一個畫面，屬於 L1 恢復（彈窗與返回）。（#14）

| 畫面 | 從哪裡進入 | 關閉方式 |
|---|---|---|
| 主題包詳情（`Effective Affinities`） | 主題包卡片上的放大鏡 | Confirm |
| Featured Theme Packs 清單 | 主題包頁或地圖頁右側按鈕 | Confirm |
| Active Effects（Trials／Grace of Stars／Choice Effects／Adversity 分頁） | 主題包頁或地圖頁右側 `?` | Confirm |
| 隊伍配置檢視（12 張人格卡） | 主題包頁或地圖頁右側罪人按鈕 | 返回 |
| E.G.O Gifts Owned／E.G.O Gifts（Owned、Clear Rewards、Current Theme Pack-Exclusive、Featured 分頁） | 主題包頁或地圖頁左上飾品欄 | Confirm |
| 教學頁（鏡牢說明、`Creating your Team`） | 地圖頁、入口頁、選隊頁、編隊頁的 `i` | 返回 |
| Progress（`Exploring` 進度頁） | Dungeon Progress 面板的 Progress | Close（直接回到地圖） |

## 未決

- **初始飾品頁的 `Activate Gift Search` 開關**：關掉後是否就不會出現 E.G.O Gift Search 頁，未確認。v1 的處理已定案為一律 Refuse Gift。（#8、#19）
- **Dungeon Progress 面板的 Forfeit**：從設定面板放棄時的確認畫面沒有截圖。（#8）
