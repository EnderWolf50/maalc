---
status: accepted（取代 ADR 0013；修訂 ADR 0006、ADR 0010、ADR 0014；依 ADR 0009 維持 Tauri）；由 #878 修訂
---

> #878 修訂（spec #871，2026-11-22）：起頭隊伍在設定視窗是隊伍佇列每一列的旗子（隊伍佇列在「執行」分頁鏡牢任務的選項裡），沒有「照隊伍佇列」這個選項：`null` 是沒有旗子亮著。設定檔會記住旗子，所以用完要再按一次旗子取消。

# 設定視窗自己執行任務，執行選項回到設定檔

用 maalc 原本要開兩個程式：隊伍、方案和飾品清單在設定視窗設定；要跑哪些任務、什麼順序、局數、難度與日常次數在 MXU 或 MFAAvalonia 的任務清單設定，按開始也在那裡。[ADR 0013](0013-run-and-daily-options-in-pi-task-options.md) 把執行選項搬進 client 之後，問題反而更多（#811）：

- client 的選項只有下拉、開關和輸入框，沒有清單。隊伍佇列只能留在設定視窗，起頭隊伍只能做成下拉選單。
- client 執行中不重讀選項，新增或改名隊伍後要重開 client。
- 兩個 client 各有怪癖：MFAAvalonia 遇到 `setting` 區塊就跑不了任務（#799），用索引存選項；MXU 讀選項分大小寫。maalc 為此寫了特殊寫法、隊伍選項檔，還要產生簡體中文語系。
- bot 想讓使用者看到的東西（下一局輪到誰、這次跑了幾局）都要繞回設定視窗看。

使用者 2026-11-17 決定拋棄 MXU 和 MFAAvalonia，把執行任務整合到設定視窗：v1.0.0 照 MXU 版發布，下一版（2026-11-18 定為 v2.0.0）完全不用 MXU 和 MFAAvalonia。

## 決定

- **設定視窗負責執行。** 視窗啟動一個 Python 執行器子程式（zip 附的 Python 跑），兩邊用標準輸入／輸出傳 JSON lines：命令是開始、停止、偵測模擬器，事件是記錄行、任務狀態、模擬器清單、錯誤與結束。執行器建立在實機工具原本的 client 程式上（連線、載入資源、啟動 bot 子程序、送任務），所以每日任務、實機測試和使用者走同一條路。細節在規格 #811「執行器」。
- **執行選項回到設定檔，版本 23。** 鏡牢任務的 10 個選項、全域的 4 個（webhook、自動同意條款、自動下載、關畫面前存截圖）、經驗本與紐本各 5 個、狂氣換腦啡肽的次數，回到 `run`、`luxcavation`、`charge_enkephalin` 三段，鍵名與預設值照 #776 以前。起頭隊伍是 `run.start_team`（`null` 是「照隊伍佇列」）。新增三段：`tasks`（任務清單：每個任務的 id 與是否勾選，陣列順序就是執行順序）、`emulator`（位址、MuMu 實例編號、MuMuManager 路徑）、`schedules`（星期、時間、是否叫醒電腦）。全部仍在一份設定檔，照 [ADR 0006](0006-settings-gui-writes-one-settings-file.md)。
- **Agent 從設定檔讀選項。** 任務開始時讀一次（#777 的讀法不變），來源從 client 送來的 `attach` 改回設定檔。跨選項的規則（目標層數對隊伍、起頭隊伍、經驗本與紐本的隊伍）照舊在那個任務開始時檢查，所以刪掉或停用的隊伍只會停下用到它的任務，不會讓整份設定檔讀不了。
- **`interface.json` 只留開發工具要讀的部分**：控制器、資源、任務入口與 Agent 的啟動設定，給 MaaDebugger 和 `maa-tools check` 用。任務選項、全域選項、`setting` 區塊、隊伍選項檔的引入、`zh_cn` 語系與 #799 的寫法都拿掉。
- **zip 不再附 MXU 與它的授權檔**，NOTICE 也拿掉 MXU。
- **定時執行交給 Windows 工作排程器**，執行 `maalc-gui.exe --run <排程 id>`；視窗另有程式自動更新（規格 #811「定時執行」「自動更新」）。
- **程式更新換下來的舊版，下次啟動時刪掉，只有一個例外**：套用中途被打斷或失敗後沒能全部搬回時，`cache/update/old/` 是那些舊檔唯一的一份，所以留著（#817）。在使用者把檔案搬回、清掉 `old/` 之前，視窗每次啟動都寫明舊檔在哪、為什麼不能套用，新的更新不套用（不會蓋掉那份舊檔），定時執行也略過，因為資料夾裡可能一半是新版的檔案。

