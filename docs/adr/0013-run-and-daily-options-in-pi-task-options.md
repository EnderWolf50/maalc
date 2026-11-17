---
status: superseded by ADR 0015（曾修訂 ADR 0006、ADR 0010）
---

> 由 [ADR 0015](0015-settings-window-runs-the-tasks.md) 取代：設定視窗自己執行任務，執行選項、日常參數與全域選項回到設定檔（版本 23），任務選項、全域選項、隊伍選項檔與 `zh_cn` 語系都拿掉。下文只記錄 v1.0.0（MXU 版）時的做法。（#813，2026-11-17）

# 執行選項與日常參數放在 PI 任務選項，隊伍下拉由設定 GUI 產生的引入檔提供

一次執行原本要在兩個程式裡設定：要跑哪些任務在 MXU／MFAAvalonia 的任務清單，每個任務怎麼跑在設定 GUI 的「執行選項」與「日常」兩頁。想多打一局、換一支隊伍打經驗本，都要切到另一個程式存檔；兩個實例不能各用各的值；清單裡排兩個鏡牢任務也做不到，設定檔只有一組執行選項。使用者 2026-11-16 決定這 25 個鍵全部搬到 client 的**任務選項**，選隊伍用下拉選單，在 v1.0.0 發布之前完成（#776）。

- 鏡牢任務的 10 個設定、經驗本與紐本各 5 個、狂氣換腦啡肽的 Daily Count，是各自任務的任務選項；webhook、自動同意使用者條款、自動接受下載與更新、關畫面前存截圖，是**全域選項**。
- 全域選項用 `global_option` 列出。MXU v2.7.1 只在設定頁的 `setting` 區塊顯示全域選項；MFAAvalonia v2.16.4 每次開始任務都在工作執行緒重建 `setting` 的項目、碰到畫面而丟例外，之後的開始全被忽略，一個任務都跑不了（#799）。所以 `setting` 區塊把選項列在 `option`，後面再放一個空的 `Option`：MXU 讀 `interface.json` 分大小寫，只看 `option`；MFAAvalonia 的 Newtonsoft.Json 比對欄位不分大小寫、後面的鍵蓋掉前面的，讀到空的 `Option` 就跳過這個區塊，全域選項只從 `global_option` 顯示一次。`tests/test_interface_options.py` 照兩邊的讀法各檢查一次。
- 每個選項只寫一個鍵，寫進所屬任務入口節點的 `attach`，全域選項寫進專用的 `GlobalOptions` 節點（沒有 `next` 指到它）。兩個 client 都把各選項的 `pipeline_override` 收成陣列交給 MaaFramework，MaaFramework 依序套用、`attach` 逐鍵合併，所以同一個節點上的多個選項不會互相蓋掉（maafw 5.14.3 實測）。
- Agent 的入口動作在點任何東西之前讀一次這兩個 `attach`，依一份選項 schema 檢查（`agent/task_options.schema.json`），之後所有讀這些值的地方都從那裡拿。少值或值不對時，任務在點任何東西之前結束，留一行指出選項名稱；沒有「讀不到就用設定檔」的退路。PI 擋不住的跨選項規則（目標層數大於 5 時隊伍要整局困難）也在這時檢查。
- 隊伍下拉：`interface.json` 用頂層的 `import` 引入 config 資料夾裡的**隊伍選項檔**，由設定 GUI 在存檔與啟動時產生。`interface.json` 每次都會被整份換掉（`tools/install.py`、兩個 client 的更新），config 資料夾則留下來。兩個 client 都只在啟動時讀 `interface.json`，所以隊伍改了要重開 client。
- 隊伍、出戰順序方案、星光方案、主題包方案、飾品清單、事件覆寫與試煉分數覆寫留在設定檔：它們是清單、具名方案和表格，PI 選項表達不了。

## 兩條之後的版本也要守的規則

- 選擇型選項的 case 只能加在最後，預設的 case 放第一個，`default_case` 也指它。MFAAvalonia 存的是 case 的索引、任務選項一律從第 0 個 case 開始；插入或重排會讓已存的值指到別的 case，MXU 則把消失的 case 換成預設。隊伍選項檔同樣只往後加，刪掉的隊伍保留它的 case。
- 入口節點與 `GlobalOptions` 的名稱、`attach` 的鍵，是 `interface.json` 與 Agent 之間的約定（`tests/test_interface_options.py` 檢查兩邊一致）。[ADR 0012](0012-resource-package-hot-update.md) 的模板版本實作後（#769），改到它們的 pipeline 變更要配新的 `interface.json`，所以模板版本要加一。

## 修訂的部分

- [ADR 0006](0006-settings-gui-writes-one-settings-file.md)：「PI 只留控制器、資源與任務，鏡牢任務沒有使用者選項」與「`pipeline_override` 傳值、`global_option` 都不再需要」不再成立。任務選項與全域選項正是用 `pipeline_override` 傳值、用 `global_option` 列出。
- [ADR 0010](0010-one-pi-task-per-daily.md)：「每個任務怎麼跑放在 settings.json，PI 不放使用者選項」不再成立；它否決「在 PI 選項放次數與隊伍」的理由（ADR 0004 的固定欄位問題）不適用於這次的做法，見下一節。

