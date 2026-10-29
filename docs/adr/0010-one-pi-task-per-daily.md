---
status: accepted（延續 ADR 0006）
---

# 每個日常一個 PI 任務，順序與排程交給 client

日常（經驗本、紐本、換腦啡肽模組、通行證任務、信箱、狂氣換腦啡肽）各是一個獨立的 PI 任務，和 `MirrorDungeon` 並列：`ExpLuxcavation`、`ThreadLuxcavation`、`AssembleModules`、`ClaimPassMissions`、`ClaimMail`、`ChargeEnkephalin`。任務的順序、啟用、排程與結束後動作都由 MXU／MFAAvalonia 的任務清單管，`settings.json` 不存一份；每個任務怎麼跑（次數、隊伍、重打次數）放在 `settings.json`，由設定 GUI 編輯，PI 不放使用者選項，延續 [ADR 0006](0006-settings-gui-writes-one-settings-file.md)。（#362，2026-10-26 定案）

每個任務從主畫面開始、回到主畫面結束，並重設 agent 的記憶體狀態，所以任務之間互不影響，任一任務也可以單獨跑。唯一的例外是 `ChargeEnkephalin` 的次數為 0（預設）：它什麼都不做、不動畫面，也就不走 `GoHome`，直接成功結束，下一個任務仍從上一個任務留下的主畫面開始（spec 01）。

## Considered Options

- **一個 `Chain` 任務，agent 依設定清單依序跑**：順序與啟用就得存進 `settings.json`，GUI 要自己做任務清單，也要重做排程。留到 GUI 自己負責執行（A2）時再做；那時可以疊在這些任務上，不必推翻它們。
- **在 PI 選項放次數與隊伍**：回到 ADR 0004 的固定欄位問題，不選。

## Consequences

- 清單怎麼串要看 client：任務正常做完必須以成功結束，client 才會繼續下一個。「局數已滿」「腦啡肽模組不夠而跳過」這類正常結束算成功；只有帳號層級的停止（維護、用戶端過舊）才清空 client 佇列。
- 排程和結束後動作不由 maalc 實作，只在 README 說明兩個 client 的設定。
- 兩個模擬器共用同一個帳號時，只在一個實例的清單勾選日常，避免重複花腦啡肽模組。
