# ProjectInterface V2 能表達多複雜的設定

> 依據（2026-10-13 取得，皆為原始碼或官方協議文件，沒有實機執行）：
> MaaFramework [f21a0b8](https://github.com/MaaXYZ/MaaFramework/tree/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f)（PI 協議 v2.10.2）、
> MXU [9fa8cc5](https://github.com/MistEO/MXU/tree/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3)（AGPL-3.0）、
> MFAAvalonia [450a8f3](https://github.com/MaaXYZ/MFAAvalonia/tree/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717)（GPL-3.0）、
> MaaEnd [0d763f9](https://github.com/MaaEnd/MaaEnd/tree/0d763f9a3eb3ed21974e8ffd881327f0701b09bf)、
> MaaLimbus [fd78ca8](https://github.com/sairaisaika/MaaLimbus/tree/fd78ca83f9e8395fddfaba3a4868825ba442ac17)（AGPL-3.0）。
> 授權界線依 [ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md)：MXU、MFAAvalonia、MaaLimbus 只讀來理解行為，本文沒有複製它們的程式碼或 interface.json 內容；引用的片段僅限說明用的欄位名稱。

## 結論

1. PI V2 的單一 option 能表達：單選、多選、開關、字串輸入（可帶 regex 驗證與型別轉換）、快捷鍵，以及 select／switch 底下無限巢狀的子 option。任務、option、preset、group、setting、pretask 都能用 `import` 拆檔。
2. **協議沒有「重複 N 組」的結構**（沒有陣列型 option、沒有動態新增列）。N 支隊伍、每隊十多個欄位只能這樣處理：(a) 預先展開固定 N 組 option（MaaLimbus 做法，`interface.json` 因此長到 3.5 MB，靠腳本產生）；(b) MXU 的「複製任務」讓同一個 task 有多份各自的 option 值；(c) 把整支隊伍放進 agent 自己管的檔案，GUI 只放「用哪一隊」這種小選項。
3. MXU 與 MFAAvalonia 兩邊共同支援的交集比協議小：`checkbox` 的 `min_count`／`max_count`、`password` 只有 MXU 有；`checkbox` 的 case 底下接子 option 只有 MFAAvalonia 有。
4. option 抵達 agent 的唯一管道是 `pipeline_override`（改節點欄位，例如 `attach`、`custom_action_param`）。`PI_*` 環境變數只帶 Client、控制器、資源的資訊，**不含任何 option 值**。
5. 兩個 GUI 都沒有提供「狀態儲存 API」，但 agent 是普通子進程，工作目錄就是安裝目錄（`interface.json` 所在處），可以自己讀寫檔案；MaaLimbus 就是把狀態寫在 `<root>/config/`。輪替進度跨次保存只能靠 agent 自己的檔案。

## 1. 單一 option 能表達什麼

出處：[3.3-ProjectInterfaceV2协议.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.3-ProjectInterfaceV2协议.md)（下稱「協議」）。

| type | 輸入形式 | 對 pipeline 的作用 | 協議出處 |
|---|---|---|---|
| `select`（預設） | 從 `cases` 選一個 | 選中 case 的 `pipeline_override` 生效 | L653-L655、L680 |
| `switch` | 兩個 case，`name` 必須是 Yes/No（或 y/n 等變體） | 同 select | L685-L690 |
| `checkbox`（v2.3.0） | 從 `cases` 勾多個；v2.10.1 起可設 `min_count`／`max_count` | 所有勾選 case 的 override 依 **`cases` 定義順序**合併，與勾選先後無關 | L683、L798-L806 |
| `input` | `inputs[]` 多個欄位，各有 `default`、`pipeline_type`（string／int／bool）、`verify`（regex）、`pattern_msg` | option 自己的 `pipeline_override` 當模板，字串中的 `{欄位名}` 被替換；整數／布林欄位會去掉引號轉型 | L712-L734、L766-L767 |
| `hotkey`（v2.8.0） | 捕獲按鍵 | 替換成虛擬鍵碼整數 | L747-L790 |

- 所有 type 共通：`controller`／`resource` 過濾（不符就整個 option 與其子 option 都不產生 override，L661-L669）、`label`／`description`／`icon`、`$` 開頭的 i18n。
- **巢狀 case**：`case.option` 是子 option 鍵名陣列，只有該 case 被選中才顯示與生效，「支援無限嵌套」（L706-L707）。協議沒有條件式（「若 A=x 且 B=y」）：條件只能是「某個 case 被選中」這一種。
- **預設值**：`default_case`（select／switch 填字串，checkbox 填陣列）；`input` 欄位各自有 `default`。
- **覆蓋順序**：`global_option` < `resource.option` < `controller.option` < `task.option`（L985-L1000）。
- **preset（v2.3.0）**：一組「哪些 task 勾選＋各 option 的值」快照。值的型別：select／switch 填 `case.name`，checkbox 填 `case.name` 陣列，input 填「欄位名→字串」物件（L896-L906）。preset 只能指向 `task[].name`，**不能引用另一個 preset，也不能對「同一個 task 出現兩次」分別給值**（以 `task.name` 為唯一鍵，L564）。
- **import（v2.2.0）**：可匯入 `task`、`option`、`preset`、`group`、`pretask`、`global_option`、`setting`。`option` 同名以後者為準，`task`／`preset`／`setting` 是追加，`group` 與 `global_option` 依名稱去重（L856-L870）。只拆檔，不提供參數化或迴圈。
- **setting（v2.8.0）**：獨立的「任務設定」頁，分區放 option（L821-L854）；搭配 `global_option` 做「不屬於單一任務的全域設定」。
- **group（v2.4.0）**：任務分組，可折疊（L506-L538）。

### 實例：MaaEnd 的用法

- `assets/interface.json` 本身只有約 10 KB，其餘全用 `import`（72 個檔案，含 `tasks/preset/*.json`、`tasks/setting/*.json`）拆開（[assets/interface.json](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/assets/interface.json)）。
- 單一 task 通常掛 3 到 5 個 select／switch／input，沒有深層巢狀（例：[AutoStockpile.json](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/assets/tasks/AutoStockpile.json)）。
- preset 的 option 值混用字串、陣列、物件三種型別，與協議表一致（[QuickDaily.json](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/assets/tasks/preset/QuickDaily.json)）。
- MaaEnd 的 agent 狀態只放在記憶體（例：[autostockpile/state.go](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/agent/go-service/autostockpile/state.go)），沒有跨次保存的做法可參考。

## 2. 清單型設定（N 支隊伍各有欄位）能不能表達

先對照 AALC 每隊要設的東西（[11-md-team-formation.md](aalc/11-md-team-formation.md) 的 `TeamSetting` 欄位表）：`team_number`（1–40）、`team_system`（10 選 1）、`sinner_order`（12 格的點選順序）、`opening_bonus`（10 個星光，各 0–3 級）、`normal_to_hard_floor`、`fixed_team_use`（困難／普通）、`use_starlight` 等，每隊約 25 個以上欄位。

**協議沒有：** 陣列型 option、「新增一列」按鈕、`repeat`／`for_each`、多個欄位共用一個模板的語法。`input` 的 `inputs[]` 是**設計時固定**的欄位清單，不是使用者可增減的列（協議 L712-L734）。所以「N 隊」在 PI V2 內只有三條路：

### 做法 A：預先展開固定組數（MaaLimbus 的做法）

- MaaLimbus 的 [assets/interface.json](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/assets/interface.json) 約 3.5 MB、711 個 option（666 select、45 input）。
- 40 個隊伍欄位：`global_option` 與 `setting` 各列出 `global_team_1` 到 `global_team_40`，每個 setting 分區 `default_expand: false`。
- 每隊的 option（`global_team_N`）是個二選一的 select：`saved`（沿用 agent 已存的）／`edit`（展開 `global_team_N_name`、`_systems`、`_order_1` 到 `_order_12`）。選 `edit` 時 `pipeline_override` 在一個專用節點（`Global_global_team_N`）的 `attach` 放 `{"global_build":{"edit":true}}`。
- 輪替長度：`mirror_queue_count` 是 select，每個 case（1 到 N）各自列出 `mirror_queue_1..k` 子 option，也就是用巢狀 case 手動展開「前 k 個欄位才出現」。
- 組數與命名高度規律（`global_team_1_order_1..12` 等），推測是腳本產生，沒有查證其產生工具。
- 代價：檔案大、GUI 載入變慢的風險未實測；組數是寫死的。

### 做法 B：複製任務（MXU 有、MFAAvalonia 未確認）

- MXU 的每個已加入任務是 `SelectedTask { id, taskName, customName, optionValues, … }`（[types/interface.ts L342-L355](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/types/interface.ts#L342-L355)），`id` 與 `taskName` 分離，同一個 `taskName` 可有多份、各有自己的 `optionValues`。右鍵「複製任務」呼叫 `duplicateTask`（[appStore.ts L1008-L1050](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/stores/appStore.ts#L1008-L1050)），可自訂名稱。每份任務各自跑一次 `entry`，各帶自己的 override。因此「一支隊伍 = 一個任務實例」在 MXU 可以做到，隊伍數由使用者決定。
- MFAAvalonia：在 [AddTaskDialogViewModel.cs](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/ViewModels/UsersControls/AddTaskDialogViewModel.cs) 沒看到去重邏輯，資源字串裡也沒有「複製任務」；**能否重複加入同一個 task 沒有確認，需實機測**。MFAAvalonia 另有非標準擴充 `task.repeatable`／`repeat_count`（[README](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/README.md) 「MFAAvalonia 擴展字段」），那是同一組設定重複執行 N 次，不是 N 組不同設定。
- 風險：規格若依賴此做法，就是依賴 GUI 行為而非 PI 協議；preset 也無法描述這種多份實例（見上節）。

### 做法 C：隊伍存在 agent 自己的檔案，GUI 只放挑選

- GUI 的 option 只放「這次用哪一隊」「輪替模式」這類少量欄位；每隊的完整設定（順序、星光、體系）由 agent 讀寫自己的檔案，編輯方式是 agent 端工具或手改檔案。
- MaaLimbus 的 `saved` 選項就是這個模式的一半：GUI 的 option 預設 `saved`（不覆蓋），只有選 `edit` 才把值推進 agent，由 agent 寫進自己的存檔（見 [mirror_task_options.py](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/mirror_task_options.py)：欄位值為 `saved` 時就不進結果）。
- 代價：GUI 上看不到完整設定；兩邊（GUI 與檔案）可能不同步，需要規格定「誰是真實來源」。

### 做法 D（補充）：把一支隊伍編成單一 `input` 字串

- 一個 `input` 欄位帶 `verify` regex，使用者貼一段約定格式的字串（如 AALC 的編隊匯出格式）。協議支援，但沒有任何一個參考專案這樣做，可用性也沒有佐證；列在這裡只是協議允許。

## 3. MXU 與 MFAAvalonia 的支援交集

比較方式：讀兩邊的 PI 資料模型與選項處理程式碼，不是看 README 宣稱。

| 能力 | MXU | MFAAvalonia | 判定 |
|---|---|---|---|
| `select`／`switch`／`input`（含 `pipeline_type`、`verify`） | 有（[pipelineOverride.ts L372-L520](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/pipelineOverride.ts#L372-L520)） | 有（[MaaInterface.cs L119-L260](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Extensions/MaaFW/MaaInterface.cs#L119-L260)） | 交集 |
| `checkbox`（基本多選） | 有 | 有（[TaskOptionGenerator.cs L189-L192](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Helper/TaskOptionGenerator.cs#L189-L192)） | 交集 |
| `checkbox` 的 `min_count`／`max_count` | 有（[checkboxOptionValidation.ts](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/checkboxOptionValidation.ts)） | **沒有**：`MaaInterface.cs` 與 `TaskOptionGenerator.cs` 搜尋 `min_count`／`max_count`／`password` 皆無結果 | 只有 MXU，別依賴 |
| `checkbox` 的 case 接子 option（`case.option`） | **不支援**：`collectOptionOverrides` 的 checkbox 分支只合併 override，不遞迴（[pipelineOverride.ts L397-L403](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/pipelineOverride.ts#L397-L403)，對比 select／switch 的遞迴在 L424）；UI 只有 select／switch 取 `nestedOptionKeys`（[OptionEditor.tsx L496](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/components/OptionEditor.tsx#L496)） | 有，註解明寫「checkbox 需顯示所有已勾選 case 的子選項」（[TaskOptionGenerator.cs L250](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Helper/TaskOptionGenerator.cs#L250)） | 只有 MFAAvalonia，別依賴 |
| `select`／`switch` 的巢狀 `case.option` | 有 | 有 | 交集 |
| `input.password` | 有（加密存設定檔，[interface.ts L263](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/types/interface.ts#L263)） | 沒有 | 只有 MXU（本專案用不到密碼） |
| `hotkey` | 有 | 有（有 `Hotkeys` 與鍵碼轉換） | 交集（本專案用不到） |
| `preset` | 有 | 有（`MaaInterfacePreset`） | 交集 |
| `import`（task／option／preset／group／setting／pretask／global_option） | 有（[interfaceLoader.ts L230](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/services/interfaceLoader.ts#L230)） | 有（[MaaInterface.cs L1766-L1772](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Extensions/MaaFW/MaaInterface.cs#L1766-L1772)，`Preset` 改成依 `name` 去重合併，與協議的「追加」略有出入） | 交集；preset 名稱別重複 |
| `global_option`、`setting`、`group`、`pretask` | 有 | 有（皆有對應欄位） | 交集 |
| 控制器 / 資源過濾 | 有 | 有 | 交集 |
| 複製任務（多份同 task） | 有 | 未確認 | 只有 MXU（確定） |

兩邊各自的非標準擴充，**規格不要用**：

- MXU：`input_type`（file／time）、`placeholder`、label 行內 Markdown、內建特殊任務（例如 `__MXU_SLEEP__`，[specialTasks.ts L41-L43](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/types/specialTasks.ts#L41-L43)）、`wlroots`、`input` 欄位的 `icon`（[interface.ts L237-L265](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/types/interface.ts#L237-L265)）。
- MFAAvalonia：`task.repeatable`／`repeat_count`、`option.doc`、`{PROJECT_DIR}` 占位符（[MaaInterface.cs L1655-L1670](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Extensions/MaaFW/MaaInterface.cs#L1655-L1670)）、`MFA_INSTANCE_ID`／`MFA_INSTANCE_NAME` 環境變數（見第 4 節）。

另外兩邊對 `PI_INTERFACE_VERSION` 宣稱的版本不同：MXU 回報 `v2.10.1`（[piEnv.ts L63](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/piEnv.ts#L63)），MFAAvalonia 回報 `v2.5.0`（[AgentHelper.cs L56](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Extensions/MaaFW/AgentHelper.cs#L56)）。這與上表一致：MFAAvalonia 沒實作 v2.10 的欄位。

### 交集內可用的「安全子集」

`select`、`switch`、`input`（string／int／bool + `verify`）、`checkbox`（**不用** `min_count`／`max_count`、**不接**子 option，上限與下限改由 agent 自己驗證）、`select`／`switch` 的巢狀 case、`global_option`、`setting`、`group`、`preset`、`import`。

## 4. option 如何到達 agent

1. **pipeline_override**（唯一管道）：Client 把選中 case 的 override 依覆蓋順序合併成 JSON 陣列，連同 `entry` 一起交給 MaaFramework 的 post task。MXU 的組裝見 [pipelineOverride.ts `generateTaskPipelineOverride`](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/pipelineOverride.ts#L523-L630)。
2. agent 端可讀的位置：
   - 節點的 `custom_action_param`／`custom_recognition_param`，任意 JSON，由框架傳進自訂動作／辨識的 callback（[3.1-任务流水线协议.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.1-任务流水线协议.md) L917-L918、L1359-L1360）。
   - 節點的 `attach`（自由 JSON，「不影響節點執行，可透過介面取得」，協議 L293-L296），用 `MaaContextGetNodeData` 之類的介面取回（[2.2-集成接口一览.md L911-L915](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/2.2-集成接口一览.md#L911-L915)）。MaaLimbus 的 agent 就是這樣讀：先在 interface 裡放一批「只用來裝 option 值」的空節點（`MirrorRunBounds`、`MirrorBattleAssignment` 等），option 的 override 寫它們的 `attach`，agent 再用 `get_node(...)['attach']` 取值（[mirror_task_options.py](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/mirror_task_options.py)）。
   - 該檔頂端註解寫「獨立的原生任務節點，避開 MXU 對 action param 的淺層替換」。意思是同一個節點上的 override 是整個欄位替換、不是深度合併；MXU 自己也在註解寫「同名欄位完整替換，非深合併」（[pipelineOverride.ts L1-L5](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/pipelineOverride.ts#L1-L5)）。**設計 option 時，一個 option 管一個節點的一個欄位，不要讓兩個 option 寫同一個 `custom_action_param`。**（此行為取自 MXU 註解與 MaaLimbus 的作法，未實測 `attach` 在 override 時是否深度合併。）
3. **型別轉換**：`input` 的 `{欄位名}` 替換由 Client 做。MXU 用 JSON 字串全域取代，整數／布林型別會去掉引號（[pipelineOverride.ts L432-L505](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/utils/pipelineOverride.ts#L432-L505)）。字串值會做 JSON 跳脫。
4. **PI_* 環境變數（v2.5.0）**：Client 啟動 agent 時注入，**只有** `PI_INTERFACE_VERSION`、`PI_CLIENT_NAME`、`PI_CLIENT_VERSION`、`PI_CLIENT_LANGUAGE`、`PI_CLIENT_MAAFW_VERSION`、`PI_VERSION`、`PI_CONTROLLER`（JSON）、`PI_RESOURCE`（JSON）（協議 L472-L504）。沒有 option 值、沒有 task 名稱、沒有實例編號。MXU 實作只放行 `PI_` 開頭的鍵（[maa_agent.rs L365-L377](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src-tauri/src/commands/maa_agent.rs#L365-L377)）。
5. **pretask（v2.7.0）**：可以讓 option 的取值序列化成單行 JSON 當最後一個參數傳給控制器啟動前的外部程式（協議 L342-L347）。這是另一條把 option 值交給程式的路，但程式是在連線前執行、與 agent 不同進程。本專案尚無需求，僅列出。
6. MFAAvalonia 另外注入 `MFA_INSTANCE_ID`、`MFA_INSTANCE_NAME`（非標準，[AgentHelper.cs L287-L288](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Extensions/MaaFW/AgentHelper.cs#L287-L288)）；MXU 沒有對應。需要區分多實例的狀態檔時別依賴這兩個變數。

## 5. agent 能否讀寫自己的設定或狀態檔

**能，而且 GUI 沒有限制，也沒有提供任何幫助。** agent 是 Client 啟動的普通子進程。

- **工作目錄**：協議規定 `child_exec` 的 CWD 為 `interface.json` 所在目錄（協議 L435）。MXU 以 `current_dir(&cwd)` 啟動，`cwd` 取自應用的 `basePath`（[maa_agent.rs L359](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src-tauri/src/commands/maa_agent.rs#L359)、[DashboardView.tsx L378-L384](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/components/DashboardView.tsx#L378-L384)）。MFAAvalonia 以 `AppPaths.DataRoot` 當 `WorkingDirectory`，預設等於安裝目錄（[AgentHelper.cs L276](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Extensions/MaaFW/AgentHelper.cs#L276)、[AppPaths.cs L15](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Helper/AppPaths.cs#L15)）。兩邊在預設安裝下都是「`interface.json` 所在目錄」，但 MFAAvalonia 有「獨立資料目錄」模式（`IsUsingIndependentDataRoot`），此時 CWD 會不同。**agent 不要假設 CWD，用 `__file__` 定位自己的根目錄**（MaaLimbus 的 `application_root` 就是為此，[runtime_paths.py](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/runtime_paths.py)）。
- **GUI 自己的檔案位置**（避免撞名）：MXU 把設定寫在 `<exe 目錄>/config/mxu-<name>.json`，並有時間戳備份檔（[configService.ts L30、L71](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/services/configService.ts#L30)；macOS 改用 `~/Library/Application Support/MXU`，[utils.rs L173-L189](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src-tauri/src/commands/utils.rs#L173-L189)）。MFAAvalonia 寫在 `<安裝目錄>/config/`（含 `instances/`），另有 `backup/`（[AppPaths.cs L16-L35](https://github.com/MaaXYZ/MFAAvalonia/blob/450a8f3134d2b5ac3fce4fc8eeb3e745197b1717/MFAAvalonia/Helper/AppPaths.cs#L16-L35)）。
- **既有先例**：MaaLimbus 的 agent 把私有狀態放 `<root>/config`（可用 `MAALIMBUS_DATA_PATH` 覆蓋），與兩個 GUI 的 `config/` 同一層共存（[runtime_paths.py](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/src/maalimbus/runtime_paths.py)）。
- **GUI 提供的相關功能**：只有各自的 option 值持久化（使用者填的值，下次開啟還在）。沒有「agent 回寫 option 值」的管道：MXU 與 MFAAvalonia 都是單向（GUI → override → agent），agent 改不了 GUI 上顯示的選項。所以輪替進度（「下一次輪到第幾隊」）若要跨次執行保存，只能寫進 agent 自己的檔案，GUI 不會知道。
- **建議（本文推論，非來源陳述）**：狀態檔放獨立子目錄（例如 `config/maalc/`），不要與 `mxu-*.json`、`instances/` 同層混放，以免被 GUI 的備份或清理動作波及；寫檔用「寫暫存檔再改名」避免中斷時毀損（MXU 自己就為「NTFS 斷電後檔案全零」加了偵測，[configService.ts L55-L66](https://github.com/MistEO/MXU/blob/9fa8cc51e8ff8cd89d99f3ea55fe3a7a82e6ede3/src/services/configService.ts#L55-L66)）。
- **多實例**：兩個 GUI 都能開多個實例（MXU 的 tab、MFAAvalonia 的 instance 頁籤），agent 可能同時有多個進程在跑，狀態檔需要考慮鎖或每實例一份；MXU 沒有傳實例 ID 給 agent，只能由 override 或 agent 參數自己帶。

## 6. 對後續規格的含意（只列觀察，決策屬於 [#9](https://github.com/EnderWolf50/maalc/issues/9)）

- 「N 支隊伍 × 約 25 欄位」不存在原生解法；上面 A、B、C 三條路各有明確代價（A：檔案大、組數固定；B：只保證 MXU；C：GUI 看不到完整設定）。
- 無論選哪條，**輪替進度必須是 agent 自己的檔案**。
- 若以交集為準，`checkbox` 做星光多選時沒有 `max_count` 保護，也不能對每個 case 掛子 option（例如「該星光要 + 還是 ++」），要改用每個星光一個 `select`（off／+／++），MaaLimbus 的 `mirror_star_task_0..9` 就是這個形狀（on／off 二選一，每個星光一個 select）。
- 每個 option 只寫自己專屬的節點欄位（第 4 節），避免淺層替換互相蓋掉。

## 未確認

- MFAAvalonia 能否把同一個 task 加入多次（有無「複製任務」）：只讀了程式碼的一部分，沒找到去重或複製功能，但沒有證明不能。
- MaaLimbus 的巨大 `interface.json`（3.5 MB、711 個 option）在 MXU 與 MFAAvalonia 的載入與渲染效能：沒測。
- `attach` 在 `pipeline_override` 時是深度合併還是整欄替換：協議只說預設值與節點 `attach` 做字典合併（L296、L420），沒有明說 override 的行為。
- 兩個 GUI 實際跑起來的畫面行為（折疊、預設展開、巢狀 case 的狀態保留）都來自原始碼，沒有實機驗證。