## 為什麼不會回到 ADR 0004

[ADR 0004](0004-team-settings-in-pi-with-fixed-preset-slots.md) 的問題是固定的欄位：6 組方案、10 支隊伍，方案只能用編號命名。這次搬過去的只有單一的值（難度、局數、次數、開關）；隊伍的 case 由使用者的隊伍產生，數量不限、名字是使用者取的；方案與清單仍在設定檔，由設定 GUI 編輯。

## Considered Options

- **把舊值寫成選項的預設值來搬遷**：MFAAvalonia 的任務選項不看 `default_case`；MXU 第一次載入新的 `interface.json` 就把當時的預設存起來；MXU 的引入是整個選項取代，帶預設值的檔會一直蓋掉之後版本的選項定義。只有隊伍兩個鍵透過隊伍選項檔的 `default_case` 帶過去，且只在 MXU 有效。
- **直接改寫 `interface.json` 放隊伍**：它每次重新組裝、每次 client 更新都被整份換掉，也就不再是手寫、受審查的檔案。
- **重新整理按鈕**：兩個 client 執行中都不重讀 `interface.json`，也沒有重新載入的按鈕，設定 GUI 裡的按鈕能做的事存檔已經做了。
- **用 `custom_action_param` 傳值**：同名欄位整個取代，多個選項寫同一個節點會互相蓋掉，經驗本與紐本入口的 `"exp"`／`"thread"` 參數也會被蓋掉。
- **其他讓兩個 client 都能用全域選項的寫法**（#799）：`setting` 加 `default_expand: false`，MFAAvalonia 收起項目的那條路一樣碰畫面（`TaskQueueView.HideCurrentPanel`）；把 `setting` 放進引入檔，兩個 client 都合併引入檔的 `setting`；換新版 MXU，v2.10.2 仍只在 `setting` 顯示全域選項；MFAAvalonia 到 v2.16.5-beta.2 與 master 都沒改這段。把 4 個全域選項搬回設定 GUI 也可行，但兩個 client 之外又多一個要設定的地方，留作這個寫法失效時的退路。

## Consequences

- 設定 GUI 少了「執行選項」與「日常」兩頁，也不再在存檔時檢查目標層數對隊伍的規則：目標層數是 client 的任務選項，GUI 看不到。隊伍頁改放一行固定說明。
- 設定檔升到版本 21，移除 `run`、`luxcavation`、`charge_enkephalin`（#782）；在那之前，這三段由 GUI 原封不動寫回，Agent 不讀。
- 模板版本從 1 升到 2（`agent/resource_package.py` 的 `TEMPLATE`，#782）。這次 pipeline（新增 `pipeline/options.json` 的 `GlobalOptions` 節點）、`interface.json`（選項寫進入口節點與 `GlobalOptions` 的 `attach`）和 Agent（入口動作只從這兩個 `attach` 讀）一起改。版本 1 的程式拿到新的 pipeline，它的 `interface.json` 不送這些選項、Agent 也不讀；新的程式拿到版本 1 的 pipeline，就少了全域選項要寫進去的 `GlobalOptions` 節點。兩邊各自只套用和自己模板版本相同的資源包（ADR 0012），所以要加一。
- 實機測試工具像 client 一樣送任務選項（`tools/client_override.py`、`bot.py run --option`）；`bot.py prep --set` 遇到搬走的鍵（`run.*`、`luxcavation.<任務>.*`（隊伍也算）、`charge_enkephalin.*`，以及這些段整段的 `--set`，例如 `--set luxcavation={...}`）停下並指向 `--option`。
- MFAAvalonia 記錄任務送出的選項值時，只要有任何 `password` 輸入就整行遮掉；webhook 是 `password` 輸入，所以除錯時要看 Agent 自己記的 `options:` 那一行（webhook 只寫有沒有設定）。
- 空的 `Option` 是繞路。根本的修正在 MFAAvalonia：在畫面的執行緒建 `setting` 的項目，或開始任務時沿用已有的項目、不再重建（`TaskLoader.CreateSettingItem`）。這在 maalc 裡改不到。
- 空的 `Option` 靠的是 MFAAvalonia 的 JSON 讀法。MFAAvalonia 改成分大小寫的讀法、又還沒修好執行緒問題時，#799 會再出現；換 MFAAvalonia 或 MXU 的版本時，要在兩個 client 上實際開始一個任務。
- MFAAvalonia 預設簡體中文，且只從介面語言的翻譯檔取字，所以 `interface.json` 另有 `zh_cn` 語系：`tools/zh_cn_locale.py` 以 OpenCC t2s 從 `zh_tw.json` 轉出，不手改（#799）。
- 兩個 client 的行為原本都是讀原始碼得來的（#776「其他說明」）；2026-11-16 在 MXU v2.7.1 與 MFAAvalonia v2.16.4 實機驗收（#776、#799）。
