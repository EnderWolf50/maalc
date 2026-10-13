# 流程放 Pipeline hub，決策放 Agent

鏡牢的流程寫在 Pipeline：由 `MirrorHub` 節點把每種鏡牢畫面都列進 `next` 並標上 `[JumpBack]`，每個畫面處理完都回到 hub，重新判斷畫面。地圖節點、飾品、主題包、商店這類需要判斷的選擇，才寫成 Agent 的 custom action 或 custom recognition。每種畫面的辨識各自寫在自己的 Pipeline 節點，不用單一 custom recognition 對全螢幕做分類。

這樣選，是因為它是 MaaFramework v5 建議的狀態分派寫法（M9A、MaaEnd 都這樣做），從任何畫面啟動都能自動接手，也能直接用 VS Code 擴充和 `maa-tools test` 除錯。MaaLimbus 和 AALC 的做法是把整輪鏡牢寫在程式碼迴圈裡：MaaLimbus 的 Pipeline 只剩佔位節點，Python 約 1.9 萬行；AALC 是一長串 if。兩者都越長越脆弱，所以我們不採用。

## Consequences

- `next` 的順序就是優先權。全域彈窗排在最前面，例如 Retry、連線中、教學提示、每週重置通知、無限鏡牢彈窗；各子流程也引用同一組節點。
- 從任何畫面回到鏡牢入口頁的導航，另外做成一串節點，不放進 `MirrorHub`；做法仿照 MaaEnd 的 SceneManager。入口頁負責分流：開新局、按 Resume 接續、領取上局沒領的獎勵、處理過期的局。
- 卡住偵測與重啟遊戲另外設計，見 #14。
