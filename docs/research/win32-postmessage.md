# Limbus Company（Windows 版）是否接受 PostMessage 輸入

> 依據：AALC [b0f4393](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0)、LixAssistantLimbusCompany（`main`，2026-10-13 取得）、MaaFramework [f21a0b8](https://github.com/MaaXYZ/MaaFramework/tree/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f)。沒有實機測試，結論全部來自原始碼與 commit 紀錄。

## 結論

| 輸入 | 純 PostMessage 能否被接受 | 信心 |
|---|---|---|
| 鍵盤（`P`、`Enter`、`Esc`） | 能，但 lParam 必須帶正確 scan code | 高：兩個專案都在用，AALC 有修復紀錄 |
| 滑鼠點擊、拖曳 | 很可能不能：遊戲似乎讀真實游標位置，而不是訊息裡的座標 | 中：兩個專案獨立得出同樣做法，但沒人留下「純 PostMessage 失敗」的明文紀錄 |

## 鍵盤：可以

- AALC 背景模式送鍵盤時只用 `PostMessage(WM_KEYDOWN/WM_KEYUP)`，不移動游標（[input.py:L575-L600](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/input.py#L575-L600)）。
- 遊戲升級後曾經失效。commit [467f0f3](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/467f0f3)（2026-05-28，「修复游戏更新后后台按键消息无效」）的註解寫：「Unity 6+ 會校驗 scan code 和 extended flag，固定 `0x00000001` / `0xC0000001` 的消息會被忽略」。修法是在 lParam 帶入 `MapVirtualKey` 算出的 scan code；方向鍵這類 extended key 另外設第 24 位元。之後 [ffc0ef5](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/ffc0ef5) 又修正細節。
- Lix 的 `background_key_press` 同樣是純 `PostMessage`，lParam 為 `(scan_code << 16) | 1`（`lalc_backend/input/game_keyboard.py`）。
- **MaaFramework 的 PostMessage 鍵盤符合條件**：`make_keydown_lparam` 帶 scan code，`make_keyup_lparam` 另設第 30、31 位元（[InputUtils.h:L212-L226](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/source/MaaWin32ControlUnit/Input/InputUtils.h#L212-L226)）。它不設 extended flag，對 `P`、`Enter`、`Esc` 沒影響，但方向鍵可能失效。

## 滑鼠：很可能不行

兩個專案的「背景點擊」都會先移動真實游標，再送按鍵訊息：

- **AALC** `BackgroundInput.mouse_click` 的順序是：`SetCursorPos` → 送 `WM_ACTIVATE` → `PostMessage(WM_LBUTTONDOWN/UP)` → 把游標移回原位（[input.py:L347-L376](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/input.py#L347-L376)、[input.py:L662-L683](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation/input_handlers/input.py#L662-L683)）。拖曳也是以 `SetCursorPos` 逐步移動游標。
- AALC 為了避免動游標，另外做了 `WindowMoveInput`：移動遊戲視窗，讓目標點對準目前的游標（commit [cb9d893](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/cb9d893)，「基于窗口移动的后台点击方式」）。這和 MaaFramework 的 `WithWindowPos` 同一思路。若訊息內的座標就有效，這個繞路沒有必要。
- **Lix** `background_click` 先 `SetCursorPos(screen_x, screen_y)` 再 `PostMessage(WM_LBUTTONUP/DOWN)`（`lalc_backend/input/game_click.py`）。外層還用 `BlockInput(True)` 包住，避免使用者在這段時間動到滑鼠（`lalc_backend/input/input_handler.py`）。
- MaaFramework 的 `WithCursorPos` 方式明文寫著是「專為檢測實際滑鼠位置的程式設計」（[2.4-控制方式说明.md](https://github.com/MaaXYZ/MaaFramework/blob/f21a0b8bdf1b2ab2461e980eeefa88b9bea75e8f/docs/zh_cn/2.4-控制方式说明.md)）。MaaLimbus 和 MaaEnd（同為 Unity 遊戲）的預設也都選這種。

推論：Limbus（Unity）讀取點擊位置時用的是游標實際位置，`WM_LBUTTONDOWN` 只提供「按下了」這個事件。純 PostMessage 點擊大概會落在游標當下所在處，而不是目標座標。

## 不搶游標的選項

| 方式 | 可行性 |
|---|---|
| 滑鼠 `PostMessageWithWindowPos`／`SendMessageWithWindowPos` + 鍵盤 `PostMessage` | 最可能可行：AALC 的 `WindowMoveInput` 用的是同一原理。代價是視窗會短暫閃動 |
| `AnchoredTouch`（合成觸控） | 未知：沒有專案驗證 Limbus 是否接受觸控輸入。另外不支援滾輪，視窗被遮擋時會閃約 70 ms |
| 純 `PostMessage` | 只有鍵盤可行 |
| 模擬器 | 不碰 Windows 游標，沒有這個問題 |

## 如何實測

在裝有 Limbus 的 Windows 上，分別用 MaaFramework 的 `PostMessage`、`PostMessageWithWindowPos`、`AnchoredTouch` 建立 Win32 控制器，各自執行以下兩件事，再截圖確認畫面是否變化：

1. 點擊主選單上一個會切換畫面的按鈕，執行時把游標放在遊戲視窗外。
2. 在戰鬥畫面按 `P`。
