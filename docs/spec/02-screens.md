# 02 畫面清單

本章列出 bot 會遇到的每一個畫面：用什麼辨識、看到後怎麼處理、之後可能出現哪些畫面。畫面依流程分組：導航與入口頁、開局、地圖、戰鬥、獎勵與事件、商店、困難模式與結算、全域彈窗，最後是誤觸才會進入的資訊面板。每個畫面都是 `MirrorHub` `next` 裡的一個 `[JumpBack]` 節點（入口頁之前的導航除外），處理完回到 hub 重新判斷（見 [01-architecture.md](01-architecture.md)）。決策的細節寫在 [03-decisions.md](03-decisions.md)，卡住與恢復寫在 [06-recovery.md](06-recovery.md)。（#8、#19）

## 總則

- 辨識方式依 #13 Q5 分工：文字與數字（標題、事件選項、主題包名稱、飾品名稱、Cost、HP、樓層、金錢、計數）用 OCR（`ppocr_v6/small`），比對時用 `expected` 對照資料檔；圖示、按鈕、畫面的固定標記用模板。模板門檻最低 0.8。（#13）
- 每個畫面節點必須設緊湊的 `roi`，盡量不做全畫面搜尋。具體的模板檔名、ROI、門檻在實作時決定。（#13、#19）
- 下表的「辨識方式」寫的是錨點：判定「現在在這個畫面」所用的標記。畫面中的其他資訊（例如計數、價格）在「處理」欄說明。
- 標題含有季名的畫面（例如 `Will you enter Mirror of Names and Spiders?`、`Grace of the Star of Names and Spiders`），錨點必須只用不隨季節改變的部分。這一季在 2026-10-15 結束。（#11）
- 所有輸入都用觸控；`P`／`Enter` 鍵盤在 Android 上不保證有效。（#2、#16）
- 「待截圖確認」表示這個畫面還沒有實機截圖，辨識方式是依 ticket 的描述暫定，截圖回來後要核對本章。已實機確認的畫面來自 2026-10-13 在 Limbus 1.116.2（MuMu 12，1280×720）上的一局普通鏡牢與一局困難鏡牢。（#7、#8、#19）
- 「實機截圖」欄列出困難鏡牢那一局的代表截圖，以檔名列出（例如 `captures/176_f2boss_rewards_card.png`），逐張說明見 [captures-2026-10-13.md](captures-2026-10-13.md)。截圖本身只留在本機，尚未遮掉 UID 與帳號名稱；實作時依 #13 遮蔽、壓縮後搬進 `tests/`（[07](07-assets-and-testing.md#測試截圖的存放與授權)）。「—」表示這一局沒有截到。（#13）
- 截圖中的座標與數值只是實測參考，不是規則；辨識方法的實機經驗見 [07](07-assets-and-testing.md#辨識方法的實機經驗)。
- 認不出畫面超過 60 秒（載入畫面不動 80 秒或超過 150 秒）、同一畫面連續處理 5 次，都交給卡住處理。（#14）
- 用 OCR 找文字再點的按鈕（`Skip`、`Continue`、`Proceed` 這類），每個畫面最多點 5 次。（#16、#19）

## 導航與入口頁

這一組是從遊戲啟動到鏡牢入口頁的導航，以及入口頁的分流。導航做成獨立的一串節點，不放進 `MirrorHub`。（#8）

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 標題畫面 | 模板：`Change Account`、`Clear all caches` 按鈕 | 點畫面中央進入遊戲 | 連線中（`CONNECTING`）、載入畫面、主畫面 | #2、#7 | — |
| 主畫面（Window 分頁） | 模板：底部分頁列（Window／Sinners／Drive／Theater／Extract／Dispense） | 點 Drive | Drive | #8 | `captures/255_final_window.png` |
| Drive | 模板：`Mirror Dungeons` 入口按鈕 | 點 Mirror Dungeons | 鏡牢入口頁 | #8 | — |
| 鏡牢入口頁：Before Entry | OCR：`Exploring:` 欄位為 `Before Entry`；模板：右下 Enter 按鈕。旁邊另有 `Rental` 按鈕，不要點（#24 實機） | 讀 Weekly Bonuses 剩餘格數（全域難度「自動」與「每週獎勵用完就停」要用）；依輪替游標開新局，點 Enter | 進入確認對話框 | #8、#9 | `captures/00_md_enter_dialog.png`（對話框背後） |
| 鏡牢入口頁：暫停中的局 | OCR：`Exploring:` 欄位為 `<季名> - F<N>`，下一行是 `<主題包> [NORMAL]` 或 `[HARD]`；還沒選主題包就暫停時是 `-`（#24 實機） | 點 Enter 接續 | Resume 對話框 | #8 | — |
| 鏡牢入口頁：Exploration Complete | OCR：`Exploring:` 欄位為 `Exploration Complete`，卡片中央 `Unclaimed Rewards` | 點 Enter，依結算規則處理上局沒領的獎勵（[01](01-architecture.md#結算規則)） | Exploration Reward 視窗 | #8、#19 | — |
| 鏡牢入口頁：過期的局（待截圖確認） | 未知 | 依結算規則處理（[01](01-architecture.md#結算規則)） | 未知 | #8、#19 | — |
| 進入確認對話框 | OCR：`Will you enter`；模板：Cancel／Enter 按鈕 | 點 Enter | 選隊頁 | #8 | `captures/00_md_enter_dialog.png` |
| Resume 對話框 | OCR：標題 `Dungeon Progress`，按鈕 `Resume`、`Halt Exploration`、`Cancel` | 讀每層的難度與進度（例如 `Floor 1 [NORMAL] 0/6`）。接續時點 Resume；放棄這局時點 Halt Exploration。實機：三個按鈕由上而下排在對話框中央（Resume 約 y 398），背後入口頁的 `Exploring:` 仍讀得到（#31） | 地圖頁或這局停下時的畫面；放棄確認對話框 | #8、#14 | `tests/screens/ResumeDialog.png` |
| 放棄確認對話框 | OCR：`Forfeit previous exploration progress?` | 點 Confirm | Exploration Reward 視窗 | #8 | — |

入口頁上的 `Parallel Superposition Mode` 必須保持 OFF。bot 在入口頁讀 `Parallel Superposition Mode : ON`／`OFF`（遊戲文字 `EN_MirrorDungeonUI_5_InfinityFloor` 的 `InfinityFloor_Mode_Button_Title` 加 `IsOnInfinityMod`／`IsOFFInfinityMod`），讀到 ON 就點下方的 `INFINITY MIRROR` 關掉，讀回 OFF 才繼續；點兩次仍是 ON 就停止（`ParallelModeOn` → `ParallelModeOff`，排在入口頁各分流之前、入口頁的對話框之後）。開關開著時只會在通過第 5 層後跳提示（`ParallelModePrompt`，點 Cancel），作為第二道保險。（#17、#94，2026-10-18 定案）

實作（#94）：ON 的畫面還沒有實機截圖，`tests/screens/EntryParallelOn.png` 是把 `EntryNewRun.png` 的 OFF 改畫成 ON 的合成圖；點 `INFINITY MIRROR` 會直接切換還是先跳確認，也還沒實機看過（跳出別的畫面時讀不回 OFF，會停止，不會亂點）。

## 開局

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 選隊頁 | OCR：左側 `TEAMS` 清單（`TEAMS #1`–`#40`）；模板：右下 Confirm | 選輪替游標指到的隊伍所設定的遊戲內隊伍欄位，點 Confirm（[03](03-decisions.md) 輪替）。清單一次只顯示約 7 欄（完整的 6 欄，列距 36.4 px），要捲動才看得到後面的欄位；`#40` 是最後一欄。實機 2026-10-18（#113）：每次捲 140 px，選 `#15`、`#30`、`#40`、`#22`、`#5` 都讀到正確標題，最多捲 8 次。右下的 `Starlight Bonus` 是這支隊伍可用的星光 | 等級警告對話框、星光頁 | #8、#9 | `captures/01_team_picker.png` |
| 等級警告對話框 | OCR：`lower than the recommended level`、`Current Avg. Level`、`Recommended Level` | 點 Confirm 繼續 | 星光頁 | #8、#19 | `captures/02_after_team_confirm.png` |
| 星光頁（Grace of Stars） | 模板：右側 `Select All Graces`、`Enter`；OCR：右上 `Owned` → `Available` → Cost 三個數字 | 依隊伍的星光方案逐張點 Grace 的等級，讀可用星光（`Available`，等於選隊頁的 `Starlight Bonus`，不是 `Owned`）；買不起時依全域選項停止或跳過（[03](03-decisions.md) 星光）。完成後點 Enter。10 張卡排成兩列，每張卡右上是基礎價格，底部是 `+`、`++` 兩個按鈕；右側另有 `Enhance All` 的 `+`／`++`，bot 不用。名稱與等級的對應見 [04](04-settings.md#6-星光方案6-組) | 星光確認對話框 | #8、#9 | `captures/03_starlight_page.png` |
| 星光確認對話框 | OCR：標題 `Select Grace of Stars`、`Continue with selected effects?`；模板：`Convert Starlight to Cost` 勾選框 | 依星光方案切換 `Convert Starlight to Cost`，點 Confirm。不勾選時，沒用掉的星光會加進這局的結算獎勵（對話框文字 `Any unspent Starlight will be added to your Dungeon clear rewards.`） | 初始飾品頁 | #8、#9 | `captures/04_starlight_confirm.png` |
| 初始飾品頁 | OCR：`Selected E.G.O Gift` 加上右上的 `Activate Gift Search` 開關（E.G.O Gift Search 頁也有同樣的 `Selected E.G.O Gift`，只有這頁有開關；它淡入時曾被認成這頁，#166）、`Select 0/1`；模板：10 個體系櫃（Burn、Bleed …） | 點隊伍主要體系的櫃子，右側面板會列出這個櫃子的 3 個飾品；點飾品，依序選滿 `Select n/m` 的可選數量，點 Select（[03](03-decisions.md) 初始飾品）。畫面一次只顯示 8 個櫃子，最後兩個（Pierce、Blunt）要往下捲才看得到。右上的 `Activate Gift Search` 開關（OCR 讀 `ON`／`OFF`，點 (1140, 158) 切換）：隊伍開啟觀測並選了飾品時切到 ON，否則切到 OFF；讀不到就不碰（[03](03-decisions.md) 第 5 節）。實機觀察 (2026-10-16)：OFF 時選完初始飾品直接到主題包頁，不出現 E.G.O Gift Search 頁；同一次遊戲執行中，下一局沿用上一局的開關，重啟模擬器後又是 ON。實機：買了 `Star-shower` 時是 `Select 0/2`；選滿後第一次點 Select 常沒反應，要確認畫面換掉，沒換就再點（#25） | 飾品獲得視窗 | #9、#10、#19 | `captures/05_initial_ego_gift.png`、`06_initial_gift_bleed_selected.png`、`07_initial_gift_picked.png` |
| 初始飾品拒絕確認 | OCR：`Continue without selecting an E.G.O Gift?` | bot 不按 Refuse Gift；誤入時點 Cancel | 初始飾品頁 | #8 | — |
| 飾品獲得視窗 | OCR：`E.G.O Gift GET!`；模板：Confirm | 點 Confirm。一次拿到多個飾品時，每個飾品各彈一次 | E.G.O Gift Search 頁、主題包頁、地圖頁、商店、飾品選擇頁、獎勵卡頁 | #8 | `captures/08_after_select.png`、`126_boss_gift2_get.png` |
| E.G.O Gift Search 頁 | OCR：標題 `E.G.O Gift Search`、`Select 0/3`、右上 `Owned` 星光（`1315 -70 ▶ 1245`）、右側 `Selected E.G.O Gift` 清單的飾品名；顏色：每格飾品左上的黃色等級條 | 隊伍開啟觀測並選了飾品時依清單選取後點 Select；否則點 Refuse Gift（[03](03-decisions.md) 第 5 節）。這頁花的是持有的星光。版面見下方「E.G.O Gift Search 頁的版面」 | 觀測確認、觀測拒絕確認 | #8、#19、#54 | `captures/09_gift_search_page.png`、`tests/screens/GiftSearchSelected.png`、`GiftSearchFadeIn.png`（淡入中，`StartingGift` 不能中） |
| 觀測確認 | OCR：`Consume 70 Starlight to search and obtain these E.G.O Gifts?` | 點 Confirm（765, 495）；Cancel 在（513, 495）。之後每個飾品各彈一次飾品獲得視窗 | 飾品獲得視窗 | #54 | `tests/screens/GiftSearchConfirm.png`、`GiftSearchGet.png` |
| 觀測拒絕確認 | OCR：`Forgo E.G.O Gift Search?` | 點 Confirm | 主題包頁 | #8 | `captures/10_gift_search_refuse_dialog.png` |
| 主題包頁 | OCR：標題 `SELECT FLOOR <N> THEME PACK`、卡片標題列；模板：右上難度切換（`NORMAL ◀ ▶`／`◀ ▶ HARD`）、`Refresh` | 先讀難度並切到這一層該用的難度（遊戲會記住上一次的選擇，地圖頁不顯示難度）。依主題包方案挑主題包，必要時用 Refresh；把選中的卡片往下拉。Pack Search 不使用（[03](03-decisions.md) 難度、主題包）。實機：任何一層切到 HARD 後，下一層起難度箭頭變灰、點了沒反應；Refresh 每層免費一次，用過就變灰。卡片上可能有 `EFFECTIVE` 標章、危險標記、紅色 `!` 標記（第 4 層的三個主題包都有，點了沒反應）；沒看到 NEW 標記。第 5 層沒有 `CLEAR BONUS` 列 | 載入畫面、地圖頁 | #8、#9、#11 | `captures/11_theme_pack_floor1.png`、`12_theme_pack_toggle_hard.png`、`128_f2_tap_difficulty_left.png`、`129_f2_refresh_tapped.png`、`197_f3boss_rewards_pack.png`、`222_f4boss_rw_pack.png` |

主題包頁出現的提示 `Unused Starlight have been added to the Clear Rewards.` 不需要處理。（#8）

### E.G.O Gift Search 頁的版面

以下都是實機觀察 (2026-10-16)，1.117.0、1280×720。（#54）

- 上方 11 個體系分頁，由左到右 `Burn`、`Bleed`、`Tremor`、`Rupture`、`Sinking`、`Poise`、`Charge`、`Slash`、`Pierce`、`Blunt`、`Keywordless`，中心 x = 113 + 62 × 序號、y = 190。兩次進頁都停在 `Bleed`（初始飾品選的也是 Bleed），Agent 不依賴它，每次先點分頁。
- 分頁下方是飾品格，每列 8 格（中心 x 約 130 + 83.4 × 欄），列距約 80 px，依等級分成 III、II、I 三段，每段開頭一條標題列。觀測頁沒有 IV 級。一次看得到約 4 列，分頁內容較多時（`Keywordless` 有 78 個）要往上拖才看得到下面。遊戲的觀測表列了 320 個，這個帳號的頁面少了 5 個（`Pinpoint Logic Circuit`、`Spicebush Branch`、`Kaleidoscope`、`Baekja Water Dropper`、`Out-of-style Rouge Clothing`），原因未確認，可能是還沒解鎖；Agent 找不到就跳過。
- 切換分頁會把捲動重設到頂端。手指放開時若還在移動，格子會繼續滑（慣性）：1 秒的 swipe 實際捲動是手指距離的 1.36–1.40 倍；手指停住 0.5 秒再放開就不滑（捲動手勢見 [07](07-assets-and-testing.md#辨識方法的實機經驗)）。拖過分頁的頭尾，放開後格子會彈回。（#56）
- 段標題列是橫跨格子的藍色帶（高 24–25 px，B − R 約 50），左端是該段等級的 1–3 條黃色數字（高 14 px，在藍色帶頂端下方 5 px）；被格子上緣切掉一部分的標題列不算。（#56，實機觀察 (2026-10-16)）
- 位置：頂端時第一段標題列 y 約 252，標題到該段第一列、該段最後一列到下一段標題都是 61 px，列距 78.7 px（`agent/gift_search.py` 的 `expected_cell`）。
- 飾品格只有圖示、沒有名字。圖示和遊戲資源裡的 `Sprite/EgoGiftIcon/<iconId>` 相同，縮成 0.21 倍（約 50 px）後可用模板比對；淺色圖示分數 0.9 以上，深色圖示（例如 `Rusted Clock Hands`）只有 0.7 左右，和相似圖示（`Etched Clock Hands`）分不太開，所以點下去後還要讀名字確認。每格左上有 1–3 條黃色等級條（高 19 px，段標題的數字只有 14 px）。這局已持有的飾品灰掉並標 `Owned`，沒有等級條，點了沒反應；已選取的格子加橘框，黃條也讀不到。
- 點一格就選取，右側 `Selected E.G.O Gift` 清單依選取順序列出名字與效果（每項名字一行，y 約 205、316、427）；再點同一格，或點清單裡那一項，就取消。選滿 `Select n/m` 後再點別格沒反應。
- 價格只看選了幾個，和等級無關：1 個 70、2 個 160、3 個 270 星光（遊戲靜態資料的觀測表也是這三個數字）。右上 `Owned` 顯示「持有 −本次價格 ▶ 剩下」。
- 按 Select 後跳出 `Consume N Starlight to search and obtain these E.G.O Gifts?`，Confirm 之後每個飾品各彈一次 `E.G.O Gift GET!`，再到主題包頁。
- 星光到結算才真正扣：這局的結算獎勵列出 `Starlight -70`；放棄獎勵（GiveUpRewards）後回入口頁，持有星光仍是觀測前的數字。
- 遊戲重啟後以 Resume 接續，會回到這一頁，之前的選取已清空。

## 地圖

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 地圖頁 | 模板：右上齒輪與右側的圖示欄、Bus；OCR：左上 `Exploring Floor <N>` 與主題包名稱、右上 Cost | 進入新一層時重設地圖的重試額度。找 Bus，對相鄰一欄的固定格位做模板比對，戰鬥節點的種類看 Cost 數字＋難度，標記作退路（[03](03-decisions.md) 第 7 節，#91），依權重點節點；失敗時走後備順序（[03](03-decisions.md) 尋路）。只有和 Bus 以亮線相連的節點能點，點其他節點沒有任何反應。實機：左上的 `Exploring Floor` 標題會被節點蓋住，所以錨點不能只靠它；困難模式約看得到前方兩欄，地圖可自由拖曳；節點與連線的樣式隨主題包改變。底部罪人列顯示每人 HP 數字與 SP，陣亡者頭像變灰、HP 為 `0` | 節點選取面板 | #3、#8、#12、#14、#19 | `captures/24_map_f1_settled.png`、`25_map_tap_unreachable_node.png`、`65_event_node_selected.png`、`200_f4_map.png`、`202_f4ev_stuck.png`、`189_map_dead_sinner.png` |
| 節點選取面板 | 模板：右側 `Enter` 按鈕；OCR：面板上的節點 Cost（只寫進記錄） | 點 Enter。點空白處會關閉面板。實機：事件節點的面板只有主題包名稱與 Enter，沒有 Cost；商店節點的面板顯示的是下一個 Boss 的獎勵與 Cost，不是商店本身的。選取節點時底部罪人列的第 7–12 位會變暗 | 戰前編隊頁、事件頁、商店、載入畫面 | #12 | `captures/26_map_node_selected.png`、`131_f2_event_selected.png`、`76_shop_node_selected.png`、`152_focused_node_selected.png` |
| 設定面板 Dungeon Progress | OCR：標題 `Dungeon Progress`、按鈕 `Progress`／`Forfeit`／`Continue`／`To Window`／`Config` | 讀每層難度與進度。L2 恢復時點 To Window；放棄這局時點 Forfeit；其他情況點 Continue 回地圖。面板上的 Parallel Superposition 開關不碰。實機：地圖頁按 Android 返回鍵也會打開這個面板（2026-10-16，#31） | 暫停確認對話框、地圖頁、放棄探索確認對話框、Progress 頁 | #8、#14、#17、#19 | `captures/31_gear_dungeon_progress.png`、`242_gear_before_forfeit.png` |
| 暫停確認對話框 | OCR：標題 `Pause Exploration`、`Save your progress and return to the Main Menu?` | 點 Confirm | 主畫面（再經導航回入口頁 Resume） | #14 | `tests/screens/PauseExploration.png` |
| 放棄探索確認對話框 | OCR：標題 `Pause Exploration`、`Quit exploring the dungeon?` | 標題和暫停確認對話框相同，必須用內文區分。這是從設定面板按 Forfeit 後出現的對話框；按 Confirm 會結束這一局。全滅後重打次數用完、全域選項為「放棄這局」時點 Confirm（[03](03-decisions.md#9-全滅與陣亡)）；其他情況點 Cancel | Defeat 畫面 → Exploration Complete → Exploration Reward 視窗（Confirm）、地圖頁（Cancel） | #8、#16、#19 | `captures/243_forfeit_dialog.png` |
| 載入畫面 | OCR：`NOW LOADING`；OCR：右側中段 `Combat Tips`（#24 實機：不在右下） | 等待，畫面不動 80 秒或超過 150 秒算卡住（#179） | 地圖頁、戰鬥、戰前編隊頁 | #14 | `captures/64_loading_combat_tips.png`、`240_after_accept_results.png` |

## 戰鬥

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 戰前編隊頁 | 模板：`Chain To Battle!`、`Clear Selection`；OCR：`Total Participants <n>/<m>` | 讀存活人數並記到進商店（治療用）；存活少於隊伍設定的 K 人時照「重打用完後」處理：停止，或按左上返回鍵回地圖後放棄這局（#137）。讀卡片上的順序標記，和出戰順序方案不符就 Clear Selection，等計數歸零後依序點選，跳過陣亡的罪人，確認每點一次計數加一。點 Chain To Battle!。實機：`<m>` 是存活人數（12 減陣亡人數，例如 `10/11`）；順序 1–7 標 `SELECTED` 上場，之後最多 5 位標 `BACKUP`（`Backup Deployed <n>/5`）；陣亡者的卡片變灰、沒有順序標記，點了沒反應；上一場的選擇會沿用 | 載入畫面、戰鬥 | #9、#10、#16 | `captures/43_after_enter_node.png`、`50_formation_collapse_details.png`、`206_formation_with_dead_sinner.png`、`207_formation_tap_dead_card.png` |
| 戰鬥（等待輸入） | 模板：右下 `Win Rate` 按鈕；OCR：左上 `TURN <n>`、`WAVE <n>/<m>` | 圓盤（`START`）沒亮就點一次 Win Rate → 點圓盤（讀成未亮也照點，#69） → 3 秒內確認戰鬥動畫或暫停圖示出現。Win Rate 已經生效時再點會取消自動配卡，所以重點前必須先確認狀態。送出 3 次後回合數不變就交給卡住處理。實機：Win Rate 按鈕的位置隨技能格數左右移動，圓盤固定在它左下方；圓盤亮不亮要用亮度判斷，不能用 `START` 字樣（見 [07](07-assets-and-testing.md#辨識方法的實機經驗)）。回合開場動畫還在播時點 Win Rate 可能沒有效果。部分戰鬥開場左上先顯示 `ENEMY <n>/<m>`，之後才是 `WAVE` | 戰鬥（演出中）、Victory、DEFEAT | #2、#16 | `captures/52_battle_turn1_ui.png`、`53_battle_winrate_pressed.png`、`56_battle_wait.png`、`182_abno_winrate_tap.png` |
| 戰鬥（演出中） | 模板：右上暫停圖示 | 等待；60 秒內什麼都認不出來就交給卡住處理，每場上限約 20 分鐘 | 戰鬥（等待輸入）、Victory、DEFEAT、戰鬥中對話 | #16 | `captures/54_battle_start_pressed.png`、`55_battle_midturn.png` |
| 戰鬥中對話與事件 | 同事件頁（左側敘事面板加右下紅色按鈕、右側 `Choices`），畫面上沒有地圖與戰鬥介面 | 用 OCR 找到文字再點，每個畫面最多 5 次，不盲點畫面中央。選擇沿用事件的通用規則。前提是使用者關掉遊戲設定裡的戰鬥旁白等待。實機：Boss 戰中途會切到這個畫面，罪人列只顯示上場的 7 人；點敘事框推進文字時可能點到戰場上的單位，開出人格詳情面板。戰鬥畫面上方的角色台詞橫幅不需要處理 | 戰鬥 | #16 | `captures/217_f4boss_rewards_stuck.png`、`218_f4boss_ev_choices.png`、`73_after_battle4.png` |
| 戰鬥暫停選單（待截圖確認） | OCR：`Resume` | 點 Resume | 戰鬥 | #16 | — |
| Victory | OCR：`VICTORY` 文字 | 看到 `VICTORY` 就算戰鬥結束；Confirm 有出現才點，之後交給 hub。不用 EX-CLEAR 標章判斷勝利。打贏後這場的重打計數歸零。實機：`VICTORY` 不需要輸入，接著是載入畫面（`Combat Tips`），然後回地圖；Focused、異想體戰與 Boss 之後先出現飾品選擇頁或獎勵卡頁 | 載入畫面、獎勵卡頁、飾品選擇頁、地圖頁 | #16、#19 | `captures/63_battle_victory.png`、`64_loading_combat_tips.png` |
| DEFEAT 對話框 | OCR：`All participating Sinners have been killed.`、`Remaining Units: <n>/12`；選項 `Return to Stage Select`、`Retry Stage`、`Accept results and return to Stage select` | 同一場最多 Retry Stage N 次（預設 2）；用完依全域選項放棄這局（預設）或停止。只有放棄這局時才點 `Accept results`，回到地圖後從設定面板按 Forfeit 結束這局，再依結算規則處理（[03](03-decisions.md#9-全滅與陣亡)、[01](01-architecture.md#結算規則)）。實機：`<n>` 是沒上場的存活人數，不一定是 0；三個選項是可選的卡片，先點選項再點 Confirm。`Retry Stage` 從第一波重打，出戰順序不變；`Accept results` 保留陣亡結果，經載入畫面回到地圖（Bus 停在同一個節點），不會進入結算 | 戰鬥（Retry）、戰前編隊頁（Return，待截圖確認）、載入畫面 → 地圖頁（Accept） | #16、#19 | `captures/236_finalboss_unknown.png`、`238_defeat_opt_retry_selected.png`、`239_defeat_opt_accept_selected.png`、`241_after_loading.png` |

## 獎勵與事件

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 獎勵卡頁 | OCR：標題 `Select Encounter Reward Card`、`Selectable <n>/<m>`；模板：5 種卡（Cost、Cost & Keyword Gift Chance、E.G.O Resource、Random E.G.O Gift、Starlight） | 依隊伍的獎勵卡順序選；比對不到任何類型就選第一張。按 Confirm 前讀 `Selectable n/m`，永遠不按 Cancel（[03](03-decisions.md) 獎勵卡）。實機：卡片置中排列，1–4 張；卡上文字例如 `Gain 100~150 Cost`、`Gain a random Tier 1~2 E.G.O Gift`、`E.G.O Resource +8 for 2 of the least-owned Affinities`、`Gain additional 8~10 Starlight upon clearing the Mirror Dungeon` | 飾品選擇頁、Boss 後的選擇與試煉、地圖頁、獎勵卡放棄確認 | #11 | `captures/115_boss_unknown.png`、`176_f2boss_rewards_card.png`、`197_f3boss_rewards_card.png`、`230_f5abno_rewards_card.png` |
| 獎勵卡放棄確認 | OCR：`Continue without choosing a reward?` | bot 不按 Cancel；誤入時點這個對話框的 Cancel 回到獎勵卡頁 | 獎勵卡頁 | #11 | `captures/158_reward_card_cancel.png` |
| 飾品剩餘選擇確認 | OCR：`You have remaining E.G.O Gift choices.` | bot 不按 Refuse Gift，也不在選滿前按 Select；誤入時點 Cancel。按 Confirm 會拿到等量的隨機試煉 | 飾品選擇頁、Boss 後的選擇與試煉 | #28 | — |
| 飾品選擇頁（戰後、事件） | OCR：飾品名稱、`Select <n>/<m>`；模板：卡片上的 `Acquire E.G.O Gift` 標籤、`Refuse Gift`、體系圖示、`Owned` 標籤 | 依「主要體系 > 其他 > 已擁有」選，計數允許多選時依同一順序繼續選；沒有任何候選時選第一個（[03](03-decisions.md) 飾品）。實機：只有一張卡時置中顯示，Select 上沒有計數，點卡片前 Select 是灰的 | 飾品獲得視窗 | #10 | `captures/154_focused_unknown.png`、`155_gift_acquire_selected.png` |
| 事件頁：敘事 | 模板：左側敘事面板、右下紅色按鈕；OCR：按鈕文字（`SKIP`、`Proceed`、`Continue`、`Commence`） | 點該文字。這幾個按鈕都在右下同一個位置，沒有作用時變灰；敘事中途要點敘事框推進文字 | 事件頁：選項、事件頁：技能判定、地圖頁、飾品獲得視窗 | #11、#16 | `captures/132_event_entered.png`、`142_event_after_skip.png`、`146_event_continue.png` |
| 事件頁：選項 | OCR：右側 `Choices` 面板的問題文字與選項文字 | 先查事件覆寫表（問題文字用模糊比對，依選項文字選）；沒有就用通用規則：「獲得主要體系 E.G.O」> 其他獲得 E.G.O 的選項 > 第一個選項（[03](03-decisions.md) 事件）。實機：選項下方的提示寫出判定與獎勵，例如 `Lust & Pride Advantage check. Pass to gain a Keywordless E.G.O Gift.`；選項多時面板會出現捲軸 | 事件頁：結果、事件頁：技能判定 | #11 | `captures/133_event_skip1.png`、`149_ev2_choices.png` |
| 事件頁：技能判定 | OCR：`Choose a character to perform the check with:`、`Threshold`；每位罪人頭像上方的成功率等級（Very High … Very Low） | 選等級最高的罪人，同等級選最左邊；讀不到就選第 1 位，不盲點。選好後點 `Commence` | 事件頁：結果 | #11 | `captures/137_event_check_after_tap.png`、`139_event_check_sinner_selected.png`、`141_event_check_result.png` |
| 事件頁：結果 | OCR：`Result` 標題、`Check Passed` 這類文字、`Continue`／`Proceed`／`SKIP` | 點該文字。獲得的飾品會先在結果面板顯示，回地圖後再彈飾品獲得視窗 | 事件頁、飾品獲得視窗、地圖頁、戰前編隊頁 | #11、#16 | `captures/134_event_choice1.png`、`143_event_next.png` |

## 商店

商店流程是先治療，再循環「出售 → 購買與刷新 → 合成」，直到跑完一圈都沒有動作或跑滿 10 圈才離開。細節見 [03-decisions.md](03-decisions.md) 商店。（#10、#19）

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 商店主畫面 | 模板：`Refresh`、`Keyword Refresh` 兩個刷新鈕、左側 `Enhance Gifts`／`Fuse Gifts`／`Sell Gifts`／`Heal Sinner`／`Team`、右下 `Leave`；OCR：各格價格與名稱、目前 Cost、`Super Shop On Next Floor? <n>%` | 依循環處理，最多 10 圈：只買主要體系、點之前先讀價格、買完核對 Cost 有沒有正確扣掉。刷新以層計數，優先用定向刷新，錢不夠時改用普通刷新；所有花費都要保留預留金額。實機：每列 4 格；刷新費用顯示在按鈕下方；買不起的格子標 `Not Enough Cost`，買過的標 `Purchased`（1.117.0 實機：買過的會移到最後一格）；除了飾品還有 `Replace <罪人>'s Skill` 這類非飾品商品 | 治療頁、出售畫面、合成畫面、定向刷新對話框、購買確認、離開確認 | #10 | `captures/77_after_enter_shop_node.png`、`107_shop_after_refresh.png`、`209_f4shop_entered.png` |
| 購買確認 | OCR：標題 `Purchase E.G.O Gifts`、Cost 的扣款預覽；模板：Cancel／Purchase | 點 Purchase | 飾品獲得視窗 | #10 | `captures/78_shop_item_tap.png` |
| 飾品資訊（`E.G.O Gift Info`） | OCR：標題 `E.G.O Gift Info` | 點 `Purchased` 的格子才會出現；點對話框外面關閉（#29 實機，1.117.0） | 商店主畫面 | #29 | — |
| 治療頁 | OCR：標題 `Heal Sinners`；三個選項 `Greatly heal a single Sinner`（HP 50% + SP 45）、`Moderately heal every Sinner`（HP 20% + SP 15）、`Revive a single Sinner`，各 100 Cost | 依隊伍的治療方式：不治療／錢 ≥ 100 + 預留時全體治療／有罪人陣亡時復活（預設）。復活也不得花到預留金額。實機：沒有人陣亡時 Revive 是灰的；復活要先點陣亡罪人的頭像，`Select` 才會出現，點活著的罪人沒反應；復活後 HP 全滿、SP 為 0。商店罪人列的頭像間距和事件頁不同 | 商店主畫面 | #10 | `captures/82_shop_heal_page.png`、`191_heal_page_with_dead.png`、`213_revive_selected.png`、`194_revive_result.png`、`109_heal_all_result.png` |
| 出售畫面 | OCR：標題 `Sell E.G.O Gift`、飾品名稱與售價；模板：重複飾品標記（`Sale & Fusion-only`，實機未見）、Close／Sell | 只在想買的飾品買不起時出售；只賣合成挑剩的材料（[03](03-decisions.md) 第 13 節），以及 `Sale & Fusion-only` 的重複飾品 | 商店主畫面 | #10 | `captures/88_shop_sell_page.png`、`89_sell_gift_selected.png` |
| 合成畫面 | OCR：標題 `Fuse E.G.O Gift`、預測列；模板：中央的體系選擇格、周圍的材料格、Close／Fuse | 依點數挑 3 個到材料槽數的非主要體系飾品合成，指定主要體系；每放一個就回讀材料槽與格子外框（[03](03-decisions.md) 第 13 節，#77）。實機：點中央格開 `Fusion - Keyword Selection` 選體系；材料最多 5 格；`Wishmaking` 勾選框要花持有的星光，必須保持不勾；按 Fuse 後還有確認頁 `Fuse the selected E.G.O Gifts?`。合成本身不花 Cost。點飾品出現的說明框會蓋住 Fuse，Close 在容易誤觸的位置。固定配方（`Fusion Available`、`Recipes`、點產物一鍵放入材料）見下方「合成頁的配方合成」 | 飾品獲得視窗、商店主畫面 | #10 | `captures/94_shop_fuse_try2.png`、`95_fuse_center_tap.png`、`173_fuse_confirm.png`、`174_fuse_result.png` |
| 定向刷新對話框 | OCR：標題 `Shop - Keyword Refresh`、`Spend <n> Cost to Keyword Refresh?`；模板：10 個體系選項、Cancel／Refresh | 指定主要體系；條件是錢 ≥ 定向刷新費用 + 120 | 商店主畫面 | #10 | `captures/79_shop_keyword_refresh_dialog.png`、`80_shop_keyword_bleed_selected.png` |
| 離開確認 | OCR：`Leave the shop?` | 點 Confirm | 地圖頁 | #10 | `captures/111_shop_leave.png` |
| Super Shop（困難） | 同商店主畫面，標題改為紅色 `Super Shop` | 和一般商店同一套流程；規則不依賴格數，每格都從畫面讀價格和體系。實機：10 格分兩列，要捲動；有一格 `ID Skill Search` 用星光計價；`Special Catalogue` 會讓獎勵卡多一張 | 同商店主畫面 | #17 | `captures/162_f2shop_entered.png`、`163_supershop_scrolled.png`、`190_f3shop_entered.png` |

### 合成頁的配方合成（#304 實機）

實機觀察 (2026-10-23)，1.117.0、1280×720、一般商店；Poise 隊，起手 Gift Search 拿 `Pendant of Nostalgia`（I）、`Recollection of a Certain Day`（II）、`Devil's Share`（I），所以持有的飾品湊得出固定配方 `Reminiscence`（III，兩件材料）。座標是遊戲像素。沒有附靜態截圖的觀察（手動放材料、放著材料改選 Burn、確認框、`GET!`、合成後的列表、Recipes 篩選鈕展開）來自 PR #321 的錄影與本機截圖。截圖：`tests/screens/ShopFuseLocked.png`、`ShopFuseAvailable.png`、`ShopFuseRecipeTwo.png`、`ShopFusionRecipes.png`（本次實機，畫面上沒有身分區，已過遮罩工具）、`ShopFuseRecipe.png`（#103，三件材料的 `Cask Spirits`）。

- **進頁先鎖住列表**：剛按 `Fuse Gifts` 進來，列表整片變暗，中間浮出 `Select a Keyword.`（停著不會自己消失），列表照樣畫出 `Fusion Available` 與持有的飾品，但點不到它們：點暗掉的格子只會開 `Fusion - Keyword Selection`。選好體系並 Confirm 後列表才亮起。（`ShopFuseLocked.png`）
- **`Fusion Available` 區塊**：持有的飾品湊得出一條固定配方時，列表最上面多一個黃色標題 `Fusion Available`（標題中心 y 約 229、x 約 710），下面列出**能合成的產物**（一格一個產物，第一格中心約 (677, 293)，格子排法和持有飾品相同，每列 5 格）；`E.G.O Gifts Owned` 標題因此往下掉到 y 約 363，第一列持有飾品的中心 y 約 427。沒有區塊時標題在 y 約 229、第一列在 293（合成後區塊消失，列表立刻往上移）。這次只湊得出一個產物，**同時多個產物、湊不齊時的樣子沒看到**。（`ShopFuseAvailable.png`）
- **點 `Fusion Available` 的產物 = 一鍵放入材料**：點一下，這個配方的材料自動進材料槽（這次是 I 階的 `Pendant of Nostalgia` 進上槽、II 階的 `Recollection of a Certain Day` 進右槽，左槽空），中央槽顯示產物（III 階 `Reminiscence`），`Forecasts` 顯示該階羅馬數字、`Guaranteed`、`100%` 與產物自己的體系圖示；產物格和持有飾品裡那兩件材料都加橘框。再點一次同一個產物，材料全部退回、中央清空、`Forecasts` 回到 `? -`。（`ShopFuseRecipeTwo.png`）一個產物有兩條配方時（例如 `Lucky Pouch`）點它會放哪一條、能不能選，**沒看到**。
- **手動放材料也會自動認成配方**：先點 `Recollection`（進右槽；單獨一件時 `Forecasts` 是 `? -`，飾品說明框彈出並蓋住 `Fuse`，點 Recipes 與 Fusion Guide 之間的空白處關掉），再點 `Pendant`（進上槽）。第二件放入的瞬間中央就換成 `Reminiscence`、`Forecasts` 變 `III Guaranteed 100%`，`Fusion Available` 裡的產物格同時加橘框。和點產物放入的結果相同。
- **固定配方和選的體系無關（只試了 Burn）**：材料放好後再開 `Fusion - Keyword Selection` 改選 Burn（原本是 Poise）並 Confirm，結果仍是 Poise 的 `Reminiscence`、`Forecasts` 仍是 `Guaranteed 100%`（只試了 Burn 這一個）。選的體系留著：合成完中央槽與 `Forecasts` 顯示的是 Burn 的火焰圖示。所以固定配方看起來不需要選對的體系（只試了 Burn 一個，unverified 其他體系），但**進頁後一定要先選一個體系才能點列表**；現有流程的順序（點中央格 → 選體系 → Confirm）本來就是先選體系。
- **按 Fuse 與確認框**：`Fuse`（約 (790, 585)）跳出 `Fuse the selected E.G.O Gifts?`，左邊 `Selected E.G.O Gifts n/3`（兩件材料時是 `2/3`，分母是槽數），右邊 `Prediction` 框列出產物；Cancel 約 (490, 583)、Confirm 約 (790, 583)。Confirm 後跳 `E.G.O Gift GET!`（產物名、說明，說明長時有往下箭頭），再按它的 Confirm（這次說明框的 Confirm 在約 (640, 532)，位置看說明長短）。回到合成頁：頁面還開著、材料槽清空、`Fusion Available` 消失、持有飾品列表多了產物、少了兩件材料。（合成不花 Cost。）
- **`Recipes` 按鈕（約 (668, 160)）**：開 `Fusion Recipes` 彈窗，**只是唯讀的配方表**：右上有篩選鈕（約 (955, 165)，展開後是 Keywords 的 Burn、Bleed、Tremor、Rupture、Sinking、Poise、Charge，Attack Type 的 Slash、Pierce、Blunt，Other 的 Keywordless 開關；開關的效果沒試），底部 `Confirm`（約 (640, 570)）關閉。列表可上下拖動；最上面可能有 `Theme Pack Exclusive Fusion Gift` 區（同一天另一局的截圖看到，沒有附檔：一個專屬配方，產物還是黑色剪影；本節附的 `ShopFusionRecipes.png` 沒有這一區），之後每個體系一區（體系圖示加名稱），每條配方一列「材料 + 材料（+ 材料）= 產物」，材料與產物的左上是階級；只在困難模式出現的飾品上方有紅色 `HARD` 小標；沒取得過的飾品是黑色剪影。點材料或產物沒有任何反應（點了兩次，沒有說明框）。體系區的順序不跟著目前選的體系（選 Burn 時 Poise 區在最前；更早一次實機是 Bleed 在最前，截圖沒有附檔），什麼決定順序**沒看出來**。Confirm 關閉。（`ShopFusionRecipes.png`）
- **月之記憶（混合配方，`Lunar Memory`）沒有驗證**：需要 IV 階殘片與記憶，這個帳號的一般商店流程湊不到；怎麼放、`Fusion Available` 是否列出它、`Forecasts` 顯示什麼都沒看到。放法等拿到殘片實機看過再補（#300）。

## 困難模式與結算

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| Boss 後的選擇與試煉 | 模板：卡片上的 `Acquire E.G.O Gift` 與 `Mounting Trials` 標籤、`Refuse Gift`；OCR：每欄的飾品名稱、試煉名稱（例如 `Defense Level Up`、`Growth I`）、`Select <n>/<m>` | 每個選項評分 = 飾品分數 − 權重 × 試煉風險，試煉以名稱查風險表，查不到的當最高風險（5）；依分數取 `Select n/m` 的可選數量，同分選風險較低者（[03](03-decisions.md#12-選飾品boss-後的選擇與試煉)）。實機：4 欄，每欄上半是飾品、下半是試煉，試煉旁有紅色 `Enemy Level Up +1`／`+2` 標記；計數是 `Select 0/2`，選一欄就同時拿到飾品和試煉。1.117.0 實機在普通局的 Boss 後也看到這一頁（未見官方公告，待確認）：3 欄、`Select 0/1`；按 `Refuse Gift` 仍會拿到隨機試煉（#28） | 飾品獲得視窗 → 下一層的主題包頁 | #17、#19、#28 | `captures/122_boss_gift_trials_page.png`、`124_boss_gift_pick2.png`、`176_f2boss_rewards_gift.png`、`127_after_boss_gifts.png` |
| 通關畫面 | OCR：右上 `Victory`（和戰鬥的 `VICTORY` 不同位置）；右下 Confirm | 點 Confirm。2026-10-15 實機（1.117.0）：第 5 層 Boss 打完、經載入畫面後出現，左邊是 `Most Valued Employee`，右邊是經驗與 12 位罪人 | Exploration Complete 摘要 | #30 | `tests/screens/RunVictory.png` |
| Defeat 畫面 | OCR：`Defeat`；模板：右下 Confirm | 點 Confirm | Exploration Complete 摘要 | #8 | `captures/244_after_forfeit_confirm.png` |
| Exploration Complete 摘要 | OCR：`Exploration Complete`、逐層結果（例如 `Floor 5 [HARD] 5/6`）、`Total Progress`；模板：右下 `Claim Rewards` | 點 Claim Rewards。摘要有 6 頁，不用翻頁 | Exploration Reward 視窗 | #8、#19 | `captures/245_after_defeat_confirm.png`、`246_exploration_complete_p6.png` |
| Exploration Reward 視窗 | OCR：標題 `Exploration Reward`、`Weekly Bonuses <n>/3`、這局的結果（最後到達的一層與進度，例如 `Floor 5 [HARD] 5/6`）；模板：三個 ON／OFF 開關、`GiveUpRewards`／`To Window`／`Claim` | 依結算規則（[01](01-architecture.md#結算規則)）：讀結果，顯示 `Floor 5` 且進度 `n/n`（已通過數等於總數，困難層可能是 `7/7`，#67）才依每週獎勵設定（不用／普通／困難、每局一次或全用）把對應數量的開關切到 ON，數量和剩餘次數從畫面讀，再點 Claim；Claim 要花的腦啡肽模組不夠就停止並通知。沒達到目標就點 GiveUpRewards。Claim 完成後輪替游標前進。bot 不點 To Window。實機：Claim 按鈕上標示花 5 個模組（`-5`）；視窗只顯示最後到達的那一層，不看背後摘要的逐層結果。2026-10-15 實機（1.117.0，普通局 `Floor 5 [NORMAL] 6/6`）：`n/3` 是剩餘次數；還有剩時遊戲**預設把第 1 個開關切到 ON**（普通局也是），開關是黃底 `ON`／暗底 `OFF` 文字；開關不影響 Claim 的 `-5`；Claim 後經載入畫面回到主畫面，不經過獎勵畫面；用了每週獎勵時先跳使用每週獎勵確認，再跳 `Rewards Acquired` 與 `Pass Level Up`（2026-10-16 實機，#65） | 主畫面、結束確認（不領獎）、不使用每週獎勵確認、移往 Window 確認 | #8、#9、#17、#19、#30、ADR 0003 | `captures/252_exploration_reward_window.png`、`tests/screens/ExplorationReward.png`、`ExplorationRewardOff.png` |
| 不使用每週獎勵確認 | OCR：`You have Weekly Bonus Eligibility remaining. Are you sure you want to claim the current rewards without using the Eligibility?` | 依結算規則不用每週獎勵時點 Confirm；其他情況點 Cancel。2026-10-15 實機：還有剩餘次數、開關全 OFF 時按 Claim 才出現；Cancel／Confirm 位置和結束確認相同 | 主畫面（Confirm）、Exploration Reward 視窗（Cancel） | #30 | `tests/screens/ClaimNoBonusDialog.png` |
| 領獎確認（沒有每週獎勵） | OCR：`Claim the rewards?` | 本週每週獎勵已用完時按 Claim 出現，視同不使用每週獎勵確認：點 Confirm。實機觀察 (2026-10-17) | 主畫面 | #34 | 實機觀察 (2026-10-17) |
| 使用每週獎勵確認 | OCR：`Spend your 「Weekly Bonuses」 to claim the bonus rewards?` | 依結算規則切好、讀回要用的每週獎勵開關後點 Confirm；其他情況點 Cancel。2026-10-16 實機：有開關 ON 時按 Claim 才出現；Cancel／Confirm 位置和結束確認相同 | `Rewards Acquired`（Confirm）、Exploration Reward 視窗（Cancel） | #65 | `tests/screens/ClaimBonusDialog.png` |
| 領獎彈窗（`ClaimPopup`） | OCR：標題 `Rewards Acquired` 或 `Pass Level Up`，蓋在 Exploration Complete 摘要上 | 點 Confirm（575–705, 455–490） | `Pass Level Up`、載入畫面 → 主畫面 | #65 | `tests/screens/RewardsAcquired.png`、`PassLevelUp.png` |
| 移往 Window 確認 | OCR：`Would you like to move to the Window?` | 誤入時點 Cancel。按 Confirm 會回主畫面，獎勵保留到下次進鏡牢選單時再彈出 | Exploration Reward 視窗、主畫面 | #8 | `captures/253_after_to_window.png` |
| 結束確認（不領獎） | OCR：`End expedition without claiming rewards?` | 依結算規則放棄獎勵時點確認；其他情況誤入時點 Cancel。2026-10-15 實機：Cancel（515, 493）回到視窗；Confirm 之後的畫面未實測 | 入口頁（待截圖確認）、Exploration Reward 視窗 | #8、#19 | `tests/screens/GiveUpDialog.png` |

輪替游標前進的理由見 [ADR 0003](../adr/0003-screen-is-truth-state-file-only-rotation-cursor.md)。

## 全域彈窗

全域彈窗排在 hub `next` 的最前面，各子流程也引用同一組節點。困難鏡牢那一局沒有遇到任何全域彈窗。（#8）

| 畫面 | 辨識方式 | 處理 | 可能的下一個畫面 | 來源 | 實機截圖 |
|---|---|---|---|---|---|
| 連線中 | OCR：`CONNECTING` | 等待 | 前一個畫面、Retry 彈窗 | #7、#8 | — |
| Retry 彈窗（待截圖確認） | OCR：按鈕文字以 `Retry`（可接倒數，例如 `Retry (5)`；不含 DEFEAT 的 `Retry Stage`）或 `Try Again` 開頭 | 點那個按鈕 | 連線中、前一個畫面 | #8、#84 | —（`tests/screens/RetryCountdown.png`、`TryAgain.png` 是合成圖） |
| 說明頁（`HelpPager`） | 每個 `i` 按鈕後面的同一種說明頁（鏡牢 34 頁、Refraction Railway 18、Sinners 17、Extract 4、Dispense 5；第一次進某畫面時自己跳出的教學是不是同一種畫面還沒截到）。標題隨頁改變，所以認外框：左上的返回按鈕（`Screen/HelpPagerBack.png`）與下方一排頁碼點（`Screen/HelpPagerDot.png`），兩個模板都中（返回按鈕單獨在入口頁的返回鍵上也有 0.98，靠頁碼點區分）。鏡牢的第 1 頁是入口頁的圖，所以它排在 `MirrorHub` 的 `HubText` 之前 | Android 返回鍵關閉（左上 ← 也可以；右側 ▶ 只翻頁） | 前一個畫面 | #8、#85 | `tests/screens/HelpPager.png`、`HelpPagerLast.png`、`HelpPagerExtract.png`、`HelpPagerSinners.png`（實機 2026-10-21） |
| 公告（`Notices`） | OCR：上方分頁 `Event Notifs`／`System Notifs` | Android 返回鍵關閉 | 主畫面 | #85 | `tests/screens/EventNotices.png`、`SystemNotices.png`（實機 2026-10-21） |
| 信箱（`Mailbox`） | OCR：標題 `Mailbox`，且按鈕 `Close` | 點 Close；旁邊的 Claim All 不按，不領信 | 主畫面 | #85 | `tests/screens/Mailbox.png`（實機 2026-10-21） |
| 設定選單（`SettingsMenu`，主畫面右上齒輪） | OCR：標題 `Settings`，且按鈕 `Return` | 點 Return；下方的 Quit Game 不按（沒有確認對話框，直接結束遊戲），也不進 Settings 改設定 | 主畫面 | #85 | `tests/screens/SettingsMenu.png`（實機 2026-10-21） |
| 每週重置通知／舊局過期（待截圖確認，沒有專用節點） | AALC：主畫面上只有一個打勾按鈕的 renew 對話框，確認後回主畫面（`renew_confirm`，AALC `mirror.py`） | 還沒做：沒有截圖，按鈕是圖示不是文字，`PopupButton` 讀不到。下次重置時看 `logs/unknown/` | 前一個畫面、主畫面 | #8、#14、#85 | — |
| 無限鏡牢（Parallel Superposition）彈窗 | OCR：`You can enter the … Mode`，按鈕 `Cancel`（兩個按鈕：Cancel／Confirm）。只有「Parallel Superposition Mode」開著、通過第 5 層（EXTREME 是第 10 層）才會出現 | 點 Cancel，不開啟（`ParallelModePrompt`，排在各頁之前，它蓋在頁面上） | 前一個畫面 | #8、#17、#85 | `tests/screens/ParallelModePrompt.png`、`ParallelModeExtreme.png`（遊戲說明頁裡的彈窗圖，位置待實機確認） |
| 升級彈窗 | 結算後的 `Pass Level Up` 是 `ClaimPopup`；其他升級彈窗沒有截圖 | `ClaimPopup` 按 Confirm；其他的由 `PopupButton` 擋住單鈕的，其餘還沒做 | 前一個畫面 | #16、#85 | `tests/screens/PassLevelUp.png` |
| 單鈕彈窗（`PopupButton`，後備） | 先比按鈕左端的模板（深色金框 `Screen/DialogButton.png`，或淺色羊皮紙 `Screen/DialogButtonParchment.png`），中了才 OCR：畫面中央（540–740, 430–520）的按鈕文字是 `Close`、`Confirm` 或 `OK`。只有一個按鈕，沒有可選的，所以按它；兩個按鈕的問句（Cancel／Confirm）按鈕不在中央，不會被它按到。排在 `ClaimPopup` 之後、所有頁面之前，維護公告在它前面（同樣是單個 Close，要停止） | 點那個按鈕 | 前一個畫面 | #85、#86 | `tests/screens/TitleErrorConfirm.png`（合成圖）；`FormationNoSinners.png`（羊皮紙，實機）；`RewardsAcquired.png`、`PassLevelUp.png` 它也讀得到，但 `ClaimPopup` 在前 |
| 標題畫面的資料下載對話框 | OCR：視窗內文含 `Download`／`Update`／`<n> MB`，按鈕 `Confirm`（另一個 `Close`）。實機 2026-10-16（L3 重啟後）與 2026-10-22（週重置更新後，`Downloading 539.76 MB of data`） | `auto_download` 開：點 Confirm（`DownloadDialog`），卡住偵測暫停 3 分鐘等進度畫面出現，這一層的時間上限重新起算（下載期間遊戲不在 bot 手上）；關：停止程序 | 下載進度畫面、標題畫面 | #31、#86 | `tests/screens/TitleDownload.png` |
| 下載進度畫面 | OCR：左下 `DOWNLOADING UPDATE`／`DOWNLOADING RESOURCES`（後接百分比與檔數，右下另有 `NOW LOADING...`） | 等待畫面（`Downloading`）：畫面一直在動就一直等，不設總上限；完全不動 80 秒才算卡住（見 [06](06-recovery.md)）。實機 2026-10-21：17.77 GB 約 32 分鐘，先 UPDATE 0/1 再 RESOURCES n/1741 | 標題畫面 | #86 | `tests/screens/DownloadingUpdate.png`、`DownloadingResources.png` |
| 遊戲內的更新通知（待截圖確認） | OCR：內文含 `new download has been added`（遊戲會關閉或回標題）或 `Version update available`，單一按鈕 `Close`／`Confirm`／`OK`；文字取自客戶端字串 `EN_MainUIText`，位置沒截圖，ROI 取得寬。排在 `DownloadDialog` 與 `PopupButton` 之前 | `auto_download` 開：按下按鈕後重啟遊戲（`AcceptUpdate` 執行 `RecoverL3`，不算卡住、不扣恢復次數；每次啟動 bot 最多 2 次，第 3 次停止），標題的下載對話框接著處理；戰鬥中也排在 `PopupButton` 前（`BattleHUD`）；關：停止程序 | 標題畫面 | #86 | `tests/screens/UpdateDialog.synthetic.png`（合成圖） |
| 使用者條款（User Agreement） | OCR：標題 `User Agreement`，且左框下有 `I agree.`。實機 2026-10-21（新帳號） | `auto_accept_terms` 開：兩個 I agree. 框沒勾的就點（框內有白勾 = 已勾），確認兩個都勾上才點 Confirm（`AcceptTerms`）；關：停止程序 | 標題畫面 | #85 | `tests/screens/UserAgreement.png`、`UserAgreementTicked.png` |
| 「?」選效果頁（待截圖確認，沒有節點） | AALC 在鏡牢迴圈裡（主題包頁與選路之間）點一個八角形的「?」按鈕（`event_effect_button`），再點打勾確認（`select_event_effect_confirm`），註解標 rare。是哪一頁、什麼時候出現都沒有截圖，AALC 的素材沒有任何背景，也沒有一張現有截圖含這個圖示 | 還沒做。證據只夠說「點八角形『?』、再點打勾」，不夠定位置與辨識。出現時 `logs/unknown/` 會留下截圖，之後再補節點。需實機確認：①是哪一頁、出現在什麼時候（AALC 的迴圈順序暗示在主題包頁之後、地圖頁之前，只是推測）；②八角形「?」和打勾在畫面哪裡，「?」是不是選項之一（AALC 沒選任何東西就按打勾）；③打勾按鈕是圖示、OCR 讀不到，要截圖裁模板；④多常出現（AALC 標 rare），會不會讓選擇有後果 | 地圖頁 | #87 | — |
| 遊戲用戶端過舊 | OCR：標題畫面的對話框內文含 `client is not up to date`（`Game client is not up to date. Please update to the latest version.`，按鈕 `Close`／`Go to Store`；實機 2026-10-22 週重置後） | 直接停止，保存證據並發 webhook（`ClientOutdated`）；不按 Go to Store，Play 商店的更新延後（#1 Deferred） | 停止 | #86 | `tests/screens/TitleClientOutdated.png` |
| 維護公告 | OCR：公告視窗內文含 `maintenance`，且視窗唯一的按鈕讀到 `Close`（兩者同時出現；其他畫面文字含 maintenance 不算） | 直接停止，保存證據並發 webhook | 停止 | #14、#83 | `tests/screens/MaintenanceNotice.png` |

## 資訊面板（誤觸才會進入）

以下面板不在流程裡，是點錯位置時才會出現。看到時關閉並回到前一個畫面，屬於 L1 恢復（彈窗與返回）。（#14）

| 畫面 | 從哪裡進入 | 關閉方式 | 實機截圖 |
|---|---|---|---|
| 主題包詳情（`Effective Affinities`） | 主題包卡片上的放大鏡 | Confirm | `captures/13_theme_pack_magnifier_detail.png` |
| Featured Theme Packs 清單 | 主題包頁或地圖頁右側按鈕 | Confirm | `captures/21_pack_list_button.png` |
| Active Effects（Trials／Grace of Stars／Choice Effects／Adversity 分頁） | 主題包頁、地圖頁或商店右側 `?` | Confirm | `captures/16_theme_pack_help.png`、`108_shop_help.png` |
| 隊伍配置檢視（12 張人格卡） | 主題包頁或地圖頁右側罪人按鈕 | 返回 | `captures/18_sinner_button_panel.png` |
| E.G.O Gifts Owned／E.G.O Gifts（Owned、Clear Rewards、Current Theme Pack-Exclusive、Featured 分頁） | 主題包頁或地圖頁左上飾品欄 | Confirm | `captures/20_ego_gift_inventory.png`、`37_map_topleft_gift_panel.png` |
| 教學頁（鏡牢說明、`Creating your Team`） | 地圖頁、入口頁、選隊頁、編隊頁的 `i` | 返回（`HelpPager`，見全域彈窗） | `captures/28_map_info_i.png`、`47_formation_info_i.png` |
| Progress（`Exploring` 進度頁） | Dungeon Progress 面板的 Progress | Close（直接回到地圖） | `captures/32_gear_progress_view.png` |
| Encounter Reward Cards Guide | 獎勵卡頁右上 | Confirm | `captures/116_reward_card_guide.png` |
| 人格詳情（戰鬥中） | 戰鬥中點到單位 | 點面板外 | `captures/219_battle_sinner_detail_panel.png`、`220_after_close_detail.png` |
| 商店子頁：`Enhance E.G.O Gift`、`Team`、`Replace <罪人>'s Skill`、`ID Skill Search` 的選人模式、`Fusion Recipes`、`Fusion Guide` | 商店主畫面或合成畫面的對應按鈕 | Close、返回、Cancel、Return 或 Confirm（依頁面） | `captures/101_shop_enhance_page.png`、`104_shop_team_page.png`、`106_shop_replace_skill.png`、`165_supershop_id_skill_search.png`、`98_fuse_recipes.png`、`99_fusion_guide.png` |

## 未決

- **DEFEAT 對話框的 `Return to Stage Select`**：之後出現哪個畫面沒有實測。（#16）
