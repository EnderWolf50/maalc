# 99 未解問題與疑似缺陷總表

> 原始碼版本：[b0f4393](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0)。本表彙整各章「未解問題」一節，依性質分類；每列只寫結論，證據與行號連結見來源章節。編號 `01-3` 表示 [01](01-architecture.md) 未解問題第 3 項。

已複核的五項主要缺陷見 [README 重要發現](README.md#重要發現疑似缺陷已由協調者對照原始碼複核)。

## A. 疑似缺陷（讀原始碼即可判定）

| 編號 | 問題 | 影響 |
|---|---|---|
| [10-1](10-mirror-dungeon-overview.md#14-未解問題)、[11-1](11-md-team-formation.md#未解問題)、[01-2](01-architecture.md#15-未解問題) | `onetime_mir_process` 吞掉所有例外，失敗不扣次數、不輪替；`unableToFindTeamError` 也被吞 | 隊名錯誤時可能無限重試同一隊 |
| [13-1](13-md-ego-gifts.md#11-未解問題) | `tasks/mirror/__init__.py` 走舊路徑 `assets/images/share/`，自 [ebb6629](https://github.com/KIYI671/AhabAssistantLimbusCompany/commit/ebb662926301e8407bf187b6f53419094475f927) 起必買／必棄／公式清單為空 | 商店購買與公式合成退化 |
| [13-6](13-md-ego-gifts.md#11-未解問題)、[13-7](13-md-ego-gifts.md#11-未解問題) | 第二體系條件在 `mirror.py` 與 `in_shop.py` 相反；`second_system_action[0] is True` 對 `int` 恆假；`[2]` 無消費端 | 第二體系四級合成可能永不觸發 |
| [12-3](12-md-battle.md#未解問題) | `to_battle()` 按鈕持續存在時不遞減 `loop_count` | 可能無限迴圈 |
| [12-6](12-md-battle.md#未解問題) | `mouse_action_interval // 1.5` 用整除，預設 0.5 → 0.0 | 防禦點擊無間隔 |
| [12-2](12-md-battle.md#未解問題) | `Battle.first_battle` 從未設為 True | 首通扣次數邏輯為死碼 |
| [12-4](12-md-battle.md#未解問題) | `to_battle()` 改 `auto.model` 後不還原 | 後續匹配範圍被放大 |
| [03-1](03-daily-tasks.md#12-未解問題) | `get_pass_prize()` 的 `last_try` 從不為 True，`mail_pos` 可能為 None | TypeError 或無限迴圈 |
| [03-2](03-daily-tasks.md#12-未解問題) | 葛朗台判斷 `minute >= 5 and seconds >= 20`，6:10 判為 False | 與文件「超過 5 分 20 秒」不符 |
| [03-3](03-daily-tasks.md#12-未解問題) | 紐本「只識別右半螢幕」用 `set_win_size / 2`（高度） | 疑似筆誤 |
| [02-1](02-recognition-and-input.md#17-未解問題) | `my_crop` 單目標回傳裁切內座標、多目標加偏移 | 呼叫端可能點錯位置 |
| [02-2](02-recognition-and-input.md#17-未解問題)、[14-3](14-md-navigation.md#11-未解問題) | ORB 在 `set_win_size > 1440` 時放大而非縮回 | 2160p 下尋路備援一準確度存疑 |
| [02-3](02-recognition-and-input.md#17-未解問題) | `get_screenshot_crop` 後 `self.screenshot` 保持彩色 | 後續灰階匹配被吞成「找不到」 |
| [02-6](02-recognition-and-input.md#17-未解問題) | `take_screenshot` 回 None 時不更新時間戳 | 呼叫端可能無節流空轉 |
| [02-8](02-recognition-and-input.md#17-未解問題) | `background_screenshot` 的 `finally` 可能用到未賦值的 `old_obj` | 極端情況 `UnboundLocalError` |
| [11-2](11-md-team-formation.md#未解問題) | 依名稱找隊是子字串比對，`编队#1` 命中 `编队#1x` | 改名後可能選錯隊 |
| [11-6](11-md-team-formation.md#未解問題) | `clean_team` 無逾時 | 找不到錨點時卡住 |
| [13 §9](13-md-ego-gifts.md#9-失敗與續跑) | `acquire_ego_gift` 主迴圈無次數上限，例外只 log 後 `continue` | 可能卡在獲取飾品頁 |
| [14-1](14-md-navigation.md#11-未解問題) | 困難模式丟掉 `column_number > 2` 連線，但 boss 可見時只找 boss | Dijkstra 回空路徑、落入備援 |
| [14-5](14-md-navigation.md#11-未解問題) | 刷新次數用完時「選最大權重」分支不會觸發 | 30 輪後 `back_init_menu`，整趟放棄 |
| [10-5](10-mirror-dungeon-overview.md#14-未解問題) | 主迴圈只有「都不符 250 次」計數，沒有同畫面看門狗 | handler 命中卻不推進時卡住 |
| [10-4](10-mirror-dungeon-overview.md#14-未解問題) | `hard_reward_eligible` 只取自設定，不從畫面推導 | 中途接續時難度判斷可能錯 |
| [01-1](01-architecture.md#15-未解問題) | `my_script_task.exception` 存下但無人讀取 | 專用例外導致靜默中止 |

## B. 需實機驗證（遊戲行為或執行環境，原始碼無法回答）

| 編號 | 問題 |
|---|---|
| [10-2](10-mirror-dungeon-overview.md#14-未解問題) | `re_start()` 放棄後是否一定出現 `battle_statistics` |
| [10-6](10-mirror-dungeon-overview.md#14-未解問題) | `get_floor` 紅色 CLEAR 閾值是否受 HDR／渲染比例影響 |
| [10-7](10-mirror-dungeon-overview.md#14-未解問題) | `to_window` 左側 200px 的按鈕是什麼 |
| [11-3](11-md-team-formation.md#未解問題) | 依序號模式的捲動常數（400 / 362.5 / 375）在其他解析度是否成立 |
| [11-4](11-md-team-formation.md#未解問題)、[13-3](13-md-ego-gifts.md#11-未解問題) | 星光卡、初始飾品重複點擊是 toggle 還是冪等 |
| [11-5](11-md-team-formation.md#未解問題) | 星光餘額不足時遊戲行為；GUI 費用估算是否正確 |
| [11-7](11-md-team-formation.md#未解問題)、[11-8](11-md-team-formation.md#未解問題)、[11-9](11-md-team-formation.md#未解問題) | `identify_assets + (0,600)`、`check_team` 的 `a/b`、`enter_mirror_confirm` 的語意 |
| [12-1](12-md-battle.md#未解問題)、[12-7](12-md-battle.md#未解問題) | 全滅畫面中間選項；陣亡放棄後回到哪個畫面 |
| [13-2](13-md-ego-gifts.md#11-未解問題)、[13-4](13-md-ego-gifts.md#11-未解問題) | 商店已售商品是否移到列表尾端；升級頁預設選中與排序選項 |
| [14-2](14-md-navigation.md#11-未解問題) | 只有 2 列時 TOP/BOTTOM 判定是否依賴固定地圖形狀 |
| [14-4](14-md-navigation.md#11-未解問題) | 事件判定 OCR 備援是否接近盲點擊 |
| [02-4](02-recognition-and-input.md#17-未解問題)、[02-9](02-recognition-and-input.md#17-未解問題) | 背景截圖路徑的 DPI 感知；背景模式仍移動真實游標 |
| [01-3](01-architecture.md#15-未解問題) | 排程啟動時 HDR 對話框會無限等待 |
| [01-5](01-architecture.md#15-未解問題)、[01-6](01-architecture.md#15-未解問題) | 單一實例埠 62333 被佔用；兩行程同時寫 `config.yaml` 的競態 |
| [03-5](03-daily-tasks.md#12-未解問題)、[03-6](03-daily-tasks.md#12-未解問題)、[03-7](03-daily-tasks.md#12-未解問題) | `all_in` 語意；經驗本／紐本失敗後的恢復死角 |

## C. 資產、主題與語言覆蓋缺口

| 編號 | 問題 |
|---|---|
| [10-3](10-mirror-dungeon-overview.md#14-未解問題) | `claim_forfeit_assets` 只有 en、`use_enkephalin_assets` 無 zh_cn |
| [13-8](13-md-ego-gifts.md#11-未解問題) | `return_assets.png` 只有 en，中文客戶端「回商店主頁」可能一直失效 |
| [12-8](12-md-battle.md#未解問題)、[03-8](03-daily-tasks.md#12-未解問題) | 戰鬥模板與 `retry.png` 大多沒有 dark 版本 |
| [13-5](13-md-ego-gifts.md#11-未解問題)、[13-9](13-md-ego-gifts.md#11-未解問題) | `must_be_abandoned` 的 `leave0..3_` 前綴未使用；公式成品缺 slash/pierce/blunt |
| [03-4](03-daily-tasks.md#12-未解問題) | `thread_enter_up80_assets` 與 `thread_enter_assets` 的差異 |
| [02-7](02-recognition-and-input.md#17-未解問題) | `maatouch` 資產未被引用 |
| [14-7](14-md-navigation.md#11-未解問題) | `MirrorMap.map`、`road_class_list` 已計算但無讀取者 |
| [14-8](14-md-navigation.md#11-未解問題) | `assets/mirror/theme_pack` 不存在，實際在 `assets/images/default/share/mirror/theme_pack/` |

## D. 打包、授權與外部來源

| 編號 | 問題 |
|---|---|
| [02-5](02-recognition-and-input.md#17-未解問題) | RapidOCR 模型隨包發佈還是首次下載 |
| [14-6](14-md-navigation.md#11-未解問題) | ONNX 模型訓練資料不在 repo；Ultralytics AGPL-3.0 與專案授權相容性 |
| [01-4](01-architecture.md#15-未解問題) | `register_daily_task` 用 `sys.executable` 未帶腳本路徑，原始碼模式失效 |
| [01-7](01-architecture.md#15-未解問題) | 圖片同步刪除不在清單的檔案，是否波及使用者自訂模板 |
| [01-8](01-architecture.md#15-未解問題) | `retry() is False` 約 30 處分支的重啟接續點彙整，見 [10](10-mirror-dungeon-overview.md)～[14](14-md-navigation.md) |
| [03-9](03-daily-tasks.md#12-未解問題) | 03 章 bbox 為 PIL 重算，與執行時可能差 1–2 px |

## 相關報告

[README](README.md) · [01](01-architecture.md) · [02](02-recognition-and-input.md) · [03](03-daily-tasks.md) · [10](10-mirror-dungeon-overview.md) · [11](11-md-team-formation.md) · [12](12-md-battle.md) · [13](13-md-ego-gifts.md) · [14](14-md-navigation.md) · [90](90-asset-index.md)
