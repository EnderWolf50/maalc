---
status: accepted（補充 ADR 0006）
---

# 設定 GUI 維持 Tauri；A2 要常駐時優先改用 GPUI

設定 GUI（[ADR 0006](0006-settings-gui-writes-one-settings-file.md)）用 Tauri 2 + React，執行時會帶出 WebView2。擔心的是它跟模擬器搶記憶體，以及安裝包大小。2026-10-23 在 Windows 11 實測，量法都一樣：啟動後等 8 秒，合計整個程序樹的 PrivateMemorySize64，GPU 記憶體取 `\GPU Process Memory(pid_*)\Dedicated Usage`。

把隊伍頁（`gui/src/Teams.tsx`）用三個原生 Rust 框架各做一版，寫死範例資料，三版花差不多的工夫調樣式，視窗都是 1100×760：

| 框架 | exe | Private | GPU 專用 | UI 程式碼 |
|---|---|---|---|---|
| Tauri 2（現況，7 個程序） | 5.7 MB | 218–221 MB | 48 MB | 367 行 TSX + 240 行 CSS |
| egui 0.37（glow） | 6.0 MB | 118–120 MB | 35 MB | 623 行 |
| Slint 1.18 | 14.9 MB | 106–107 MB | 52 MB | 507 行 `.slint` + 186 行 Rust |
| GPUI（gpui-kit 0.7.3） | 21.6 MB | 118 MB | 25 MB | 419 行 |

- 原生框架大約省下一半的 private memory，三者之間差距很小。安裝包的大頭是 MaaFramework（約 86 MB），GUI 換成哪一個都不會明顯改變總大小。
- 調過樣式後，三版外觀都接近 Tauri 版。「預設很醜」只是預設值的問題。
- egui 預設用 wgpu 渲染，在更簡單的表單上就要 459 MB private 和約 258 MB GPU 記憶體，所以一定要改用 glow。
- 三個框架都能做拖放排序，各約 15 行，插入位置的計算另外共用。用 cua-driver 在背景拖曳，Slint 和 GPUI 都收得到；egui 能收到背景點擊，但收不到背景拖曳的座標和放開事件。
- GPUI 的 Button、Select、Input、Checkbox 改主題就能用，程式碼最少。egui 要自己畫可展開面板、fieldset 標題和漸層。Slint 的內建 Fluent 元件換不了配色，最後下拉選單、核取方塊、按鈕、輸入框都自己寫。

決定：

- A1 維持 Tauri。GUI 只編輯設定，存好就能關掉，bot 執行時它不佔記憶體。
- 到了 A2，如果 GUI 也負責執行、必須一直開著，優先改用 GPUI：元件最完整，改寫成本最低，也能用 cua-driver 在背景自動測試。在意包體就改選 egui（glow），代價是樣式要自己畫，背景拖曳也測不了。

## Considered Options

- **Slint**：記憶體最低，但多出來的幾 MB 不足以抵掉自己寫元件的成本。另外它是 GPLv3、免版稅授權、商業授權三選一，跟本專案的 PolyForm Noncommercial 能不能並用還沒確認。
- **iced、Avalonia**：沒有實測。iced 沒有內建表格；Avalonia 要帶 .NET runtime，包體和記憶體都不會比 Tauri 小。
- **現在就換**：省下的約 100 MB，只有在 GUI 常駐時才有意義。

## Consequences

- A2 的選型直接引用這份實測，不必重做。數字來自寫死資料的原型頁，不是完整的應用程式；GPUI 的 API 還在跟著 Zed 一起變，到時要用當下的版本再量一次。
- 原型用完即丟，沒有放進 repo。
