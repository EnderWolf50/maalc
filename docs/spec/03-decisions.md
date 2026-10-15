# 03 決策規則

本章列出 Agent 在鏡牢中要做的每一種判斷：從畫面、使用者設定與遊戲資料檔讀進什麼，依什麼規則決定，預設值、上限與後備做法。流程如何在畫面之間切換見 [01-architecture.md](01-architecture.md) 與 [02-screens.md](02-screens.md)；設定的完整清單見 [04-settings.md](04-settings.md)；資料檔的格式見 [05-game-data.md](05-game-data.md)；卡住後的 L1/L2/L3 處理見 [06-recovery.md](06-recovery.md)。

所有判斷都以當下畫面為準。Agent 狀態檔只存輪替游標，其他數值每次都從畫面重新讀取（[ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)）。需要判斷的選擇寫成 Agent 的 custom action 或 custom recognition，畫面之間的流程留在 `MirrorHub`（[ADR 0002](../adr/0002-pipeline-hub-and-agent-decisions.md)）。

本章用「每隊」標示設定檔裡每支隊伍的欄位，用「全域」標示設定檔的執行選項（`run`），用「資料檔」標示遊戲資料（[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)、[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)）。

## 1. 選隊與輪替

**輸入**

| 來源 | 內容 | 層級 |
|---|---|---|
| 設定 | 隊伍是否啟用、遊戲內隊伍欄位（`TEAMS #1`–`#40`）、用途（都可／只跑困難／只跑普通） | 每隊 |
| 設定 | 難度（困難／普通／自動）、跑幾局、每週獎勵用完就停 | 全域 |
| 狀態檔 | 輪替游標 | Agent 狀態檔 |
| 畫面 | 入口頁的 Weekly Bonuses 剩餘次數；選隊頁與戰前編隊頁的 `TEAMS #N` | — |

**規則**

