# 用 MaaFramework 重寫 AALC（僅模擬器）可行性評估

> 依據：AALC [b0f4393](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0)、MaaFramework [f21a0b8](https://github.com/MaaXYZ/MaaFramework/tree/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f)（最新 release v5.14.3，2026-10-10）。AALC 細節見 [aalc/](aalc/README.md)。

## 結論

可行。框架本身已經涵蓋大部分底層工作；真正的工作量在 Python Agent（鏡牢決策邏輯）和素材轉換。主要風險在授權與遊戲行為驗證，不在技術能力。

## AALC 模組 → MaaFramework 對應

| AALC | MaaFramework | 說明 |
|---|---|---|
| 模擬器截圖／輸入（MuMu IPC、ADB、minitouch，約 3,000 行，[02](aalc/02-recognition-and-input.md)） | Adb 控制器，自動選最佳方式 | 截圖 `EmulatorExtras` 支援 MuMu 12、雷電 9、AVD；輸入優先序 `EmulatorExtras > Maatouch > MinitouchAndAdbKey > AdbShell`（[2.4-控制方式说明.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/2.4-控制方式说明.md)）。這部分整層可以刪掉 |
| `P`／`Enter` 按鍵（AALC 在模擬器上送 `input keyevent` 或 MuMu 原生 key，[simulator_control.py:L613-L623](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/simulator/simulator_control.py#L613-L623)） | `ClickKey` 動作 | 用 Android keycode |
| 畫面判斷狀態機、斷點接續（[10](aalc/10-mirror-dungeon-overview.md)） | Pipeline 的 `next` 清單 | 原本就是「看畫面決定下一步」，和 Pipeline 模型天然吻合 |
| 模板比對（灰階 `TM_CCOEFF_NORMED`，2560×1440 基準） | `TemplateMatch` | MaaFramework 要求模板「無損原圖縮到 720p 後裁切」（[1.1-快速开始.md:L167](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/1.1-快速开始.md)），需轉換，見下 |
| ORB 特徵比對（尋路備援） | `FeatureMatch` | |
| 顏色判斷（`get_floor` 紅色 CLEAR） | `ColorMatch` | |
| RapidOCR | `OCR`（PaddleOCR ONNX：`det.onnx`／`rec.onnx`／`keys.txt`） | 同源模型；中文／英文模型需另備 |
| YOLO 節點偵測 `best.onnx` | `NeuralNetworkDetect` | **可直接沿用**，見下 |
| Dijkstra 尋路、商店購買與合成、飾品優先序、金錢 OCR 解析、隊伍輪替 | Agent（Python）的 Custom Recognition／Action（[1.3-Custom&Agent.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/1.3-Custom&Agent.md)） | 工作量主體，可參考 [13](aalc/13-md-ego-gifts.md)、[14](aalc/14-md-navigation.md) 移植 |
| 重啟遊戲 | `StartApp`／`StopApp` | |
| PySide GUI、設定、排程（[01](aalc/01-architecture.md)） | ProjectInterface V2 + 現成 GUI（MXU、MFAAvalonia） | 不必自己寫 GUI |

### YOLO 模型相容性（已對照原始碼確認）

- `best.onnx` 輸入 `[1,3,544,960]`、輸出 `[1,11,10710]`，metadata `end2end=False`、`nms=False`。雖然名為 YOLO26n，輸出格式與 YOLOv8／v11 相同（4 個框座標 + 7 類），符合 MaaFramework 的支援範圍（[3.1-任务流水线协议.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.1-任务流水线协议.md#neuralnetworkdetect)）。
- 前處理一致：MaaFramework 從模型讀輸入尺寸，等比縮放並置中補 114 灰邊（[NeuralNetworkDetector.cpp:L78-L100](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L78-L100)），並轉 RGB、除以 255（[VisionUtils.hpp:L284-L297](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/VisionUtils.hpp#L284-L297)）。AALC 的作法相同（[search_road.py:L424-L440](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L424-L440)）。720p 輸入縮放比 0.75，結果是 960×540 加 4 px 補邊，和 AALC 從 1440p 縮放的結果相同。
- 類別名稱已寫在 metadata 的 `names`，MaaFramework 會自動讀取。

## 需要另外研究或驗證的項目

1. **授權（最優先）**：AALC 是 AGPL-3.0。直接沿用它的模板圖、`best.onnx`（模型本身也標示 Ultralytics AGPL-3.0），新專案就必須是 AGPL。不想受此限制就得自己截圖、自己訓練模型。MaaFramework 本身是 LGPL-3.0，不強制專案授權。
2. **現有同類專案**：
   - [sairaisaika/MaaLimbus](https://github.com/sairaisaika/MaaLimbus)：2026-10-01 建立、至今仍活躍，同樣是 MaaFramework + Python Agent + MXU。README 自述已在 MuMu 英文畫面跑通「困難鏡牢五層 → 領獎 → 換隊再入場」，但商店、合成和長時間無人值守尚未完成。授權 AGPL-3.0。
   - [NekoyashikiSuzu/MaaLBC](https://github.com/NekoyashikiSuzu/MaaLBC)：2026-05 建立，之後沒有更新。
   - [HSLix/LixAssistantLimbusCompany](https://github.com/HSLix/LixAssistantLimbusCompany)：另一個大型 Limbus 助手（1.3k stars，AGPL-3.0），也可參考。

   動工前應先決定：貢獻 MaaLimbus、fork 它，還是從零開始。
3. **素材轉換管線**：AALC 的 642 張 PNG 中，檔名以 `assets.png` 結尾的是整張 2560×1440 透明底圖，執行時取非黑區 bbox 當搜尋範圍（[02](aalc/02-recognition-and-input.md)）。轉換方式是縮 0.5 倍並依 bbox 裁切，bbox 加上 AALC 的寬容度（`clam` ±30、`normal` ±100）換算成 `roi`。縮到 720p 後小字模板可能失真，這類應改用 OCR；需要寫腳本批次轉換並抽樣驗證門檻。
4. **手機版與 PC 版畫面差異**：AALC 在模擬器上沿用同一套模板，代表 UI 版面相同，但仍要確認以下幾點，這些是 AALC 研究沒涵蓋的 Android 特有流程：
   - Android 客戶端的套件名稱
   - 首次啟動時的資源下載與登入畫面
   - 模擬器解析度是否必須是 16:9
5. **AALC 已知缺陷不要照抄**：見 [99](aalc/99-open-questions.md) A 類。尤其是必買／必棄／公式清單在 AALC 現行版本實際上是空的，所以 AALC「實際的行為」和「設計上的行為」不同；移植時以設計意圖為準。
6. **設定複雜度**：AALC 的 `TeamSetting` 每隊有數十個欄位（[11](aalc/11-md-team-formation.md)、[13](aalc/13-md-ego-gifts.md)）。ProjectInterface V2 的選項只有 `select`／`input`／`checkbox`，飾品清單這類結構化設定要麼塞進 `input`，要麼讓 Agent 讀自己的設定檔。這部分需要設計。

## 不需要再研究的

模擬器控制層（原本考慮補寫的 `04-simulator.md`）：這層改由 MaaFramework 負責，AALC 的實作已經沒有參考價值。
