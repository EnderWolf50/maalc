---
status: accepted（修訂 ADR 0006、ADR 0010）
---

# 執行選項與日常參數放在 PI 任務選項，隊伍下拉由設定 GUI 產生的引入檔提供

一次執行原本要在兩個程式裡設定：要跑哪些任務在 MXU／MFAAvalonia 的任務清單，每個任務怎麼跑在設定 GUI 的「執行選項」與「日常」兩頁。想多打一局、換一支隊伍打經驗本，都要切到另一個程式存檔；兩個實例不能各用各的值；清單裡排兩個鏡牢任務也做不到，設定檔只有一組執行選項。使用者 2026-11-16 決定這 25 個鍵全部搬到 client 的**任務選項**，選隊伍用下拉選單，在 v1.0.0 發布之前完成（#776）。

- 鏡牢任務的 10 個設定、經驗本與紐本各 5 個、狂氣換腦啡肽的 Daily Count，是各自任務的任務選項；webhook、自動同意使用者條款、自動接受下載與更新、關畫面前存截圖，是**全域選項**。
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

## Consequences

- 設定 GUI 少了「執行選項」與「日常」兩頁，也不再在存檔時檢查目標層數對隊伍的規則：目標層數是 client 的任務選項，GUI 看不到。隊伍頁改放一行固定說明。
- 設定檔升到版本 21，移除 `run`、`luxcavation`、`charge_enkephalin`（#782）；在那之前，這三段由 GUI 原封不動寫回，Agent 不讀。
- 實機測試工具像 client 一樣送任務選項（`tools/client_override.py`、`bot.py run --option`）；`bot.py prep --set` 遇到搬走的鍵（`run.*`、`luxcavation.<任務>.*` 除了隊伍、`charge_enkephalin.count`）停下並指向 `--option`。
- MFAAvalonia 記錄任務送出的選項值時，只要有任何 `password` 輸入就整行遮掉；webhook 是 `password` 輸入，所以除錯時要看 Agent 自己記的 `options:` 那一行（webhook 只寫有沒有設定）。
- 沒有在 MXU 或 MFAAvalonia 實際跑過；兩個 client 的行為都是讀原始碼得來的（#776「其他說明」），實機驗收在各張子 issue。