- 輪替：啟用的隊伍依設定裡隊伍清單的順序各跑一局，循環下去。（#9、#19）
- 開新局前先決定這一局的難度（見第 2 節），再從輪替游標開始往後找第一支用途符合的隊伍。用途不符的隊伍跳過，但游標不因跳過而前進。（#9）
- 繞完一圈都沒有用途符合的隊伍，就結束任務。（#9）
- 在選隊頁選出該隊的遊戲內隊伍欄位，確認畫面上的標題是 `TEAMS #N` 後再按確認。（#8、#9）
- 輪替游標只在 bot 親眼看到某隊完成一局並領到結算獎勵後才前進，前進到該隊的下一支啟用隊伍。手動跑的局不影響游標。（#8，[ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)）
- 選隊頁或戰前編隊頁顯示的隊伍和游標不同時，以畫面為準，照畫面上那支隊伍的設定繼續這一局。（#8）
- 接續暫停中的局時，設定面板與 Resume 對話框不顯示隊伍。Agent 必須等下一次戰前編隊讀到 `TEAMS #N` 才得知隊伍；整局都沒讀到，就不推進輪替游標。（#8、#19）
- 選隊確認後出現「隊伍平均等級低於建議等級」警告時，按 Confirm 繼續。（#8、#19）
- 任務開始時，Agent 必須檢查設定，例如同一個出戰順序裡同一位罪人被選兩次、隊伍引用的方案不存在，有錯就報錯停止。完整清單見 [04-settings.md](04-settings.md#2-寫入與檢查)。（#9、#19，[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)）

**停止條件**（#8）

- 「跑幾局」只計算這次啟動後 bot 達到目標並領到獎勵的局數（第 14 節），不存檔；達到就停止。
- 「每週獎勵用完就停」開啟時，開新局前讀入口頁的 Weekly Bonuses；三格全空就停止。
- 沒有任何用途符合的隊伍時停止（如上）。

## 2. 難度

**輸入**：全域難度（困難／普通／自動）；每隊的用途與第幾層起轉困難；入口頁的 Weekly Bonuses；主題包頁右上角的難度切換。（#9）

**規則**

- 全域難度決定這一局是困難局還是普通局，預設「自動」。自動 = 開局前讀入口頁的 Weekly Bonuses，還有剩就跑困難，用完就跑普通。（#9、#19）
- 第幾層起轉困難：每隊一個數字 N（0–5），預設 0。只在這一局是困難局時有效：N 表示第 N 層起用 HARD，之前的層用 NORMAL；0 表示整局用 HARD。普通局每層都用 NORMAL。（#9、#19）
- 只要有一層是 HARD，這一局就算困難局；每週獎勵與「自動」難度都照這個判斷。遊戲規定某一層進入困難後就不能切回普通，這條規則不會要求切回普通。（#9、#19）
- 難度是逐層在主題包頁設定的。遊戲會記住上一次選的難度，所以每一層進主題包頁時，Agent 必須先讀出目前的難度，和本層應有的難度不同就切換，確認切換成功後才選主題包。不得假設預設值。（#8）
- 地圖頁不顯示難度。接續暫停中的局時，從入口頁（`… [NORMAL]`）或設定面板、Resume 對話框的 `Dungeon Progress`（例如 `Floor 1 [NORMAL] 0/6`）讀出各層難度。（#8，[ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)）
- 任何一層選了 HARD 之後，之後各層都不能切回 NORMAL：下一層起主題包頁的難度箭頭變灰、點了沒反應。（#19，2026-10-14 定案；實機：captures/128_f2_tap_difficulty_left.png）
- 實機：第 1 層選主題包之前，HARD 與 NORMAL 可以來回切換；HARD 時點左箭頭（`◀ ▶ HARD`）切到 NORMAL，NORMAL 時點右箭頭（`NORMAL ◀ ▶`）切到 HARD。每次切換都會換一組主題包，切回原本的難度時換回原本那一組。（#25；2026-10-14 實機）
- 普通局到第 N 層（N > 1）才切到 HARD 是否可行，還沒有實測，見[未決](#未決)。

## 3. 出戰順序與戰前編隊

**輸入**：每隊的出戰順序（引用一個出戰順序方案，或該隊自訂）；戰前編隊頁上每張罪人卡片的順序標記、已選計數與存活人數（例如 `11/12`）。（#9、#16）

**規則**

- 出戰順序是點選罪人的順序，前 7 位上場。（#9）
- 遊戲沿用上一場的選擇，不會自動帶入隊伍的出戰順序。每場戰前必須讀卡片上的順序標記，和方案比對。（#9）
- 不符時按 Clear Selection，等計數歸零後依方案順序逐一點選，每點一次都確認計數加一。（#9）
- 有罪人陣亡時，照方案順序重選並跳過陣亡的罪人。（#16）
- 出戰順序可以只列部分罪人（例如小指良打法只列 Ryōshū）：沒列的罪人不上場，重選時一律不點，格子空著也不補。順序裡的罪人全部陣亡時停止。「存活少於 K 人」照樣算全部 12 位罪人的存活人數。（#52）
- 每次在戰前編隊頁讀出的存活人數要記在 Agent 記憶體，供商店的治療判斷使用（第 13 節）。（#10）
- 存活少於 K 人就停止：每隊一個數字，預設 0（不檢查）。有些隊伍需要罪人陣亡，所以預設不檢查。（#16）
- 實機：`Total Participants <n>/<m>` 的 `<m>` 就是存活人數（12 減陣亡人數）；陣亡者的卡片變灰、沒有順序標記，點了沒反應。順序 1–7 上場（`SELECTED`），之後最多 5 位是 `BACKUP`。（實機：captures/206_formation_with_dead_sinner.png、captures/207_formation_tap_dead_card.png、captures/49_formation_tap_unselected_card.png）
- 實機（1.117.0）：Clear Selection 會先問 `Reset Deployment Order?`，按 Confirm 後計數才歸零。存活的罪人都可以點選，12 人存活時 `Backup Deployed 5/5`。（#27；2026-10-15 實機）

## 4. 星光

**輸入**：每隊的星光（引用一個星光方案，或該隊自訂）；全域「買不起時」選項；星光頁上各加成的價格與剩餘星光。（#9）

10 個加成的名稱與價格見 [04-settings.md](04-settings.md#7-星光方案starlight_plans)。

**星光方案的內容**（#9）

| 欄位 | 內容 |
|---|---|
| 等級 | 10 個加成各自的等級：不買／基礎／+／++ |
| 購買優先順序 | 10 個加成排成一個順序，排在前面的先買（#19） |
| 剩餘星光換成 Cost | 是／否 |

**規則**

- 依購買優先順序，把每個加成買到方案指定的等級。（#9）
- 買不起某個加成時，依全域選項處理：停止整個任務（一張都不買，這局停在星光頁），或跳過這個加成繼續買下一個（預設跳過）。（#9、#19、#25）
- 方案要求換成 Cost 時，買完後把剩下的星光換成 Cost。（#9）
- 按 Enter 後若出現 `Continue with selected effects?`，按確認。（#8）
- 買不起由 Agent 自己用價格判斷：遊戲允許選超過 `Available` 的加成，差額會從持有的星光（`Owned`）扣。每點一張都要重讀 `Available`，出現 `0+N` 就取消這張並停止。點法與價格見 [04-settings.md](04-settings.md#7-星光方案starlight_plans)。（#25；2026-10-14 實機）

## 5. 初始飾品與 Gift Search

**輸入**：每隊的主要體系（10 選 1）。（#9）

**規則**

- 主要體系決定初始飾品的體系。在初始飾品頁選主要體系那一欄，依序選滿可選數量。（#9、#19）
- 觀測飾品（E.G.O Gift Search）v1 一律 Refuse，在確認彈窗按 Confirm。依體系觀測延後到 v1 之後（[00-overview.md](00-overview.md)）。（#8、#19）
- 初始飾品頁不按 Refuse；誤入它的確認彈窗時按 Cancel。（#8）

## 6. 主題包

**輸入**：每隊引用的主題包方案（資料檔的預設方案，或設定檔裡使用者的方案）；主題包頁卡片標題列的文字。（#11、#19，[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）

**規則**（#11）

- 辨識：OCR 每張卡片的標題列，和資料檔的主題包清單做模糊比對（門檻見 [05-game-data.md](05-game-data.md)）。標記為 NEW 或比對不到的主題包視為中立。
- 依主題包方案的標記選擇：偏好 > 中立 > 避開；同等級選最左邊。
- 只有畫面上全部是避開時才用免費刷新，可用次數全部用完（例如 `Refresh 4/4`）。刷新後畫面不變就視為用完；仍然全部是避開，就選最左邊的一個，絕不停在這頁。之後可加開關選擇用或不用、用一次或全用。（#11、#19、#25）
- 實機：卡片數量會變。買了 `Star of the Beginning` 與 `Interstellar Travel+`（各 `Theme Pack Selection +1`）時第 1 層有 5 張；`Interstellar Travel+` 讓刷新按鈕顯示 `Refresh 4/4`（`Theme Pack Refresh Chance +3`）。所以卡片位置從標題列的 OCR 結果取得，不用固定格位。（#25；2026-10-14 實機）
- 選主題包時要把卡片往下拉才能選定。（#8）
- 選主題包之前必須先依第 2 節設定好本層難度。（#8）
- 實機：免費刷新每層一次，用過按鈕就變灰。這一局沒有看到 NEW 標記；第 4 層的主題包左上有紅色 `!` 標記（推測是沒打過的主題包），標題照常可讀。第 5 層的主題包沒有 `CLEAR BONUS` 列。困難局打完 Boss 後直接進入下一層的主題包頁，中間沒有換層畫面。（實機：captures/129_f2_refresh_tapped.png、captures/197_f3boss_rewards_pack.png、captures/222_f4boss_rw_pack.png、captures/127_after_boss_gifts.png）

## 7. 地圖選路

**輸入**：地圖頁的 Bus 位置、相鄰格位的節點圖示（自製模板）；資料檔的節點權重。（#3、#12，[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）

**節點辨識**（#12）

- 先找 Bus，再對相鄰的固定格位做模板比對。
- 節點類型只看圖示模板。v1 不用 Cost 交叉確認；節點上的 Cost 只 OCR 下來寫進記錄。（#12、#19，2026-10-14 定案）

| 節點 | 普通 Cost | 困難 Cost | 權重（越低越優先） |
|---|---|---|---|
| 事件 | 75 | 100 | 1 |
| 普通戰鬥 | 75 | 85 | 2 |
| Focused | 100 | 120 | 4 |
| 異想體戰 | 150 | 180 | 5 |
| Risky | 120 | 150 | 6（困難模式 8） |
| 無法辨識 | — | — | 9 |

表上的 Cost 只供參考，不用於辨識。權重放在資料檔（[05-game-data.md](05-game-data.md)）。困難鏡牢實機看到的 Cost 列在 [05-game-data.md](05-game-data.md#6-cost-對照表與商店數字)。（#12、#19）

**路線**（#12）

- 只看相鄰一欄，選權重最低的節點。
- Boss 只在它是唯一可走的節點時才走。不特地找商店，每層 Boss 前一定有一家。
- 同權重時，選下一欄可走路線最多的節點；節點連線辨識不出來時，改成中間列優先，再來是上列。
- 每一步都重新辨識，不保存路線。
- 困難模式只看得到兩欄，權重相同，只把 Risky 改為 8，排在其他可辨識節點之後、無法辨識（9）之前。（#12、#19）
- 實機：只有和 Bus 以亮線相連的節點能進入，點其他節點（包括斜對角沒有連線的節點與還不能走的 Boss）沒有任何反應。商店節點的選取面板顯示的是下一個 Boss 的 Cost。（實機：captures/25_map_tap_unreachable_node.png、captures/65_event_node_selected.png、captures/75_map_tap_boss_unreachable.png、captures/76_shop_node_selected.png）
- 點節點 → 等 Enter → 點 Enter。之後出現什麼畫面由 `MirrorHub` 判斷，不依預期的節點類型分支；兩者不符時只記錄下來。（[ADR 0002](../adr/0002-pipeline-hub-and-agent-decisions.md)）

**辨識失敗時的後備順序**（#12）

1. 點 Bus。出現 Enter 代表目前所在的節點還沒進入（中途接續的情況），直接進入。
2. 依權重順序點相鄰的三格，無法辨識的放最後。每點一格等約 1.5 秒，看 Enter 是否出現。
3. 三格都沒反應，就拖曳地圖讓 Bus 回到中央一次，再重複第 2 步。
4. 仍然不行，交給卡住處理（[06-recovery.md](06-recovery.md)）。

**保護機制**（#12、#14）

- 每次進入地圖頁時給一份重試額度，任何子流程都不能把它歸零；只有進入新一層的地圖時才清除。
- 看門狗：一直看到同一張地圖畫面就累計次數，交給卡住偵測。
- 移動前不必先證明 Bus 的位置。

## 8. 戰鬥

**範圍**：戰鬥只按勝率加開始，不做技能配置與配卡決策；唯一的例外是開局連續防禦（見下）。（#1、#16、#52）

**規則**（#16）

- 只用觸控，每個動作都要確認結果。
  1. 點勝率 → 確認開始圓盤亮起，最多試 2 次。勝率按鈕的位置隨技能格數移動，圓盤亮起要用亮度判斷，見 [07-assets-and-testing.md](07-assets-and-testing.md#辨識方法的實機經驗)。
  2. 點圓盤 → 3 秒內確認出現戰鬥動畫或暫停圖示。
- 送出 3 次後回合數都沒變，或 60 秒內什麼都認不出來，交給 L1 → L2 → L3（[06-recovery.md](06-recovery.md)）。（#16、#19）
- 每場戰鬥上限約 20 分鐘，超過就直接走 L2。
- 勝利以 `VICTORY` 文字判斷，不用 EX-CLEAR 標章。看到 `VICTORY` 就算戰鬥結束；Confirm 有出現才按，之後的畫面交給 `MirrorHub`。實機：`VICTORY` 不需要輸入，之後是載入畫面（`Combat Tips`），再回到地圖；Focused、異想體戰與 Boss 之後先出現飾品選擇頁或獎勵卡頁。（#16、#19；實機：captures/63_battle_victory.png、captures/64_loading_combat_tips.png）
- 升級彈窗屬於全域彈窗。
- 前提：使用者必須在遊戲設定裡關掉戰鬥中的旁白等待。

**開局連續防禦**（小指良打法，#52）

- 隊伍設定「開局連續防禦回合數」N（0 = 不用，1–5）。每局最前面的 N 個戰鬥回合全員防禦，不按勝率；回合跨場累計，整局只用一次，用完照常按勝率。
- 做法：依序點每個技能格下方的罪人頭像，讓該格改用防禦技能，再確認開始圓盤亮起（只點頭像、沒按勝率時，圓盤只有在每一格都選好技能後才會亮）。技能格用頭像六角框頂端的橘色邊找，不用固定座標，因為格數會變。
- 設定防禦失敗（找不到技能格、點完圓盤沒亮）時，這回合改按勝率再開始，不扣回合數。只有回合真的開始了才扣一回合。
- 剩餘回合數只記在 Agent 記憶體，跟著這一局的計畫走。Agent 在一局中途重啟時無從得知已經用了幾回合，視為已經用完，之後照常按勝率（[ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)）。L1–L3 恢復（包括重開遊戲）不重啟 Agent，剩餘回合數保留。
- 暫不做「連結戰第一回合全員防禦」。

## 9. 全滅與陣亡

**全滅**（#16）

- 辨識：DEFEAT 對話框，顯示 `All participating Sinners have been killed.` 與 `Remaining Units: <n>/12`，選項有 `Return to Stage Select`、`Retry Stage`、`Accept results and return to Stage select`。實機：`<n>` 是沒上場的存活人數，不一定是 0；選項要先點選再按 Confirm。（實機：captures/236_finalboss_unknown.png）
- 按 `Retry Stage` 重打。同一場最多重打 N 次（全域，預設 2）。計數以每場遭遇戰為單位，打贏就歸零。
- 重打次數用完後依全域選項處理：停止（預設）或放棄這局。停止時保存證據。
- 只有重打次數用完、而全域選項為「放棄這局」時，才放棄這局：（#16、#19，2026-10-14 定案）
  1. 按 `Accept results`。它只保留陣亡結果，經載入畫面回到地圖，不會結束這局。
  2. 開設定面板（`Dungeon Progress`）→ 按 Forfeit → `Quit exploring the dungeon?` 按 Confirm。
  3. 依序經過 Defeat → Exploration Complete → Exploration Reward，再依第 14 節的結算規則處理。
- 其他情況不得按 `Accept results`，也不得按 Forfeit。
- 實機：`Retry Stage` 從第一波重打，出戰順序不變。`Accept results` 回到地圖時 Bus 停在同一個節點。（實機：captures/240_after_accept_results.png、captures/241_after_loading.png、captures/243_forfeit_dialog.png、captures/244_after_forfeit_confirm.png、captures/245_after_defeat_confirm.png）

**陣亡**（#16）

- 戰鬥中不放棄。下一場戰前依出戰順序重選，跳過陣亡的罪人（第 3 節）。
- 每隊的「存活少於 K 人就停止」預設 0（不檢查）。設定說明必須提醒：需要罪人陣亡的隊伍，商店治療應設為「不治療」。

## 10. 戰鬥中的事件、地圖事件

**輸入**：事件頁的問題文字、選項文字、技能判定的成功率等級；資料檔的事件覆寫表；每隊的主要體系。（#11，[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）

**地圖事件**（#11）

- 先查事件覆寫表：格式是「問題文字 → 選項文字」。問題文字用模糊比對，比對到就選表上指定文字的選項。表一開始是空的，依記錄逐步補充。（#11、#19）
- 沒列在表上的事件照通用規則：「獲得主要體系 E.G.O」> 其他獲得 E.G.O 的選項 > 第一個選項。
- 技能判定：選成功率等級最高的罪人（Very High > … > Very Low），同等級選最左邊；讀不到就選第 1 位，不盲點。
- 實機：選項下方的提示寫出判定與獎勵的體系，例如 `Lust & Pride Advantage check. Pass to gain a Keywordless E.G.O Gift.`；成功率等級顯示在每位罪人頭像上方。（實機：captures/133_event_skip1.png、captures/137_event_check_after_tap.png）
- 實作：選項的文字連同提示一起讀，提示寫 `<主要體系> E.G.O Gift` 的算「獲得主要體系 E.G.O」。問題文字取左側敘事框的文字。成功率等級逐一頭像讀：整列一起讀時相鄰的等級會黏在一起。（#28）

**戰鬥中的事件與對話**（#16）

- 暫停選單按 Resume。
- 戰鬥中出現的選擇沿用地圖事件的規則。實機：Boss 戰中途的劇情用的是事件頁，畫面上沒有地圖與戰鬥介面，罪人列只顯示上場的 7 人。（實機：captures/217_f4boss_rewards_stuck.png、captures/218_f4boss_ev_choices.png）
- Skip、Continue、Proceed 這類文字用 OCR 辨識後點擊，每個畫面最多 5 次；不盲點畫面中央。（#16、#19）
- 認不出來的畫面超過 60 秒，交給卡住處理（[06-recovery.md](06-recovery.md)）。（#16、#19）

## 11. 獎勵卡

**輸入**：每隊的 5 個獎勵卡優先順序下拉選單；獎勵卡頁的卡片類型與 `Selectable n/m`。（#11）

**規則**（#11）

- 基本卡只有 5 種：Cost、Cost & Keyword Gift Chance、E.G.O Resource、Random E.G.O Gift、Starlight，各有 I–VII 階。
- 依該隊的順序選卡。預設順序：Starlight → Random E.G.O Gift → Cost & Keyword Gift Chance → Cost → E.G.O Resource。
- 比對不到任何類型時選第一張。
- 實作：卡片類型由卡上說明的 OCR 文字判斷（`Starlight`、`Resource`、`Cost` 加 `Gift`／`chance`、`Cost`、`Gift`），不用圖示模板。（#28）
- 按 Confirm 前先讀 `Selectable n/m`，確認已選滿；永遠不按 Cancel。
- 張數：第 1、2 層每次 2 張，第 3 層起 3 張。普通最高到 V 階，困難最高到 VII 階。Special Catalogue、Tomorrow's Fortune、Star-shower、Binary Star-shop 會改變卡的效果，但不是新的卡種，仍依類型比對。
- 實機：困難局看到 1–4 張。第 1、2 層 2 張，第 3 層起 3 張；買了 `Special Catalogue`（`Number of Encounter Reward Card Choices +1`）後每次多 1 張。Focused 與異想體戰之後的順序是飾品選擇頁 → 飾品獲得視窗 → 獎勵卡頁；Boss 之後先出現獎勵卡頁。按 Cancel 會問 `Continue without choosing a reward?`。（實機：captures/115_boss_unknown.png、captures/176_f2boss_rewards_card.png、captures/197_f3boss_rewards_card.png、captures/157_after_focused.png、captures/158_reward_card_cancel.png）

## 12. 選飾品、Boss 後的選擇與試煉

**戰後與事件選飾品**（#10）

- 依「主要體系 > 其他 > 已擁有」挑選。
- 還能多選時（例如 `0/2`），依同樣順序繼續挑。
- 沒有任何候選（全部都已擁有或讀不出體系）時，選第一個。（#10、#19）
- 永遠不按 `Refuse Gift`。選不滿就按 Select 會問 `You have remaining E.G.O Gift choices.`，按 Confirm 會拿到等量的隨機試煉；誤入時按 Cancel。（#28；2026-10-15 實機）
- 實機：只有一張卡時，Select 上沒有計數。第 3 層的異想體戰節點標了飾品，打完卻沒有出現飾品選擇頁。（實機：captures/154_focused_unknown.png、captures/183_f3abno_map.png）
- 實作：主要體系以卡片說明的 OCR 文字判斷，說明裡出現主要體系的字（例如 `Burn`）就算；卡上的體系圖示太小，沒有做模板。已擁有以卡上的 `Owned` 文字判斷。（#28）

**Boss 後的選擇與試煉**（#17、#28）

- 遊戲 1.117.0 實機在普通局 Boss 後也看到這一頁（未見官方公告，待確認；程式碼兩種難度都處理，沒出現就不影響），選項一定附帶試煉；按 `Refuse Gift` 仍會拿到隨機試煉。所以兩種難度都照同一條規則評分：選項分數 = 飾品分數 − 權重 × 試煉風險。（#28；2026-10-15 實機）
  - 飾品分數：沿用選飾品的順序，主要體系 3、其他 2、已擁有 0。
  - 試煉風險：0–5。從選項上 OCR 讀出試煉名稱（例如 `Defense Level Up`、`Growth I`），查資料檔的試煉風險表（開發者每季更新）；查不到就當作最高風險 5。不用等級：每個試煉旁的 `Enemy Level Up +1`／`+2` 只有兩種值，分不出試煉。（#17；實機：captures/122_boss_gift_trials_page.png、captures/176_f2boss_rewards_gift.png）
  - 權重：每隊一個下拉選單（低／中／高），預設「高」；數值為低 0.5、中 1、高 2。
- 依分數取 `Select n/m` 的可選數量（困難 `Select 0/2`、普通 `Select 0/1`）；同分時選試煉風險較低的。（#17、#19，2026-10-14 定案；#28）
- 實機：困難頁面有 4 欄，每欄上半是飾品、下半是 `Mounting Trials`；計數是 `Select 0/2`，選一欄就同時拿到飾品和試煉。選完後每個飾品各彈一次飾品獲得視窗，然後直接進入下一層的主題包頁。普通頁面是 3 欄、`Select 0/1`，試煉例如 `Resilient I`、`Offense Level Up I`。（實機：captures/122_boss_gift_trials_page.png、captures/124_boss_gift_pick2.png、captures/127_after_boss_gifts.png；1.117.0 普通局 2026-10-15）
- 以上數值是初始值，等截圖確認後再調整。（#17、#19）

## 13. 商店

**輸入**：每隊的主要體系、刷新上限 N（預設 2）、治療方式、預留金額（預設 0）；商店畫面每格的價格與體系；目前的 Cost；戰前編隊頁記下的存活人數。（#10）

**流程**（#10、#17）

1. 先治療（依治療方式）。
2. 進入循環：出售 → 購買與刷新 → 合成。跑完一整圈都沒有任何動作就離開商店。
3. 循環最多跑 10 圈，避免卡住。（#10、#19）
4. 飾品升級 v1 不做；之後接在循環最後。

**治療**（每隊三選一，#10、#16）

| 方式 | 規則 |
|---|---|
| 不治療 | 不進治療頁 |
| 全體治療 | Cost ≥ 100 + 預留金額時全體治療 |
| 有罪人陣亡時才治療（預設） | 依戰前編隊頁記下的存活人數（例如 `11/12`），有人陣亡就用「復活」 |

每到新的一層，罪人會自動復活並回滿，所以商店治療只對本層的 Boss 戰有幫助。存活門檻 K > 0 的隊伍應設為「不治療」。實機：每層 Boss 打完後所有罪人 HP 全滿；層內的 HP 與 SP 會延續到下一個節點。（實機：captures/130_f2_map.png、captures/200_f4_map.png、captures/223_f5_map.png、captures/187_map_sinner_bar_damaged.png）

實機的治療頁有三個選項，各 100 Cost：單人大量治療（HP 50% + SP 45）、全體中量治療（HP 20% + SP 15）、復活一人。沒人陣亡時復活是灰的；復活要先點陣亡罪人的頭像才會出現 `Select`；復活後 HP 全滿、SP 為 0。商店的罪人列也直接顯示陣亡者（灰色、HP `0`）。（實機：captures/82_shop_heal_page.png、captures/191_heal_page_with_dead.png、captures/213_revive_selected.png、captures/194_revive_result.png）

預留金額適用於所有花費：治療、購買、刷新。任何花費後剩下的 Cost 都不得低於預留金額。（#10、#19）

**購買與刷新**（#10）

- 只買主要體系的飾品。點之前先讀價格，Cost 扣掉預留金額後夠才買；買完核對 Cost 是否正確扣除。
- 每家商店最多刷新 N 次（每隊）。刷新次數記在 Agent 記憶體，以層為單位，不存檔。
- 優先用定向刷新並指定主要體系，條件是 Cost ≥ 定向刷新費用 + 120（約一個 I 級飾品的價格）。
- 錢不夠定向刷新、但 Cost ≥ 普通刷新費用 + 120 時，改用普通刷新。（#10、#19）
- 刷新費用：普通刷新 15 起、每次 +15；定向刷新 90 起、每次 +15。兩者共用同一個次數計數。這些數字放在資料檔（[05-game-data.md](05-game-data.md)）。（#10、#19）
- 實機：普通刷新一次後，普通刷新變 30、定向刷新變 105，和上面的數字一致。買不起的格子標 `Not Enough Cost`。（實機：captures/107_shop_after_refresh.png）

**出售**（#10）

- 只在想買的主要體系飾品買不起時才出售。
- 只賣兩種：湊不滿 3 個、無法合成的非主要體系飾品；遊戲標記為 Sale & Fusion-only 的重複飾品。
- 主要體系的飾品永遠不賣。

**合成**（#10）

- 把非主要體系的飾品每 3 個合成一個，指定主要體系（成功率 90%）。
- 不動主要體系的飾品。
- 激進合成與固定配方合成延後到 v1 之後。（#1）

**實作**（#29）

- 飾品的體系沿用第 12 節的文字規則：購買看購買對話框的說明，出售看出售頁左側的說明，合成看點飾品後跳出的說明框。主要體系的字出現在說明裡就算主要體系。
- 預留金額加在門檻上：刷新的條件是 Cost ≥ 刷新費用 + 120 + 預留金額，全體治療是 Cost ≥ 100 + 預留金額，復活每人 100、復活後也不得低於預留金額。刷新費用從按鈕下方讀，不用資料檔的數字。
- 想買的主要體系飾品買不起時，先不刷新，下一圈先出售；出售過了仍然買不起才照常刷新。
- 出售的數量是非主要體系飾品數除以 3 的餘數（合成用不到的那些），從售價高的賣起，賣到買得起為止；全部賣掉也不夠就不賣。
- 合成時從合成頁目前看得到的 15 格依序點，主要體系的再點一次取消；湊滿 3 個才按 Fuse，確認對話框顯示 `3/5` 才確認。`Wishmaking` 已勾選時不合成。
- 治療的陣亡者以商店罪人列的灰色頭像為準；戰前編隊記下的存活人數只拿來核對，不一致時寫進記錄。
- 進行中的商店狀態（是否已治療、刷新次數、讀過的飾品體系）存在 Agent 記憶體，離開商店時清掉。Agent 重啟後會重新判斷治療。
- 尚未處理：Super Shop 10 格中要捲動才看得到的最後 2 格；合成頁超過 15 個飾品時的捲動；出售後若有確認對話框（還沒看過）。

實機觀察（1.117.0，2026-10-15，普通局第 5 層商店）：

- 買下的商品會移到格子的最後面並標 `Purchased`，其後的商品往前遞補，所以每買一個都要重讀格子。點 `Purchased` 的格子會開 `E.G.O Gift Info` 對話框，點對話框外面才會關。
- 購買對話框右上的 Cost 預覽（例如 `2864 ▶ 2612`）可以算出實際價格。
- 第 5 層的商店沒有 `Super Shop On Next Floor?` 欄。
- 合成頁一打開就顯示 `Select a Keyword.`，選好體系前不能放材料；這一家商店的材料格是 3 格（1.116.2 的 Super Shop 是 5 格）。點已放入的飾品會把它取出。排序有 `By Tier`、`By Keyword`、`Recent`。
- `Dark Vestige` 的說明是 `Counts as a Tier 1 E.G.O Gift. Can be sold at a Shop or be used as an ingredient for Fusion.`，沒有體系，算非主要體系。
- 全體治療花 100 Cost，結果頁按右下 Leave 回到商店主畫面。

**Super Shop**（困難模式，#17）

- 和一般商店用同一套流程：先治療，再循環「出售 → 購買與刷新 → 合成」。
- 規則不依賴格數，每格都從畫面讀出價格和體系。
- 合成仍然每 3 個一組；放 5 個合成屬於延後的激進合成。
- 實機：商店顯示 `Super Shop On Next Floor? <n>%`，這個機率隨本層花掉的 Cost 上升（3% → 8% → 15% → 24%），進過 Super Shop 後回到 3%。Super Shop 標題是紅色 `Super Shop`，10 格分兩列要捲動；其中 `ID Skill Search` 用星光計價，`Special Catalogue` 讓獎勵卡多一張。合成畫面的 `Wishmaking` 也花星光。只買主要體系飾品的規則已經排除這些商品。（實機：captures/77_after_enter_shop_node.png、captures/87_back_to_shop.png、captures/162_f2shop_entered.png、captures/163_supershop_scrolled.png、captures/94_shop_fuse_try2.png）

## 14. 結算與每週獎勵

**輸入**：全域每週獎勵選項（不用／用在普通／用在困難，預設「用在困難」）與用量（每局只用一次／一次全用，預設「一次全用」）；Exploration Reward 視窗上的 `Weekly Bonuses n/3` 與開關、這一局的結果（例如 `Floor 5 [HARD] 6/6`）。（#9、#17、#19）

**規則**

- 結算前必須先判斷這一局有沒有達到目標。目標是五層全部通過：Exploration Reward 視窗顯示 `Floor 5` 且進度是 `6/6` 才算達到。不看 Exploration Complete 摘要的逐層 `n/6`。（#8、#19，2026-10-14 定案）
- 達到目標時：
  - 這一局的難度符合「用在普通」或「用在困難」時才使用每週獎勵；選「不用」或難度不符時，所有開關保持 OFF。提供「不用」是因為有些玩家還沒開放困難鏡牢。困難局的判斷見第 2 節。（#9、#19）
  - 用量：每局只用一次 = 切 1 個開關到 ON；一次全用 = 把剩餘次數全部切到 ON。開關的數量和剩餘次數都從結算視窗讀。（#9、#17）
  - 切好開關後按 Claim。Claim 要花的腦啡肽模組不夠時，必須停止並通知（[06-recovery.md](06-recovery.md)）。（#8、#19）
- 沒達到目標時：按 GiveUpRewards 放棄獎勵，不花模組。（#19）
- 實機：視窗的三個按鈕是 `GiveUpRewards`、`To Window`、`Claim`，Claim 上標示花 5 個腦啡肽模組（`-5`）；bot 不按 To Window。視窗只顯示最後到達的那一層（例如 `Floor 5 [HARD] 5/6`，表示第 5 層沒打完，沒達到目標）。（實機：captures/252_exploration_reward_window.png、captures/245_after_defeat_confirm.png）
- 這條規則適用於：一般結算；入口頁顯示 `Unclaimed Rewards` 時補領上一局沒領的獎勵；每週重置後過期的局；全滅後重打次數用完、全域選項為「放棄這局」時從設定面板 Forfeit 之後的結算（第 9 節）。（#8、#16、#19）
- 看到 Claim 完成後，輪替游標才前進（第 1 節）。（#8）
- 實作（#30）：
  - 一局算不算困難局，看視窗上最後一層的 `[HARD]`／`[NORMAL]`：任何一層選了 HARD 就不能切回普通，所以最後一層就代表整局（第 2 節）。
  - 一次用 2 次以上的每週獎勵，要每一層都是 HARD（遊戲內說明頁，`captures/29_help_page_02.png`）。所以「一次全用」只在 bot 自己開的困難局、且「第幾層起轉困難」≤ 1 時才切多個開關，其他情況最多切 1 個。
  - 遊戲會預設切好開關（實機：普通局也預設第 1 個 ON），所以每個開關都要從畫面讀成 ON 或 OFF，把 ON 的數量調到剛好等於要用的數量，再讀一次確認；讀不出來或調不到就停止，不按 Claim。
  - 按 Claim 後視窗沒有關掉，而且不是「不使用每週獎勵確認」對話框，就停止、不再點任何東西（模組不夠時的畫面還沒見過，這樣不會誤點購買）。這局在 `runs.jsonl` 記為「停止」。
  - 輪替游標只在這局是 bot 自己在入口頁選的隊伍時才前進；接續或補領的局不前進（第 1 節）。
  - 「跑幾局」只算 bot 這次啟動後達到目標並領到獎勵的局；放棄獎勵（沒達到目標、放棄這局）與停止的局不算。達到時在入口頁停止，不開新局。（2026-10-16 定案）

## 未決

1. **普通局第 N 層才轉困難**：任何一層選 HARD 後不能切回 NORMAL 已確認（第 2 節）。普通局在第 2 層以後還能不能切到 HARD 沒有實測；不能的話，「第幾層起轉困難」欄位會移除。（#9、#19；實機：captures/128_f2_tap_difficulty_left.png）
2. **Risky 節點的圖示**：困難實機還沒看到 Risky 節點，它的圖示模板和 Focused 怎麼區分還不知道。（#12、#19）
