# maalc v1 規格

這份規格寫出 maalc v1 要做什麼。設計理由見 [ADR](../adr/)，用語見 [GLOSSARY](../../GLOSSARY.md)，討論過程見 [map #1](https://github.com/EnderWolf50/maalc/issues/1) 底下的各個 ticket。每條規則都註明來源 ticket。

| 章節 | 內容 |
|---|---|
| [00 總覽](00-overview.md) | 目的、v1 範圍、Out of scope 與 Deferred、目標環境、技術選型 |
| [01 架構](01-architecture.md) | `MirrorHub`、入口導航與分流、Pipeline 與 Agent 的分工、中途接續、一局的流程 |
| [02 畫面](02-screens.md) | 每個畫面的辨識方式、處理方式與下一個畫面 |
| [03 決策規則](03-decisions.md) | 選隊與輪替、難度、編隊、星光、主題包、選路、戰鬥、事件、獎勵卡、飾品、商店、結算 |
| [04 設定](04-settings.md) | 設定檔結構：執行選項、方案、隊伍欄位、覆寫、檢查、介面語言、狀態檔 |
| [05 遊戲資料](05-game-data.md) | 每季更新的資料檔：主題包清單與預設方案、事件覆寫表、試煉表、選路權重 |
| [06 卡住與恢復](06-recovery.md) | 卡住的判定、L1–L3、上限、停止與通知 |
| [07 素材與測試](07-assets-and-testing.md) | 截圖與模板、門檻驗證、OCR、測試策略、驗收標準、參考環境 |

各章最後的「未決」列出還沒定案的問題；定案後，會改寫成正文並註明來源。
