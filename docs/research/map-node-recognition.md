# 不依賴 AGPL 的鏡牢地圖節點辨識方式

> 回答 [maalc#3](https://github.com/EnderWolf50/maalc/issues/3)。調查日期 2026-10-13。
> 依據：Ultralytics [f58f681](https://github.com/ultralytics/ultralytics/tree/f58f6818a79cecec674431c8c7d297ac012ab408) 與 [授權頁](https://www.ultralytics.com/license)、MaaFramework [f21a0b8](https://github.com/MaaXYZ/MaaFramework/tree/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f)、MaaNeuralNetworkCookbook [23c06b8](https://github.com/MaaXYZ/MaaNeuralNetworkCookbook/tree/23c06b8d5a9de39d1f273087516cb100cb0d3608)、AALC [b0f4393](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0)。
> **授權相關段落是對公開文件的整理，不是法律意見。** 有疑義的地方會明確標出。

## 結論

1. **不要用 Ultralytics 訓練或匯出的任何模型。** Ultralytics 官方立場是：用它訓練出來的模型，即使從零訓練、不用預訓練權重，也屬 AGPL-3.0，除非買 Enterprise License。這個說法在法律上能否成立有爭議，但在 MIT 專案裡賭這一點不划算。[ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md) 留下的「尚待查證」可以結案：**排除**。
2. **建議 v1 不用偵測模型，而是「Bus 定位 + 固定格位分類」。** 地圖是三列的格狀結構，相鄰節點相對 Bus 的位置固定（AALC 用的就是固定偏移），所以問題可以從「在整張圖找節點」簡化成「判斷幾個已知格位上是哪種圖示」。分類先用自製模板的 `TemplateMatch`；實測準確率不夠時，再換成 `NeuralNetworkClassify`（MaaNeuralNetworkCookbook 的分類範例是 MIT、純 PyTorch，跟 Ultralytics 無關）。
3. **真的需要整張地圖的偵測模型時**，用 Apache-2.0／MIT 的訓練框架（YOLOX、LibreYOLO 的 YOLOv9、MultimediaTechLab/YOLO 等），在匯出時加一層轉換，把輸出改成 MaaFramework 要的 `[1, 4+nc, N]`。MaaFramework 只看張量排列，不在乎模型是哪一家訓練的。

## 1. Ultralytics 訓練的權重是否受 AGPL 約束

### Ultralytics 的立場（一手來源）

- Repo 授權是 AGPL-3.0（[LICENSE](https://github.com/ultralytics/ultralytics/blob/f58f6818a79cecec674431c8c7d297ac012ab408/LICENSE)），README 說另有 Enterprise License，可「bypassing the open-source requirements of AGPL-3.0」（[README.md 授權段](https://github.com/ultralytics/ultralytics/blob/f58f6818a79cecec674431c8c7d297ac012ab408/README.md#-license)）。
- [授權頁 FAQ](https://www.ultralytics.com/license)「What license do I need to use Ultralytics YOLO?」原文：使用「Ultralytics YOLO code, models, architectures, training pipelines, or trained/fine-tuned models」時，必須「Open-source your entire project under AGPL-3.0, or Obtain an Ultralytics Enterprise License」，而且「This applies even if you: Train your own model from scratch / Do not use pretrained weights / Use YOLO only internally or for R&D」。
- 同頁「Are Ultralytics YOLO trained models licensed under the AGPL-3.0 license?」答：「Yes. All Ultralytics YOLO trained models fall under the AGPL-3.0 License by default. The AGPL-3.0 License covers the training code and the models produced by that training code.」
- 匯出器會把授權寫進模型：`exporter.py` 的 metadata 固定帶 `"license": "AGPL-3.0 License (https://ultralytics.com/license)"`（[ultralytics/engine/exporter.py:L983](https://github.com/ultralytics/ultralytics/blob/f58f6818a79cecec674431c8c7d297ac012ab408/ultralytics/engine/exporter.py#L983)）。所以 ONNX 匯出檔也一樣自帶 AGPL 聲明，AALC 的 `best.onnx` metadata 就是如此（[aalc/14 ONNX 細節表](aalc/14-md-navigation.md)）。

### 法律上的不確定處（不是法律意見）

- AGPL-3.0 第 2 節本身寫著：「The output from running a covered work is covered by this License only if the output, given its content, constitutes a covered work.」（[LICENSE:L146-L148](https://github.com/ultralytics/ultralytics/blob/f58f6818a79cecec674431c8c7d297ac012ab408/LICENSE#L146-L148)）。依此條文，用自己的資料訓練出的權重是否算「covered work」並不明確；Ultralytics 的 FAQ 主張的範圍（連「architectures」都算）比條文本身寬。
- 反方向的論點也存在：匯出的 ONNX 計算圖是 Ultralytics 程式碼按其模組結構產生的，權重又是其訓練程式的產物，主張它是衍生作品並非毫無根據。
- 沒有判例可以參考；權利人公開表態會主張權利。對 MIT 專案來說，結論是：**不論法律上誰對，用 Ultralytics 都會讓授權狀態有爭議**，違反 ADR 0001「素材與模型全部自製、不受 AGPL 約束」的目的。

### 一併排除的其他框架

| 專案 | 授權 | 備註 |
|---|---|---|
| [ultralytics/yolov5](https://github.com/ultralytics/yolov5) | AGPL-3.0 | 同一家，同樣立場 |
| [THU-MIG/yolov10](https://github.com/THU-MIG/yolov10) | AGPL-3.0 | 建在 Ultralytics 程式碼上 |
| [WongKinYiu/yolov7](https://github.com/WongKinYiu/yolov7)、[WongKinYiu/yolov9](https://github.com/WongKinYiu/yolov9) | GPL-3.0 | Copyleft，問題相同 |
| [meituan/YOLOv6](https://github.com/meituan/YOLOv6) | GPL-3.0 | 同上 |
| [open-mmlab/mmyolo](https://github.com/open-mmlab/mmyolo) | GPL-3.0 | 注意：MMDetection 本體是 Apache-2.0，但 MMYOLO 是 GPL |

授權皆以 GitHub API `repos/{owner}/{repo}` 的 `license.spdx_id` 查得（2026-10-13）。

## 2. MaaFramework `NeuralNetworkDetect` 實際要求什麼

文件只寫「支持由 YOLOv8 和 YOLOv11 导出的 ONNX 格式的模型，其他同样输入输出的 YOLO 模型理论上也可以支持」（[3.1-任务流水线协议.md#neuralnetworkdetect](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.1-任务流水线协议.md#neuralnetworkdetect)）。讀原始碼，真正的約束如下（[NeuralNetworkDetector.cpp](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp)）：

| 項目 | 要求 | 出處 |
|---|---|---|
| 輸入 | 一個 4 維 NCHW 輸入；寬高從模型讀，所以必須是**固定尺寸**（動態軸會讀到 -1） | [L70-L78](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L70-L78) |
| 前處理 | 等比縮放（只縮不放大，`scale ≤ 1`）、置中補 114 灰邊、BGR→RGB、除以 255，**不做 mean/std 正規化** | [L79-L101](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L79-L101)、[VisionUtils.hpp:L284-L297](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/VisionUtils.hpp#L284-L297) |
| 輸出 | 只讀第一個輸出，形狀 `[1, 4+nc, N]`：前 4 列是輸入像素座標下的 `cx, cy, w, h`，其後每列是一個類別的分數，**沒有 objectness 欄** | [L116-L133](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L116-L133) |
| 分數 | 直接當機率用，寫死先丟掉 `< 0.3` 的，所以模型要輸出已經 sigmoid 過的分數 | [L137-L144](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L137-L144) |
| NMS | 框架自己做，模型裡**不要**再含 NMS；不分類別，以「交集 ≥ 0.7 × 後者面積」判重 | [L175](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L175)、[VisionUtils.hpp:L185-L210](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/VisionUtils.hpp#L185-L210) |
| 類別名稱 | 可從 metadata 的 `names`／`name`／`labels`／`class_names` 讀 Python dict 字串，也可在 Pipeline 手填 `labels` | [L283-L361](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkDetector.cpp#L283-L361) |

也就是說，框架只管張量的排列。任何偵測器只要在匯出時包一層 `torch.nn.Module` 做「轉置、obj × cls、座標格式轉換、必要時把 0–1 輸入乘回 255 或做正規化」，就能輸出這個格式。這層轉換是自己寫的，授權跟著訓練框架走。

`NeuralNetworkClassify` 的要求更簡單：輸入同樣是固定尺寸 NCHW、RGB/255，**直接縮放到輸入尺寸**（不補邊）；輸出 logits，框架自己做 softmax（[NeuralNetworkClassifier.cpp:L57-L90](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaFramework/Vision/NeuralNetworkClassifier.cpp#L57-L90)）。

另一條路：Python Agent 的 Custom Recognition 可以自己呼叫 onnxruntime，輸出格式完全自訂（[1.3-Custom&Agent.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/1.3-Custom&Agent.md)）。代價是自己寫前後處理，也拿不到框架的除錯繪圖。

### MaaNeuralNetworkCookbook

- Repo 本身是 MIT（[LICENSE](https://github.com/MaaXYZ/MaaNeuralNetworkCookbook/blob/23c06b8d5a9de39d1f273087516cb100cb0d3608/LICENSE)）。
- **偵測食譜用的就是 Ultralytics**：`requirements.txt` 只有 `ultralytics`、`onnx`；`train.py` 是 `YOLO("data/yolo11n.pt")`，README 用 `yolo detect train` 與 `yolo export`（[NeuralNetworkDetect/](https://github.com/MaaXYZ/MaaNeuralNetworkCookbook/tree/23c06b8d5a9de39d1f273087516cb100cb0d3608/NeuralNetworkDetect)）。Repo 的 MIT 只涵蓋食譜文字與腳本，照著做出來的模型仍落在第 1 節的 Ultralytics 立場裡，**不能照抄這份食譜**。
- **分類食譜不依賴 Ultralytics**：純 PyTorch + torchvision transforms，自帶一個 GoogleNet 實作，用 `torch.onnx.export` 匯出（[NeuralNetworkClassify/](https://github.com/MaaXYZ/MaaNeuralNetworkCookbook/tree/23c06b8d5a9de39d1f273087516cb100cb0d3608/NeuralNetworkClassify)）。PyTorch 與 torchvision 是 BSD-3-Clause（[pytorch/vision](https://github.com/pytorch/vision)）。這條路授權乾淨。

### 授權寬鬆、可接上 MaaFramework 的偵測框架

| 框架 | 程式授權 | 預訓練權重 | 原生 ONNX 輸出 | 接上 MaaFramework 要做的事 |
|---|---|---|---|---|
| [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) | Apache-2.0 | repo release，同授權 | `[1, N, 5+nc]`，含 objectness，`decode_in_inference` 時座標已解碼（[yolo_head.py](https://github.com/Megvii-BaseDetection/YOLOX/blob/6ddff4824372906469a7fae2dc3206c7aa4bbaee/yolox/models/yolo_head.py)、[export_onnx.py](https://github.com/Megvii-BaseDetection/YOLOX/blob/6ddff4824372906469a7fae2dc3206c7aa4bbaee/tools/export_onnx.py)） | 包裝層：輸入 ×255 並轉 BGR（預設前處理不除 255、BGR、左上角補邊，見 [data_augment.py:L142-L156](https://github.com/Megvii-BaseDetection/YOLOX/blob/6ddff4824372906469a7fae2dc3206c7aa4bbaee/yolox/data/data_augment.py#L142-L156)）；輸出 `obj×cls` 後轉置成 `[1, 4+nc, N]`。repo 最後推送 2025-06，維護低 |
| [LibreYOLO/libreyolo](https://github.com/LibreYOLO/libreyolo) | MIT（程式） | 依模型而異，README 明說「not all of them are permissive」，要逐個看 HF 卡 | 有 YOLOv9、YOLOX、RT-DETR、D-FINE、DEIM 等，ONNX 匯出已驗證（[export_support.md](https://github.com/LibreYOLO/libreyolo/blob/89efbe87231d2efb0ac05a329f1aeb15e90d2cbe/docs/export_support.md)） | 輸出排列**未實測**，需匯出後檢查；必要時同樣加包裝層。API 與 Ultralytics 相近，讀 YOLO 格式資料集 |
| [MultimediaTechLab/YOLO](https://github.com/MultimediaTechLab/YOLO)（YOLOv9 官方 MIT 重寫） | MIT（README：「official YOLO model implementation with an MIT License」） | 未逐一確認 | 有 ONNX 推論路徑（`task.fast_inference=onnx`） | 輸出排列未實測 |
| [PaddlePaddle/PaddleDetection](https://github.com/PaddlePaddle/PaddleDetection)（PP-YOLOE、RT-DETR） | Apache-2.0 | 同 | 需 Paddle2ONNX，輸出多為兩個張量或含 NMS | 包裝較麻煩，要多一層框架 |
| [lyuwenyu/RT-DETR](https://github.com/lyuwenyu/RT-DETR)、[Peterande/D-FINE](https://github.com/Peterande/D-FINE)、[roboflow/rf-detr](https://github.com/roboflow/rf-detr) | Apache-2.0 | 同（rf-detr 部分模型另有授權，需逐個確認） | DETR 系：固定數量 query、輸出 boxes／logits 分開 | 包裝層把 `[1, Q, 4]` + `[1, Q, nc]` 拼成 `[1, 4+nc, Q]`、座標從 0–1 換成輸入像素。DETR 不需 NMS，框架的 NMS 只會多做一次去重 |
| [open-mmlab/mmdetection](https://github.com/open-mmlab/mmdetection) | Apache-2.0 | 同 | 經 mmdeploy 匯出 | 框架龐大、2024 後幾乎停更，不建議 |
| [hank-ai/darknet](https://github.com/hank-ai/darknet) | Apache-2.0 | — | 原生非 ONNX，需轉換 | 不建議 |

授權與最後推送日期取自 GitHub API（2026-10-13）。

**注意**：預訓練權重是另一個授權層。用 COCO 預訓練權重做微調時，要確認該權重本身的授權；7 類 UI 圖示這種單純目標，從零訓練也可行，就能避開這一層。

## 3. 不用模型：模板或特徵比對是否可行

### 節點圖示長什麼樣（僅作事實描述）

AALC 的備援模板（[assets/images/default/share/mirror/road_in_mir/](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/images/default/share/mirror/road_in_mir)，2560×1440 下裁切）顯示：

- 每種節點是一個扁平、單色系、帶水平掃描線紋理的剪影：戰鬥是金色的交叉刀劍，事件是白色問號，危險遭遇是米色多面體；各類形狀差異大，顏色也不同。
- 尺寸在 1440p 下約 68–134 px（`focused_encounter` 68×87、`event` 79×103、`battle` 119×84、`shop` 134×84）。換到 maalc 的 720p 基準約 34–67 px，**低於 `FeatureMatch` 文件建議的 64×64**（[3.1-任务流水线协议.md#featurematch](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/3.1-任务流水线协议.md#featurematch)），所以特徵比對不是好選擇；`TemplateMatch` 在固定縮放下比較適合。
- 地圖預設縮放下，欄距 520 px、列距 437 px（1440p），相鄰節點相對 Bus 的偏移固定（[aalc/14 §3.2 步驟 4、7](aalc/14-md-navigation.md)）。

### AALC 為什麼改用模型

從 [search_road.py 的 git 歷史](https://github.com/KIYI671/AhabAssistantLimbusCompany/commits/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py)看：

1. **2025-02**：先做的是 ORB 特徵比對，對 Bus 相鄰格位評分（[70b39ac](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/70b39ac643)「添加特征匹配功能用于镜牢寻路」）。這就是今天的備援一。
2. **2025-09-06**：一天內加入 YOLO 節點偵測、路線分組與整張地圖尋路（[7e858c1](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/7e858c1d90)、[85b0d2d](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/85b0d2df1d)、模型 [269d9d3](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/269d9d3481)）。commit 訊息只寫做了什麼，**沒有寫為什麼放棄特徵比對**。
3. **2026-08**：[AALC#868](https://github.com/KIYI671/AhabAssistantLimbusCompany/pull/868) 把模型換成 YOLO26n、輸入 960，並附上數據：mAP50 從 86.04% 升到 98.67%；但逐類別數字（同 PR 表格）仍只有 84–94%，舊 YOLOv8 的 `abnormality` 只有 41.24%。同一個 PR 也把連線辨識從 LSD 改成 `up/mid/down` 模板（[AALC#838](https://github.com/KIYI671/AhabAssistantLimbusCompany/issues/838)：LSD 約 10% 節點沒有路可到）。
4. 模型也會錯：[AALC#430](https://github.com/KIYI671/AhabAssistantLimbusCompany/issues/430) 維護者回覆「目前的识别模型有时会把普通战斗节点识别为boss节点」。

**推論**（非作者說明）：AALC 換模型的動機是要「看整張地圖、建整張路線圖再跑 Dijkstra」，偵測器一次給出所有節點的位置與類別，這是模板逐格比對做不方便的事。不是因為模板認不出圖示。另外，連 AALC 自己也是用模板確認連線，而且維護者提到連線圖片會因位置而變形（[AALC#838 討論](https://github.com/KIYI671/AhabAssistantLimbusCompany/issues/838)）。

### maalc 需要整張地圖嗎

- 困難鏡牢（v1 驗收目標）AALC 本來就只看兩欄（`init_road` 丟掉 `column_number > 2` 的連線，[aalc/14 §3.2 步驟 5](aalc/14-md-navigation.md)）。
- 只看兩欄時，候選格位最多 3 + 9 個，位置都能由 Bus 推出來。這種「固定位置判斷類別」正是 `TemplateMatch` 加小 ROI，或 `NeuralNetworkClassify` 的適用範圍；不需要偵測器。
- 普通模式補虛擬欄求全圖路徑的做法，是偵測器方案的附加價值，但 v1 只要求困難鏡牢。

**可行性判斷**：在固定預設縮放、已知格位的前提下，模板比對預期可行，但**沒有實測**。我手上沒有 Android 720p 的地圖截圖。主要未知是：選取或滑鼠懸停時圖示是否變色或放大、路線線條是否壓到圖示、異想體與 Boss 圖示的樣子（AALC 沒有這兩類模板）、模擬器縮放造成的模糊。這些都要先截圖驗證。

## 4. 方案比較

| 方案 | 授權 | 工作量 | 風險 | 建議 |
|---|---|---|---|---|
| A. Ultralytics 自己訓練 YOLO | 官方主張 AGPL；法律上有爭議 | 低（食譜現成） | **授權爭議**，違反 ADR 0001 | **排除** |
| B. Bus 定位 + 固定格位 `TemplateMatch` | 全部自製，MIT | 低：每類 1–3 張模板，加上 Agent 依 Bus 算 ROI | 圖示狀態變化、未知新圖示；格位推算依賴預設縮放 | **v1 首選** |
| C. 固定格位 `NeuralNetworkClassify`（自訓 CNN，PyTorch） | BSD／MIT，乾淨 | 中：每類約數百張裁切（可用方案 B 的結果半自動標註）、訓練腳本 | 資料收集；模型小，CPU 推論便宜 | B 實測不夠準時的升級路線 |
| D. 整張地圖偵測（YOLOX／LibreYOLO-YOLOv9 等，加輸出轉換層） | Apache-2.0／MIT（權重要逐個確認） | 高：框選標註、訓練、轉換層、驗證輸出排列 | 轉換層寫錯會靜默失準；框架維護度不一 | 僅在需要全圖路徑（普通模式最佳化）時考慮，v1 不做 |
| E. 盲走（不辨識，依序試點 Bus 相鄰格） | 無授權問題 | 極低 | 會走進危險遭遇，回合變長 | 只當最後備援（AALC 備援二亦如此） |

### 建議落地順序

1. 先截 Android 720p 地圖畫面（含每種節點、懸停或選取狀態、Boss、異想體），確認圖示的實際外觀與格位偏移。
2. 實作方案 B：Pipeline 用 `TemplateMatch` 找 Bus，Agent 依偏移算出各格位 ROI，再對每格跑一組節點模板；認不出的格位記為 `unknown` 權重。
3. 用多輪困難鏡牢的截圖統計誤判率。不達標才做方案 C，並用方案 B 的結果當初始標註。
4. 方案 D 留待 v1 之後。

## 未解問題

- Android 客戶端的地圖縮放、懸停效果與 Boss／異想體圖示，需實機截圖確認。
- LibreYOLO 與 MultimediaTechLab/YOLO 匯出的 ONNX 輸出排列未實測。
- Ultralytics 權重的 AGPL 主張沒有判例；本文只依權利人公開立場做風險判斷。