## 維持 Tauri（ADR 0009）

[ADR 0009](0009-keep-tauri-gui-gpui-if-resident.md) 說：GUI 要負責執行、又必須一直開著時，優先改用 GPUI，因為 Tauri 開著時約佔 220 MB。這次視窗不必常駐：定時執行靠工作排程器在時間到時打開視窗，跑完就關；平常開視窗只是為了設定或手動執行。所以 220 MB 只在執行期間出現，ADR 0009 改框架的前提不成立，視窗留在 Tauri。執行器與視窗之間的協定和 GUI 框架無關，之後真要換框架，執行器不用動。

## 修訂的部分

- [ADR 0006](0006-settings-gui-writes-one-settings-file.md)：A1「GUI 只編輯設定，不執行 bot；執行在 MXU 或 MFAAvalonia」結束。A2 的「用 MaaFramework 的 Rust 綁定，或照 PI 的方式啟動 Agent」定為後者的變形：視窗啟動 Python 執行器，執行器再啟動 Agent。「A1 的設定檔格式不能因為 A2 而改變」：設定檔從版本 22 升到 23，只加回與新增段落，原有的段落不變。
- [ADR 0010](0010-one-pi-task-per-daily.md)：一個日常一個任務照舊；「順序、啟用、排程交給 client」改成設定檔的 `tasks` 與 `schedules`，由視窗編輯、執行器照順序送出；每個任務怎麼跑回到設定檔，和 ADR 0013 以前一樣。
- [ADR 0014](0014-team-queue-apart-from-team-list.md)：起頭隊伍從 client 選項 `MirrorStartTeam` 改成設定檔的 `run.start_team`。規則不變：任務開始時檢查隊伍已刪除或停用，第一局新局開局前排到佇列第一。client 會記住選擇的那條提醒，換成「設定檔會記住」：平常仍應留「照隊伍佇列」。

## Considered Options

- **視窗用 MaaFramework 的 Rust 綁定直接執行**：要在視窗裡多一份 MaaFramework 與它的 LGPL 授權說明，MaaFramework 當掉時視窗也跟著當掉，實機工具也得另寫一條路。Python 執行器沿用每天在跑的程式，當掉只結束子程序（規格 #811 研究第 1 節）。
- **繼續用 MXU，只在設定視窗補上任務清單**：client 的選項限制和兩個 client 的怪癖都還在，使用者還是要開兩個程式。
- **任務清單、模擬器與排程另存一個檔**：ADR 0006 定了一份設定檔；分檔要多一套寫入與合併。
- **視窗內的計時器做定時執行**：視窗要一直開著，正是 ADR 0009 要避免的；重開機後也不會補跑錯過的時段。

## Consequences

- 取代 ADR 0013。它的任務選項、全域選項、隊伍選項檔（`config/team_options.json`）、`tools/client_override.py`、`zh_cn` 語系，以及只為兩個 client 守的規則（case 只往後加、空的 `Option`）都不再需要；設定視窗不再寫隊伍選項檔。
- 設定檔版本 23。Agent 在記憶體裡遷移，只能用預設值補上新段落；設定視窗遷移後寫回，舊檔另存成 `config/settings.v<版本>.json`。版本 20 的檔原本就有這三段，遷移時保留它的值。從 MXU 的設定檔讀回使用者設過的選項，是「執行」分頁那張票的事（#811）。
- 模板版本從 2 升到 3（`agent/resource_package.py` 的 `TEMPLATE`）：pipeline 拿掉 `GlobalOptions` 節點，Agent 不再讀節點的 `attach`。版本 2 的 Agent 拿到新 pipeline 會少了它要讀的節點，所以兩邊各自只套用自己的模板版本（ADR 0012）。
- 實機工具：`bot.py prep --set` 又能設 `run.*`、`luxcavation.<任務>.*` 與 `charge_enkephalin.*`；`bot.py run` 不再收 `--option`。原本經由 client 覆寫送選項的任務測試，改成在設定檔放值。
- 從 v1.0.0 升級的使用者要手動下載 v2.0.0：MXU 不會替 maalc 檢查更新。MXU 加密存放 webhook，所以 webhook 要重填；MFAAvalonia 的設定不讀回（規格 #811 範圍外）。
- 「執行」分頁、執行器、排程與自動更新由 #811 的其他票實作；這張 ADR 生效時，設定檔已經有它們要用的段落，存檔會保留，但還沒有編輯畫面。
