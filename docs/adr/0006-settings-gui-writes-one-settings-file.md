---
status: accepted（取代 ADR 0004，修訂 ADR 0005）
---

# 使用者設定改由自製設定 GUI 寫進一份設定檔

[ADR 0004](0004-team-settings-in-pi-with-fixed-preset-slots.md) 把使用者設定全部放進 PI 選項，結果是固定 6 組方案、10 支隊伍，方案只能叫「方案 1」到「方案 6」，合計約 387 個控制項；PI 也沒有清單、表格和按鈕。使用者要的是自己命名、數量不限的方案與隊伍，以及能編輯的覆寫表。所以 maalc 另做一個設定 GUI，用 Tauri 2 + React/TypeScript（前例：MXU）。所有使用者設定都由它寫進 `<root>/config/settings.json`，Agent 在任務開始時讀取。（#19，2026-10-14 定案）

第一階段（A1）的 GUI 只編輯設定，不執行 bot。執行仍在 MXU 或 MFAAvalonia：PI V2 只留控制器、資源與鏡牢任務，鏡牢任務沒有使用者選項，照舊用 `agent.child_exec` 啟動 Python Agent。之後（A2）GUI 可能也負責執行，用 MaaFramework 官方的 Rust 綁定，或照 PI 的方式啟動 Agent；A1 的設定檔格式不能因為 A2 而改變。

設定檔的格式由一份 JSON Schema（`settings.schema.json`）描述，GUI 和 Agent 共用。型別、範圍，以及出戰順序的罪人、獎勵卡順序、星光優先順序不重複這類結構檢查寫在 schema。跨物件的檢查，例如兩支啟用的隊伍用同一個 `TEAMS` 欄位、沒有啟用的隊伍、引用的方案不存在，在 GUI 儲存時和 Agent 任務開始時各做一次。Agent 遇到任何錯誤都不開始跑。

## Considered Options

- **NiceGUI**：次佳。全 Python，MaaDebugger 也用它，但介面像網頁。
- **Electron**：安裝包約 385 MB，Tauri 約 3 MB。
- **PySide6 + PyQt-Fluent-Widgets**：GPLv3 會強迫整個專案改授權（[ADR 0001](0001-mit-and-no-agpl-derived-assets.md)）。AALC 用的就是它。
- **Flutter**：沒有 MaaFramework 綁定。
- **Wails v3、Flet 1.0**：都在大改版中。
- **維持只用 PI 選項**：沒有清單、表格、按鈕，欄位數量固定。這正是 ADR 0004 要繞過的限制。

## Consequences

- ADR 0004 作廢。固定的方案欄位、`global_option`、用 `pipeline_override` 傳值、用腳本產生 `interface.json`，都不再需要。
- 方案（出戰順序、星光、主題包）由使用者命名，數量不限。隊伍的出戰順序與星光可以引用方案，也可以選「自訂」，直接填只給這支隊伍用的值；主題包只能選「預設」或使用者的方案。
- 隊伍數量不限，每支有一個不隨改名或排序改變的 id。輪替游標與 `runs.jsonl` 都記隊伍 id。
- 修訂 [ADR 0005](0005-game-data-files-separate-from-user-settings.md)：每季的預設主題包方案仍在資料檔，使用者不能改；使用者的主題包方案、事件覆寫、試煉風險覆寫存在設定檔，疊加在資料檔上。不再有另外的覆寫檔。
- 設定檔用暫存檔加改名寫入，並有 `version` 欄位供日後遷移格式。
- 多一個要維護的專案（`gui/`），也多一套 Rust 與 TypeScript 工具鏈。
