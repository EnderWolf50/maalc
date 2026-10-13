# maalc

用 MaaFramework 自動化 Limbus Company 鏡牢的工具。這裡的用語以英文版遊戲畫面為準。

## 鏡牢

**局**：
從選隊開始、到領取結算獎勵為止的一次鏡牢挑戰，共五層。
_Avoid_: run（寫程式時可用）、輪、場

**暫停中的局**：
用 To Window 存檔離開、還沒結束的局。入口頁會顯示它的層數與難度，按 Enter 會出現 Resume 對話框。
_Avoid_: 中斷的局、held run

**難度**：
每一層的 NORMAL 或 HARD，在該層的主題包頁切換。一局之中，不同層的難度可以不同。
_Avoid_: 模式、困牢（指整局時）

**每週獎勵**：
入口頁的 Weekly Bonuses，每週三次，在領取結算獎勵時決定要不要使用。
_Avoid_: 困難次數、bonus

## 隊伍

**輪替**：
使用者排定的隊伍順序，bot 每完成一局就換下一隊。
_Avoid_: 輪換、rotation queue

**輪替游標**：
輪替中下一局要派的隊伍，是 Agent 狀態檔唯一保存的資料。
_Avoid_: 帳本、輪替位置
