# MaaFramework 專案骨架與開發工具

> 依據（皆為查證當日 2026-10-13 的 `main`／最新版）：MaaFramework [f21a0b8](https://github.com/MaaXYZ/MaaFramework/tree/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f)（v5.14.3）、MaaPracticeBoilerplate [5cb1c73](https://github.com/MaaXYZ/MaaPracticeBoilerplate/tree/5cb1c73b043113b15271a8a8b705391302e67600)、maa-support-extension [56b31bc](https://github.com/neko-para/maa-support-extension/tree/56b31bcadc4e0d7b482abd477950bb381ddf6b65)、MaaDebugger [02ce840](https://github.com/MaaXYZ/MaaDebugger/tree/02ce8404de6229e887b2acb64b233af5c403abc0)、MaaPipelineEditor [833c10c](https://github.com/kqcoxn/MaaPipelineEditor/tree/833c10c2eb8df132394b9b758066efc621505dc2)、MaaEnd [0d763f9](https://github.com/MaaEnd/MaaEnd/tree/0d763f9a3eb3ed21974e8ffd881327f0701b09bf)。標「本機實測」的項目，是在 `maafw==5.14.3` 的 Linux wheel 上實際跑過；其餘皆來自原始碼或官方文件。

## 結論

1. **骨架**：MaaPracticeBoilerplate 是 MIT，可以當起點。但它是 GitHub「Use this template」模板，maalc 已有歷史，所以是手動搬需要的檔案，並保留 `Copyright (c) 2024 MaaXYZ` 授權聲明。
2. **Agent**：`interface.json` 的 `agent.child_exec` / `child_args` 讓 UI 啟動 `python ./agent/main.py`，socket id 當最後一個參數傳入；Python 綁定是 PyPI 的 `maafw`（目前 5.14.3，LGPL-3.0）。
3. **720p 截圖與裁切**：用 VS Code 擴充 Maa Pipeline Support（MIT）或 MaaFramework 自帶的 ImageCropper。MaaDebugger 沒有裁切功能，也不是 720p 工具。
4. **離線測試**：現成方案是 `@nekosu/maa-tools test`（MIT），對存好的截圖逐節點驗證「命中／不命中」，MaaEnd 已在 CI 使用。它只跑內建辨識，不跑 Python Agent 的 Custom Recognition；後者要自己用 `CustomController` 餵圖寫 pytest。官方的 `DbgController` 在 pip 與官方 release 都**不能用**（見下）。
5. **授權**：所有開發階段工具都是 MIT 或 LGPL，可安心使用；MXU 是 **AGPL-3.0**、MFAAvalonia 與 MFAToolsPlus 是 **GPL-3.0**，當外部程式執行不影響 maalc 授權，但不要複製其程式碼，打包時另議（打包不在 v1 範圍）。

## 1. MaaPracticeBoilerplate：授權、結構、能否當起點

### 授權

- 專案是 MIT，著作權人 `MaaXYZ`（[LICENSE](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/LICENSE)；GitHub API 回傳 `MIT`）。
- 與 [ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md) 相容。複製檔案時要保留這份著作權與授權聲明（MIT 的唯一條件）。
- `interface.json` 範本裡 `"license": "MIT"` 是預填欄位，maalc 同為 MIT 可保留；`name`、`github`、`contact` 等要改成 maalc 自己的資訊。

### 結構

| 路徑 | 用途 | 出處 |
|---|---|---|
| `assets/interface.json` | PI V2 描述檔：`controller`（`Adb` 附 `display_short_side: 720`；`Win32`）、`resource`、`task`、`option`、可選的 `agent` | [interface.json](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/assets/interface.json) |
| `assets/resource/{pipeline,image,model}` | Pipeline JSON、模板圖、模型。`model/ocr/` 被 `.gitignore` 忽略，CI 發佈時自動配置 | [how_to_develop.md](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/docs/zh_cn/develop/how_to_develop.md) |
| `agent/{main,my_reco,my_action}.py` | Python AgentServer 範例 | [agent/](https://github.com/MaaXYZ/MaaPracticeBoilerplate/tree/5cb1c73b043113b15271a8a8b705391302e67600/agent) |
| `tools/{install,configure,validate_schema}.py` | 組裝發佈目錄、下載 OCR 模型、用 JSON Schema 驗證資源 | [tools/](https://github.com/MaaXYZ/MaaPracticeBoilerplate/tree/5cb1c73b043113b15271a8a8b705391302e67600/tools) |
| `maatools.config.mts`、`package.json` | `@nekosu/maa-tools` 設定（`check`、`test` 指令） | [maatools.config.mts](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/maatools.config.mts) |
| `.github/workflows/check.yml` | push／PR 時跑 `npx @nekosu/maa-tools check` 與 JSON Schema 驗證 | [check.yml](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/.github/workflows/check.yml) |
| `.github/workflows/install.yml` | 打 `v*` tag 時，下載 MaaFramework 與 MFAAvalonia，跑 `tools/install.py`，六平台打包並發 Release | [install.yml](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/.github/workflows/install.yml) |
| `.vscode/extensions.json` | 推薦 `nekosu.maa-support`、Black、markdownlint | [extensions.json](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/.vscode/extensions.json) |

### 對 maalc 的建議

- **要搬**：`agent/main.py` 的骨架、`interface.json` 的欄位骨架（只用 PI V2 標準欄位）、`maatools.config.mts` + `check.yml`。
- **先不搬**：`install.yml` 與 `tools/install.py`。它把 MFAAvalonia（GPL-3.0，見第 5 節）一起打包，且六平台矩陣對「只支援 Android 模擬器、不做打包」的 v1 是多餘的；範本也沒有幫 Python Agent 附帶 Python 直譯器（見第 2 節）。
- 範本 README 明寫「請不要直接克隆本倉庫，應通過模板創建」；maalc 已經有 commit 歷史，所以走「手動複製需要的檔案」。
- 範本不含任何測試，`check.yml` 只做靜態檢查。測試要自己加（第 4 節）。

## 2. Python Agent 的啟動與打包

### 啟動方式

- PI V2 的 `agent` 欄位可為單一物件或陣列：`child_exec`（可執行檔，例如 `"python"`）、`child_args`（參數陣列）、可選 `identifier`。工作目錄是 `interface.json` 所在目錄（[3.3-ProjectInterfaceV2协议.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.3-ProjectInterfaceV2%E5%8D%8F%E8%AE%AE.md)）。這是 PI V2 標準欄位，MXU 與 MFAAvalonia 都吃（MXU README 列有「Agent 支持」，MFAAvalonia 是範本預設搭配的 UI，見 [MXU README](https://github.com/MistEO/MXU/blob/main/README.md)、[install.yml](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/.github/workflows/install.yml)）。
- UI 啟動子進程後，把 socket id 附加為**最後一個參數**；範本 `main.py` 取 `sys.argv[-1]`，依序呼叫 `Toolkit.init_option("./")`、`AgentServer.start_up(socket_id)`、`AgentServer.join()`、`AgentServer.shut_down()`（[main.py](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/agent/main.py)）。
- 自訂辨識／動作用裝飾器註冊：`@AgentServer.custom_recognition("name")`、`@AgentServer.custom_action("name")`，在 `main.py` 裡 `import` 模組即完成註冊（[agent.md](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/docs/zh_cn/develop/agent.md)）。
- 自 PI v2.5.0 起，Client 會在子進程環境注入 `PI_` 前綴的環境變數（`PI_CONTROLLER`、`PI_RESOURCE`、`PI_CLIENT_NAME` 等），Agent 可讀取使用者目前選的控制器與資源。VS Code 擴充也實作了同一套（[agent.ts `wrapEnv`](https://github.com/neko-para/maa-support-extension/blob/56b31bcadc4e0d7b482abd477950bb381ddf6b65/pkgs/extension/src/service/agent.ts)）。

### Python 綁定

- 套件名 `maafw`（範本文件提醒「千萬不要裝錯」，另有名稱相近的套件）。PyPI 最新版 **5.14.3**（2026-10-10 發佈），`Requires-Python >=3.9`，依賴 `numpy`、`maaagentbinary`、`strenum`；授權檔為 LGPL-3.0（[PyPI](https://pypi.org/project/maafw/)；本機解開 wheel 的 `dist-info/licenses/LICENSE.md` 為 GNU LGPL）。
- 版本要與 UI 載入的 MaaFramework 原生庫同版。MaaEnd 在 CI 明確檢查這一點（[test.yml](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/.github/workflows/test.yml)）。MaaLimbus 的做法是在 `pyproject.toml` 釘死 `maafw==5.12.2`（[pyproject.toml](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/pyproject.toml)，僅作參考，AGPL）。
- 經由 `pip install maafw` 取得的 wheel 內含 `maa/bin/` 原生庫（Adb／Custom／Record／Replay ControlUnit 等），所以純 Python 即可在本機驅動 MaaFramework，不需另外下載 release。

### 打包

- 範本**沒有**處理 Python：文件寫「推薦做法是打包時附帶 Python embeddable package 與依賴，並在打包時改寫 `interface.json` 的 `agent.child_exec`」，並指向第三方專案 narutomobile 的 CI 腳本當範例（[agent.md「打包」](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/docs/zh_cn/develop/agent.md)）。
- maalc 的 v1 範圍已排除「打包、安裝包與自動更新」（map #1），開發期用 `child_exec: "python"` 即可；要記得只有開發機需要 Python 環境。

## 3. 720p 截圖、裁切與 ROI 工具

### 規則

- 模板圖「需要基於無損原圖縮放到 720p 後再裁剪」；官方建議用下列工具取得截圖，以避免縮放或編碼造成辨識異常（[1.1-快速开始.md「图像素材」](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/1.1-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.md)）。
- 控制器截圖預設縮放到短邊 720；PI 的 `display_short_side` 預設 720（[3.3 協議](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.3-ProjectInterfaceV2%E5%8D%8F%E8%AE%AE.md)）。ROI 座標也是以縮放後的座標系為準。
- 本機實測：用 `CustomController` 回傳 2560×1440 的圖，`post_screencap` 得到的是 **1280×720**。所以「任何 16:9 解析度皆可，素材以 720p 製作」的前提，在控制器這一層成立。

### 工具比較

| 工具 | 授權 | 720p 截圖 | 裁切／ROI | 備註 |
|---|---|---|---|---|
| **Maa Pipeline Support**（VS Code 擴充，`nekosu.maa-support`） | MIT | 「Maa: 截圖」存到 `debug/screenshot`；依 `interface.json` 的 `display_*` 設定縮放（[maa.ts](https://github.com/neko-para/maa-support-extension/blob/56b31bcadc4e0d7b482abd477950bb381ddf6b65/pkgs/maa-server/src/maa.ts)） | 內建裁切 webview：載入圖後自動把短邊縮到 720（[image.ts](https://github.com/neko-para/maa-support-extension/blob/56b31bcadc4e0d7b482abd477950bb381ddf6b65/pkgs/webview/src/crop/states/image.ts)）；另有任務定義跳轉、引用查詢、補全、診斷、直接執行節點（[README](https://github.com/neko-para/maa-support-extension/blob/56b31bcadc4e0d7b482abd477950bb381ddf6b65/release/README.md)） | 官方文件的首選；最近一次提交 2026-10-12 |
| **ImageCropper**（MaaFramework 倉庫 `tools/ImageCropper`） | LGPL-3.0（隨 MaaFramework 倉庫） | 可連 ADB 裝置，或讀事先準備好的截圖；`F` 存「全螢幕標準化截圖」 | 滑鼠框選；`S` 存裁切圖，`R` 只輸出 ROI，`C` 輸出 ROI 加 ColorMatch 欄位；Python 3.9+，依賴 `MaaFw`、`opencv_python`（[README](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/tools/ImageCropper/README.md)） | 只有 OpenCV 視窗，沒有 Pipeline 感知 |
| **MFAToolsPlus** | **GPL-3.0** | 官方清單形容為「提供便捷的數據獲取和模擬測試方法」，並被列為 720p 截圖推薦工具之一（[README](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/README.md)） | 倉庫 README 沒有功能說明，我沒有實際執行，無法確認細節 | .NET 10 + Avalonia；最後一次提交 2026-08-03，約兩個月未動；當外部程式用可以，不要抄碼 |
| **MaaDebugger** | MIT | 連 ADB／Win32，也可用單張圖建 `CustomController`。**自訂圖片模式設了 `set_screenshot_use_raw_size(True)`**（[maafw/__init__.py:L179](https://github.com/MaaXYZ/MaaDebugger/blob/02ce8404de6229e887b2acb64b233af5c403abc0/src/MaaDebugger/maafw/__init__.py#L179)） | 原始碼內搜尋不到裁切或 ROI 功能（只有執行節點、辨識結果頁） | `requires-python <3.14`；README 說正在重構，早期預覽改走 `npx @weinibuliu/maa-debugger`（[README](https://github.com/MaaXYZ/MaaDebugger/blob/02ce8404de6229e887b2acb64b233af5c403abc0/README.md)） |
| **MaaPipelineEditor（MPE）** | MIT（LICENSE.md 文字是 MIT，但抬頭寫 `Copyright (c) 2019, Google LLC`，疑似範本殘留，不影響使用） | 內建識別小工具與截圖裁剪、取色框選，需要啟動本機服務才能接裝置（[README](https://github.com/kqcoxn/MaaPipelineEditor/blob/833c10c2eb8df132394b9b758066efc621505dc2/README.md)） | 可視化節點編輯、流程除錯 | 只支援線上網頁或本機服務；VS Code 擴充也可呼叫它編輯 Pipeline |

### 對 maalc 的建議

素材製作流程用 **VS Code 擴充**當主力（截圖、裁切、ROI 一條龍，MIT），ImageCropper 當備用（需要 `C` 取色欄位時）。不要用 MaaDebugger 的圖片模式截圖做模板。MFAToolsPlus 授權是 GPL，且文件稀少，不列入標準流程。

## 4. Pipeline 除錯與離線重播、自動化測試

### 除錯

- **VS Code 擴充**：直接在編輯器內執行單一節點或整個 interface；Agent 會被自動啟動（呼叫 `launch.json` 裡名稱符合的 debug 設定，並把參數中的 `{AGENT_ID}` 替換成 socket id），所以可以在 Python Agent 設中斷點。範本文件也明說「只有這個擴充能自動啟動 debug session，其他工具要手動啟動 AgentServer 並傳入 socket id」（[agent.ts `startDebugSession`](https://github.com/neko-para/maa-support-extension/blob/56b31bcadc4e0d7b482abd477950bb381ddf6b65/pkgs/extension/src/service/agent.ts)、[agent.md「调试」](https://github.com/MaaXYZ/MaaPracticeBoilerplate/blob/5cb1c73b043113b15271a8a8b705391302e67600/docs/zh_cn/develop/agent.md)）。`maatools.config.mts` 的 `vscode.agents` 可把 Agent 目錄對應到 launch 設定（MaaEnd 用法：[maatools.config.mts](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/maatools.config.mts)）。
- **日誌與可視化**：多數工具會在同目錄生成 `config/maa_option.json`，其中 `logging`（預設 true，輸出 `debug/maafw.log`）、`save_draw`（存每次辨識的繪圖結果，預設 false）、`save_on_error`（任務失敗存截圖，預設 true）、`stdout_level`、`draw_quality`；自行整合時用 `Toolkit.init_option`（[1.1-快速开始.md「调试」](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/1.1-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.md)）。範本 `main.py` 已呼叫 `Toolkit.init_option("./")`。
- **MaaDebugger**：網頁版節點執行器（NiceGUI，預設埠 8011），可綁定 `AgentClient`（[maafw/__init__.py](https://github.com/MaaXYZ/MaaDebugger/blob/02ce8404de6229e887b2acb64b233af5c403abc0/src/MaaDebugger/maafw/__init__.py)）。重構進行中，不建議當主力。
- **日誌分析**：MaaLogAnalyzer（MIT）、MaaLogs 等，列在官方工具清單（[README](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/README.md)），需要時再看。

### 離線重播與自動化測試

| 方案 | 做什麼 | 能否用於 maalc | 出處 |
|---|---|---|---|
| **`@nekosu/maa-tools test`** | 每個測例是「一張截圖 + 應命中的節點清單（可附 `box`）」；對每個 interface 的 controller × resource 組合載入資源，用假控制器對每張圖跑 `context.run_recognition(node, image)`；有 worker pool 並行。MaaEnd 在 CI 跑 `pnpm test` | **可以，是最省事的辨識回歸測試**。限制：只載入 resource，**不執行 Agent**，所以 Custom Recognition 的節點測不到；且是辨識層級，不驗證流程順序 | [src/test/index.ts、worker.ts](https://github.com/neko-para/maa-support-extension/tree/56b31bcadc4e0d7b482abd477950bb381ddf6b65/pkgs/maa-tools/src/test)、[MaaEnd node-testing.md](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/docs/zh_cn/developers/node-testing.md)、[MaaEnd test.yml](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/.github/workflows/test.yml) |
| **Python 自寫：`CustomController` 餵圖** | 繼承 `CustomController`，`screencap()` 回傳存好的圖，輸入操作全回 `True`；搭配 `Tasker.post_recognition(...)` 或整條 `post_task(entry)` 跑 | **可以，涵蓋 Agent**。本機實測：`maafw==5.14.3` 能建立、連線、辨識（ColorMatch 命中 `Rect(0,0,1280,720)`）。MaaDebugger 的圖片模式用的就是這招（[MyCustomController](https://github.com/MaaXYZ/MaaDebugger/blob/02ce8404de6229e887b2acb64b233af5c403abc0/src/MaaDebugger/maafw/__init__.py#L34-L49)）；`Context.run_recognition` 可在 Agent 內單獨跑節點 | wheel `maa/controller.py`、`maa/tasker.py` |
| **`RecordController` + `ReplayController`** | 錄製：包住真實控制器，把所有操作寫成 JSONL，截圖存到 `{stem}-Screenshot/`。重播：依錄製順序回放截圖與操作結果，**操作型別或參數與錄製不符就失敗，任務提早結束會直接 `std::abort()`**，設計目的就是「確定性的 pipeline 測試」 | **可用於整條流程的回歸測試**（含 Agent，只要 Agent 的決策是確定性的）。代價：Pipeline 或 Agent 行為一改，錄製檔就要重錄；重播時會照錄製的 `cost` 睡眠 | [2.2-集成接口一览.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/2.2-%E9%9B%86%E6%88%90%E6%8E%A5%E5%8F%A3%E4%B8%80%E8%A7%88.md)、[ReplayController.cpp](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaReplayControlUnit/ReplayRecording/ReplayController.cpp)、[RecordController.cpp](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaRecordControlUnit/RecordController.cpp) |
| **`DbgController`**（官方「資料夾圖片輪播」控制器） | 載入目錄內所有圖片、每次截圖輪播，輸入操作直接成功 | **目前不能用**。本機實測：`pip install maafw==5.14.3` 後呼叫 `DbgController("imgs")`，日誌顯示 `Failed to load library .../maa/bin/MaaDbgControlUnit`，建立失敗。確認 wheel 與 Linux release zip 都沒有 `MaaDbgControlUnit` 動態庫（zip 只有標頭 `DbgControlUnitAPI.h`），原始碼倉庫有 `source/MaaDbgControlUnit/`，需自行編譯。Record／Replay 的動態庫則都有隨附。改用上一列的 `CustomController` 即可，功能相同 | wheel 內容、[release v5.14.3](https://github.com/MaaXYZ/MaaFramework/releases/tag/v5.14.3)、[2.2-集成接口一览.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/2.2-%E9%9B%86%E6%88%90%E6%8E%A5%E5%8F%A3%E4%B8%80%E8%A7%88.md#maadbgcontrollercreate) |

### 重要陷阱：直接餵圖不會被縮放

本機實測：`Tasker.post_recognition(..., image)`（`maa-tools` 的 `context.run_recognition(node, image)` 同理）把傳入的圖**原樣**拿去辨識；傳入 2560×1440 的圖，ROI `[0,0,2560,1440]` 得到的 box 是 `2560×1440`。只有經過控制器 `screencap` 的圖才會被縮到短邊 720。因此：

- 存測試截圖時，一律存**已縮到 720p 的圖**（或用 ImageCropper 的 `F`、VS Code 擴充的縮放後存檔）。
- 若走 `CustomController`，可以存原始解析度，讓框架縮放，行為與實機一致。兩種做法不要混用。

### 其他專案怎麼做（僅供參考，皆為 AGPL，只讀不抄）

- **MaaEnd**：`maa-tools test` 測例放在 `tests/**/test_*.json`，截圖放在獨立的 git 子模組 `MaaEndTestset`，並有 skill 專門處理提交前的 UID 打碼；明說「節點測試不驗證流程時序，流程要靠開發工具與實機」（[node-testing.md](https://github.com/MaaEnd/MaaEnd/blob/0d763f9a3eb3ed21974e8ffd881327f0701b09bf/docs/zh_cn/developers/node-testing.md)）。
- **MaaLimbus**：用 pytest 測 Python 模組，測試圖是用 OpenCV 把自己的模板貼到 1280×720 底圖上合成的，另外直接 assert `interface.json` 與 Pipeline 節點的欄位（[tests/test_battle_vision.py](https://github.com/sairaisaika/MaaLimbus/blob/fd78ca83f9e8395fddfaba3a4868825ba442ac17/tests/test_battle_vision.py)）。

### 對 maalc 的建議測試分層

1. 靜態：`npx @nekosu/maa-tools check`（範本已有），進 CI。
2. 辨識回歸：`maa-tools test`，截圖自己存、自己打碼；Custom Recognition 以外的節點都能測。
3. Agent 邏輯：純函式（尋路、金錢解析、飾品優先序）用 pytest；需要辨識的部分用 `CustomController` 餵 720p 截圖。
4. 整條流程回歸（選配）：實機用 `RecordController` 錄一次，之後用 `ReplayController` 重播。成本高、錄製檔易失效，v1 驗收仍以 MuMu 12 實機連跑 N 輪為準。

## 5. 授權總表（專案為 MIT，ADR 0001）

| 對象 | 授權 | 用法與限制 | 出處 |
|---|---|---|---|
| MaaPracticeBoilerplate | MIT | 可複製，保留 `MaaXYZ` 著作權聲明 | LICENSE |
| MaaFramework（含 ImageCropper、原生庫） | LGPL-3.0 | 以動態庫連結（pip wheel 即是）不要求 maalc 開源；若修改並散佈 MaaFramework 本身需遵守 LGPL。我只確認授權標示，沒有做法律判斷 | [LICENSE](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/LICENSE.md) |
| `maafw`（PyPI） | LGPL-3.0 | 同上 | wheel `licenses/LICENSE.md` |
| maa-support-extension（含 `@nekosu/maa-tools`） | MIT | 開發工具與 CI 依賴，無限制 | LICENSE、GitHub API |
| MaaDebugger | MIT | 同上 | LICENSE |
| MaaPipelineEditor | MIT | 同上（抬頭異常見第 3 節） | LICENSE.md |
| MaaLogAnalyzer | MIT | 選用 | GitHub API |
| MaaCommonAssets（OCR 模型轉檔腳本與模型） | MIT（倉庫）；模型源自 PaddleOCR | 範本預設從這裡下載 `ppocr_v6` OCR 模型；我沒有逐一查證模型本身的授權，納入前再確認 | [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets) |
| **MXU** | **AGPL-3.0** | 開發期當 GUI 執行即可；**不要複製其程式碼**，打包散佈另議 | [MistEO/MXU](https://github.com/MistEO/MXU)（GitHub API） |
| **MFAAvalonia** | **GPL-3.0** | 同上；範本 CI 會把它打包進發佈檔，maalc 先不搬這段 | GitHub API |
| **MFAToolsPlus** | **GPL-3.0** | 同上 | [README](https://github.com/SweetSmellFox/MFAToolsPlus) |
| M9A、MaaEnd、MaaLimbus、create-maa-project | AGPL-3.0 | 可讀不可抄（ADR 0001） | GitHub API |
| MaaInspector | GitHub 未標示授權 | 無授權即預設保留所有權利，不使用 | GitHub API |

> 備註：MXU／MFAAvalonia 作為獨立程式讀取 `interface.json`，與 maalc 的 Pipeline、Agent 之間只透過檔案與 socket 溝通，maalc 本身不需要因此改授權。不過「發佈時把 GUI 與 maalc 放進同一個壓縮包」在 AGPL／GPL 下要附對方原始碼與授權，這屬於打包範圍，v1 先不處理；這裡不構成法律意見。

## 未解決／未驗證

- MFAToolsPlus 的實際功能（有無 720p 截圖、ROI 工具）：README 與原始碼我只看了目錄，沒執行，標為「不採用」。
- `ReplayController` 的 JSONL 格式與 Agent 搭配時的完整行為，只讀了控制器原始碼，沒實際錄過。
- `maa-tools test` 的 `box` 比對方式（`checkRect` 要求實際框落在期望框內）只讀程式碼，沒實跑。
- MaaDebugger 新版（`@weinibuliu/maa-debugger`）未評估。
- 範本裡 OCR 模型 `ppocr_v6` 是否含英文辨識、是否夠用於 Limbus 的英文畫面，屬於辨識策略題，不在本 ticket 範圍。
