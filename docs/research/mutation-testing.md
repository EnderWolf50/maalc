# 決策程式的突變測試（#634）

> 量測日：2026-11-11。16 個檔案量在 `main` 7449099d 上；`agent/gifts.py`、`agent/settings.py` 之後在 `main` 有改，這兩個在 e3f5b724 上重量，其餘檔案兩者相同。全部離線，沒碰模擬器。數字可以用下面「重跑」一節的指令在 repo 裡重算。

## 結論

- 18 個檔案、3311 個突變：測試抓到 2637 個（80.1%），沒抓到 655 個（其中 30 個在任何測試裡都不會執行到），19 個確認改了不影響行為（等價，各附理由）。
- 沒抓到的 655 個裡，395 個是「某個數字加 1」，多半是像素座標、顏色門檻、ROI 大小這類辨識常數：這次跑的測試用到的截圖沒有落在邊界上，所以 +1 之後測試照樣全過。要量到這種常數，得有剛好落在門檻附近的截圖。
- 真正值得補的是決策邏輯的分支：結算時的每週獎勵、星光恩典的購買、事件選項的排序、試煉辨認、設定檢查。前 10 名列在「最值得補測試的 10 個」。
- 其餘 260 個不是數字的存活突變沒有逐一證明「改了一定有影響」；清單裡可能還有等價的，確認過的才列進等價表。
- 分數最低的是 `pass_missions`（38%）、`shop`（67%）、`battle`（68%）、`gift_search`（71%）、`hub_text`（75%）：除了 `shop` 的融合與購買邏輯，主要都是像素辨識。`pass_missions` 與 `hub_text` 的 `CustomRecognition.analyze` 沒有任何測試會執行到（「沒有測試執行」那 30 個大多在這）。

## 工具：自己寫的 AST 突變工具

| 選項 | 這台 Windows 能不能用 | 結果 |
|---|---|---|
| mutmut | 不行：README 寫「Mutmut must be run on a system with `fork` support … if you want to run on windows, you must run inside WSL」（[README](https://github.com/boxed/mutmut/blob/main/README.rst)） | 要在 WSL 另裝一套 Linux 版 MaaFramework、numpy、OpenCV 環境，結果也只能在 WSL 重跑 |
| cosmic-ray | 文件沒提 Windows；它「makes mutations directly on disk」，並提醒可能沒把檔案改回來，建議先 commit（[tutorial](https://cosmic-ray.readthedocs.io/en/latest/tutorials/intro/index.html)） | 改檔會碰到工作樹；要跑在副本裡，而且 `exec` 一次跑完所有待跑的突變，不好切成 bench 佇列的短批次 |
| 自己寫（`tools/mutation.py`） | 能，純 Python、Windows 原生 | 採用 |

自己寫的版本不改任何檔案：`tools/mutation_plugin.py` 是一個 pytest plugin，測試 import 某檔案時，把它的程式換成突變後的語法樹（`__file__` 不變，資料檔照樣找得到）。主 checkout 與 worktree 都不會留下突變；每個突變一個 pytest 子行程、4 個同時跑，可以中斷、續跑，每批 14 分鐘一張 bench ticket。

突變種類（每個節點各一個）：比較 `<`↔`<=`、`>`↔`>=`、`==`↔`!=`、`in`↔`not in`、`is`↔`is not`；算術 `+`↔`-`、`*`↔`/`、`//`→`/`、`%`→`//`、`|`↔`&`、`**`→`*`（含 `+=` 等）；`and`↔`or`；拿掉 `not`、拿掉負號；`True`↔`False`；整數、浮點數加 1；`if c:` → `if not c:`；刪掉一行函式呼叫；`return x` → `return None`；`break`↔`continue`。不碰：型別標註、docstring、f-string、`if __name__ == "__main__":`、字串常數（OCR 關鍵字多，變了幾乎一定被抓或只是雜訊）。

## 跑哪些測試

1. **第一輪**：每個檔案跑「直接 import 它的測試檔」（`MODULES` 表），pytest `-x`，第一個失敗就停。逾時是同一組測試未突變時間的 3 倍再加 10 秒。
2. **覆蓋率**（`cover`）：每個測試檔各跑一次（不突變），用 Python 3.12 的 `sys.monitoring` 記下「哪個測試執行了哪個檔案的哪一行」。
3. **複驗**（`recheck`）：第一輪存活的突變，再跑一次「所有執行到它那一行的測試」（跨檔，例如 `shop.fusion_places` 由 `test_fuse_page.py` 經 `actions.py` 測到）。只在 import 時執行的行（檔案常數）改用「執行到讀這個名字的行」的測試。沒有任何測試執行到的，記為「沒有測試執行」。這一輪多抓到 100 個，其中 `gift_cells` 47 個（它的測試主要在 105 秒的 `test_gift_cells.py`，第一輪沒放）。

兩輪都略過：

- 啟動 MaaFramework 子行程的測試（`run_child`，一個要幾分鐘，而且子行程從磁碟 import，不吃突變）；plugin 讓它們 skip。
- 名字含 `when_it_is_unpacked` 的測試：拿 repo 裡的表跟這台機器解出的遊戲資料比。CI 上會跳過，也不跑 agent 的程式；遊戲更新後、表還沒跟上時，它們不管突變都會紅（量測當天在 7449099d 上就是這樣，e3f5b724 更新了表）。
- `test_shop_skill_screens.py`、`test_map_hard.py` 等自己開子行程跑的測試：覆蓋率記錄看不到子行程，所以複驗不會選到。

分數 = （抓到 + 複驗才抓到 + 逾時）/（前三者 + 沒抓到 + 沒有測試執行）；等價突變不算。

## 沒涵蓋的檔案

| 檔案 | 為什麼 |
|---|---|
| `agent/actions.py` | 5953 行的 MaaFramework 自訂動作；測試分散在約 40 個檔案，好幾個是幾分鐘一次的 MaaFramework 子行程，一個突變就要幾分鐘。它裡面的決策多半呼叫本次涵蓋的檔案（商店、地圖、結算） |
| `agent/main.py` | AgentServer 的進入點，沒有決策邏輯 |

## 重跑

```powershell
uv run python tools/mutation.py list                       # 每個檔案有幾個突變，不跑測試
uv run python tools/mutation.py baseline                   # 未突變時各檔案的測試會過，記下時間
uv run python tools/live/queue.py run --resource bench --name mutation-1 -- uv run python tools/mutation.py run --budget 840
uv run python tools/live/queue.py run --resource bench --name mutation-cover -- uv run python tools/mutation.py cover
uv run python tools/live/queue.py run --resource bench --name mutation-r1 -- uv run python tools/mutation.py recheck --budget 840
uv run python tools/mutation.py report                     # 下面的表與清單（英文表頭；本文翻成中文）
```

`run` 與 `recheck` 每次最多 14 分鐘，輸出的最後一行寫還剩幾個；剩下的再排一張 ticket。結果寫在主 checkout 的 `.local/scratch/mutation/results.jsonl`，以檔案原始碼的雜湊為鍵：程式改了，該檔案的舊結果自動不算。等價突變列在 `docs/research/mutation-equivalent.json`（`檔案:行:欄:突變` → 理由）。

這次的 bench 時間：第一輪 8 批約 6300 秒（第 7 批被背景任務的 2 小時上限中斷，結果檔完好，第 8 批續跑）、覆蓋率 4 次約 950 秒、複驗 4 批約 2760 秒，rebase 後重量 `gifts`、`settings` 約 190 秒，合計約 10200 秒（2.8 小時）。

## 最值得補測試的 10 個

挑法：從最後仍沒抓到的突變裡（複驗後、等價的已排除）挑決策邏輯，不挑像素常數；錯了在實機不容易看出來，或會花掉資源、讓一局白跑。後果是讀程式推得的，沒有實機跑過。

| # | 位置 | 突變 | 錯了在實機會怎樣 |
|---|---|---|---|
| 1 | `agent/settlement.py:87` | `if 1 in floors_hard:` → `if 2 in floors_hard:` | 重啟後從第 2 層以後接手的 HARD 局，第 1 層沒看到，`floors_hard.get(1)` 是空的，`all_hard` 變成假：結算只開 1 個每週獎勵，不是 3 個，剩下的要另開一局才用得掉 |
| 2 | `agent/run_start.py:53` | `continue` → `break` | 星光方案的優先順序裡有一個恩典設成 none，排在它後面的恩典全部不買 |
| 3 | `agent/run_start.py:14` | `GRACE_BASE` 第 5–9 個價格加 1 | 恩典 5–9 的價格算錯：星光剛好夠時判成買不起而跳過（`unaffordable: stop` 時後面全停） |
| 4 | `agent/rewards.py:48` | `return i, False` → `return i, True` | 設定指定的事件選項（override）被標成「只有檢定失敗才給」，派出最不可能過檢定的罪人，檢定失敗、拿不到那個選項的獎勵 |
| 5 | `agent/rewards.py:93`、`:98` | `not main` → `main` | 同一級的事件選項裡，不再優先給隊伍主要體系（如燒傷、流血）的 E.G.O 飾品，拿到別的體系的飾品 |
| 6 | `agent/rewards.py:102`、`:103` | 層級 `2` → `3`、`3` → `4`、`1` → `2` | 事件選項的層級被打亂：例如 `1` → `2` 讓直接拿飾品的選項和要過檢定的選項同級，可能選了會失敗的那個 |
| 7 | `agent/rewards.py:296` | `alike[1][0] < alike[0][0]` → `<=`；`alike[0][0]` → `alike[0][1]` | Mounting Trials 的卡：兩個試煉效果一樣接近時不再改用名字判斷，直接取第一個；或一個數值都對不上也認定是某個試煉。試煉認錯，評分跟著錯 |
| 8 | `agent/settings.py:487` | `continue` → `break` | 目標 10 或 15 層時，隊伍清單裡第一個停用的隊伍之後就不再檢查，排在後面、`usage: normal_only` 的啟用隊伍不會被擋下；輪到它時整局 NORMAL，到不了第 6 層 |
| 9 | `agent/luxcavation.py:12` | `THREAD_COST` `2` → `3` | 紐本一場以為要花 3 個腦啡肽模組（※ 依 `actions.py` 用它排場數推得）：腦啡肽模組剛好夠時少打一場 |
| 10 | `agent/pass_missions.py:64` | 點擊框座標（`- 20` → `+ 20` 等） | 沒有任何測試執行 `PassClaimable.analyze`：回傳的點擊框錯了，領通行證任務時點到旁邊，只有實機看得出來 |

其他也值得一看但沒排進前 10：`agent/settlement.py:28`（停在第 6 層、樓層標記沒讀到的局，run 紀錄的 difficulty 變 null，不是 HARD）、`agent/rewards.py:317`（試煉評分裡，最後一個前期池的金幣也算進去）、`agent/team_queue.py:114`（`return teams` → `None`：佇列其實寫了，log 卻說沒動）、`agent/hub_text.py:188`-`194`（`HubText.analyze` 沒有測試執行）、`agent/recovery.py:327`（runs 紀錄裡一行時間壞掉就停止讀後面的時間，`run_limit` 退回預設；沒有測試執行）。`agent/shop.py:260`（`locked` 的 `and` → `or`）也沒抓到，但只在 6 張牌、技能 3 為 0 張時才有差，而技能替換只會增加技能 3，實際碰不到，所以沒排進來。

## 各檔案的數字

| 檔案 | 突變 | 抓到 | 複驗才抓到 | 逾時 | 沒抓到 | 沒有測試執行 | 等價 | 錯誤 | 沒跑 | 分數 |
|---|---|---|---|---|---|---|---|---|---|---|
| settlement | 103 | 93 | 0 | 0 | 9 | 0 | 1 | 0 | 0 | 91% |
| rewards | 405 | 335 | 2 | 0 | 62 | 4 | 2 | 0 | 0 | 84% |
| battle | 173 | 113 | 4 | 0 | 56 | 0 | 0 | 0 | 0 | 68% |
| run_start | 328 | 290 | 3 | 0 | 29 | 0 | 6 | 0 | 0 | 91% |
| recovery | 296 | 258 | 1 | 0 | 35 | 1 | 1 | 0 | 0 | 88% |
| gift_search | 166 | 115 | 3 | 0 | 48 | 0 | 0 | 0 | 0 | 71% |
| shop | 785 | 488 | 32 | 6 | 258 | 0 | 1 | 0 | 0 | 67% |
| map_route | 121 | 95 | 0 | 0 | 26 | 0 | 0 | 0 | 0 | 79% |
| gifts | 91 | 88 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 99% |
| gift_cells | 64 | 6 | 47 | 0 | 11 | 0 | 0 | 0 | 0 | 83% |
| team_queue | 44 | 41 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 93% |
| lunacy | 43 | 43 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100% |
| luxcavation | 62 | 60 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 98% |
| ocrtext | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100% |
| pack_cover | 100 | 87 | 0 | 0 | 12 | 0 | 1 | 0 | 0 | 88% |
| settings | 285 | 266 | 2 | 0 | 11 | 0 | 6 | 0 | 0 | 96% |
| hub_text | 153 | 111 | 4 | 0 | 27 | 11 | 0 | 0 | 0 | 75% |
| pass_missions | 80 | 30 | 0 | 0 | 36 | 14 | 0 | 0 | 0 | 38% |

「抓到」是第一輪抓到的，「沒跑」是還沒跑的突變（這次 0）。

## 等價突變

改了也不影響行為的，各附一行理由；不算進分數，也不列進下面的清單。

| 位置 | 突變 | 為什麼不影響行為 |
|---|---|---|
| `agent/settlement.py:100` | `3` -> `4` | min(want, left) 的 left 最多 3（一週的每週獎勵數），3 與 4 開出的獎勵一樣多 |
| `agent/rewards.py:67` | `>` -> `>=` | 相等時新的 (score, fail_only) 和原本的 best 是同一組值，換不換都一樣 |
| `agent/rewards.py:425` | `break` -> `continue` | count 滿了之後不再變，後面每張卡都碰到同一個檢查而被跳過 |
| `agent/run_start.py:25` | `5` -> `6` | settings.schema.json 的 target_floor 只能是 5、10、15，> 5 與 > 6 結果相同 |
| `agent/run_start.py:97` | `1024` -> `1025` | lru_cache 的大小：只影響快取留多少，不影響回傳值 |
| `agent/run_start.py:176` | `8` -> `9` | lru_cache 的大小：只影響快取留多少，不影響回傳值 |
| `agent/run_start.py:308` | `15` -> `16` | target_floor 最多 15，一局沒有第 16 層，(11, 16) 與 (11, 15) 涵蓋的樓層相同 |
| `agent/run_start.py:320` | `15` -> `16` | target_floor 最多 15，一局沒有第 16 層，floor <= 16 與 floor <= 15 結果相同 |
| `agent/run_start.py:383` | `>` -> `>=` | target == max(visible) 代表 target 在 visible 裡，上一行已經回傳 |
| `agent/recovery.py:237` | `0` -> `1` | n 是 0 以上，max(n - 1, 1) 只在 n <= 1 時不同，而那時 1 // 5 與 0 // 5 都是 0 |
| `agent/shop.py:584` | `break` -> `continue` | cost 夠了之後不再變，後面每個飾品都碰到同一個檢查而被跳過 |
| `agent/luxcavation.py:56` | `>` -> `>=` | target == now 在上一行已經回傳 []，這裡 target 不會等於 now |
| `agent/pack_cover.py:46` | `1` -> `2` | lru_cache 的大小：只影響快取留多少，不影響回傳值 |
| `agent/settings.py:76` | call deleted | 第 14 版遷移（_team_gift_list）用同樣的預設值 [] 讀 keep_keywords，接著把它刪掉 |
| `agent/settings.py:77` | call deleted | 第 14 版遷移不讀 keywordless（Keywordless 一律保留），接著把它刪掉 |
| `agent/settings.py:78` | call deleted | 第 14 版遷移（_team_gift_list）用同樣的預設值 [] 讀 keep_gifts，接著把它刪掉 |
| `agent/settings.py:111` | call deleted | 第 14 版遷移（_team_gift_list）用同樣的預設值 "any" 讀 fusion_condition，接著把它刪掉 |
| `agent/settings.py:381` | `return x` -> `return None` | 唯一的呼叫端（team_queue._reorder）只看真假，None 與 False 一樣是假 |
| `agent/settings.py:480` | `5` -> `6` | settings.schema.json 的 target_floor 只能是 5、10、15，schema 錯誤時不跑這段交叉檢查 |

## 沒抓到的突變（655 個）

「跑過的測試」是複驗時執行到那一行的測試數；「沒有測試執行」表示沒有任何測試執行到。

<details><summary>全部列出</summary>

| 位置 | 突變 | 跑過的測試 | 原始碼 |
|---|---|---|---|
| `agent/settlement.py:28` | `5` -> `6` | 7 個 | `return True if self.floor > 5 else None` |
| `agent/settlement.py:47` | `1` -> `2` | 11 個 | `return Result(floor, None, int(m[1]), int(m[2])) if m else None` |
| `agent/settlement.py:87` | `1` -> `2` | 30 個 | `if 1 in floors_hard:` |
| `agent/settlement.py:88` | `>=` -> `>` | 14 個 | `return floor >= 1 and all(floors_hard.get(f) for f in range(1, floor + 1))` |
| `agent/settlement.py:88` | `1` -> `2` | 14 個 | `return floor >= 1 and all(floors_hard.get(f) for f in range(1, floor + 1))` |
| `agent/settlement.py:137` | `-x` -> `x` | 2 個 | `return f"{len(forfeits)} runs in a row forfeited" + (f" ({forfeits[-1]})" if forfeits[-1] ` |
| `agent/settlement.py:137` | `1` -> `2` | 2 個 | `return f"{len(forfeits)} runs in a row forfeited" + (f" ({forfeits[-1]})" if forfeits[-1] ` |
| `agent/settlement.py:172` | `True` -> `False` | 43 個 | `path.parent.mkdir(parents=True, exist_ok=True)` |
| `agent/settlement.py:174` | `False` -> `True` | 43 個 | `f.write(json.dumps(line, ensure_ascii=False) + "\n")` |
| `agent/rewards.py:48` | `False` -> `True` | 2 個 | `return i, False` |
| `agent/rewards.py:51` | `0` -> `1` | 38 個 | `best = min(open_, key=lambda i: (wanted.get(i) is None, -(wanted[i][0] if wanted.get(i) el` |
| `agent/rewards.py:93` | `not x` -> `x` | 4 個 | `return 3, not main` |
| `agent/rewards.py:94` | `True` -> `False` | 5 個 | `return 4, True  # a hint with neither text (901061, 901023, 971088) matches no AALC templa` |
| `agent/rewards.py:98` | `not x` -> `x` | 4 個 | `return 0, not main` |
| `agent/rewards.py:102` | `2` -> `3` | 2 個 | `return 2, not main` |
| `agent/rewards.py:103` | `3` -> `4` | 9 個 | `return (3 if re.search(r"\bdepending on\b", text, re.I) else 1), not main` |
| `agent/rewards.py:103` | `1` -> `2` | 9 個 | `return (3 if re.search(r"\bdepending on\b", text, re.I) else 1), not main` |
| `agent/rewards.py:118` | `and` -> `or` | 26 個 | `if len(s) >= len(_key(o["text"])) and s:` |
| `agent/rewards.py:119` | `-x` -> `x` | 26 個 | `scored.append((SequenceMatcher(None, s, target[:len(s)]).ratio(), -abs(len(target) - len(s` |
| `agent/rewards.py:119` | `-` -> `+` | 26 個 | `scored.append((SequenceMatcher(None, s, target[:len(s)]).ratio(), -abs(len(target) - len(s` |
| `agent/rewards.py:121` | `<` -> `<=` | 26 個 | `if not scored or scored[0][0] < min_ratio:` |
| `agent/rewards.py:141` | `>=` -> `>` | 23 個 | `hits = [e for e in events if s and SequenceMatcher(None, e["key"], s[-len(e["key"]):]).rat` |
| `agent/rewards.py:142` | `0` -> `1` | 23 個 | `longest = max((len(e["key"]) for e in hits), default=0)` |
| `agent/rewards.py:152` | `5` -> `6` | 22 個 | `b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:152` | `5` -> `6` | 22 個 | `b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:152` | `700` -> `701` | 22 個 | `b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:152` | `728` -> `729` | 22 個 | `b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:152` | `1` -> `2` | 22 個 | `b, _, r = image[y - 5:y + 5, 700:728].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:153` | `>` -> `>=` | 22 個 | `return bool(r - b > 10)` |
| `agent/rewards.py:153` | `10` -> `11` | 22 個 | `return bool(r - b > 10)` |
| `agent/rewards.py:156` | `165` -> `166` | 12 個 | `CHOICE_LIST_Y = (165, 512)  # the option list's view; options past it are cut off` |
| `agent/rewards.py:156` | `512` -> `513` | 12 個 | `CHOICE_LIST_Y = (165, 512)  # the option list's view; options past it are cut off` |
| `agent/rewards.py:157` | `50` -> `51` | 12 個 | `CARD_GAP = 50  # px between two edges at most for a card's bottom and the next card's top:` |
| `agent/rewards.py:169` | `>` -> `>=` | 25 個 | `bright = image[y0:y1, 700].astype(int).sum(1) > 200` |
| `agent/rewards.py:169` | `200` -> `201` | 25 個 | `bright = image[y0:y1, 700].astype(int).sum(1) > 200` |
| `agent/rewards.py:172` | `<=` -> `<` | 25 個 | `if edges and y - edges[-1][1] <= 6:` |
| `agent/rewards.py:172` | `6` -> `7` | 25 個 | `if edges and y - edges[-1][1] <= 6:` |
| `agent/rewards.py:179` | `<` -> `<=` | 25 個 | `if k and first - edges[k - 1][1] < CARD_GAP:` |
| `agent/rewards.py:181` | `1` -> `2` | 25 個 | `if k + 1 < len(edges):` |
| `agent/rewards.py:182` | `>=` -> `>` | 25 個 | `return edges[k + 1][0] - last >= CARD_GAP` |
| `agent/rewards.py:182` | `0` -> `1` | 25 個 | `return edges[k + 1][0] - last >= CARD_GAP` |
| `agent/rewards.py:183` | `if c:` -> `if not c:` | 24 個 | `if k:` |
| `agent/rewards.py:184` | `return x` -> `return None` | 24 個 | `return False  # the last edge, a card's height below another: that card's bottom` |
| `agent/rewards.py:185` | `return x` -> `return None` | 沒有測試執行 | `return last - first >= 6  # alone in the view: a double line is a top` |
| `agent/rewards.py:185` | `>=` -> `>` | 沒有測試執行 | `return last - first >= 6  # alone in the view: a double line is a top` |
| `agent/rewards.py:185` | `-` -> `+` | 沒有測試執行 | `return last - first >= 6  # alone in the view: a double line is a top` |
| `agent/rewards.py:185` | `6` -> `7` | 沒有測試執行 | `return last - first >= 6  # alone in the view: a double line is a top` |
| `agent/rewards.py:200` | `215` -> `216` | 22 個 | `b, _, r = image[215:445, 1203:1213].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:200` | `445` -> `446` | 22 個 | `b, _, r = image[215:445, 1203:1213].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:200` | `1203` -> `1204` | 22 個 | `b, _, r = image[215:445, 1203:1213].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:200` | `1213` -> `1214` | 22 個 | `b, _, r = image[215:445, 1203:1213].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:200` | `1` -> `2` | 22 個 | `b, _, r = image[215:445, 1203:1213].reshape(-1, 3).mean(0)` |
| `agent/rewards.py:201` | `and` -> `or` | 22 個 | `return bool(r > 40 and r - b > 20)` |
| `agent/rewards.py:201` | `>` -> `>=` | 22 個 | `return bool(r > 40 and r - b > 20)` |
| `agent/rewards.py:201` | `40` -> `41` | 22 個 | `return bool(r > 40 and r - b > 20)` |
| `agent/rewards.py:201` | `>` -> `>=` | 22 個 | `return bool(r > 40 and r - b > 20)` |
| `agent/rewards.py:201` | `-` -> `+` | 22 個 | `return bool(r > 40 and r - b > 20)` |
| `agent/rewards.py:201` | `20` -> `21` | 22 個 | `return bool(r > 40 and r - b > 20)` |
| `agent/rewards.py:257` | `>=` -> `>` | 29 個 | `return any(SequenceMatcher(None, key[i:i + len(word)], word).ratio() >= min_ratio` |
| `agent/rewards.py:258` | `1` -> `2` | 29 個 | `for i in range(max(1, len(key) - len(word) + 1)))` |
| `agent/rewards.py:258` | `+` -> `-` | 29 個 | `for i in range(max(1, len(key) - len(word) + 1)))` |
| `agent/rewards.py:258` | `-` -> `+` | 29 個 | `for i in range(max(1, len(key) - len(word) + 1)))` |
| `agent/rewards.py:258` | `1` -> `2` | 29 個 | `for i in range(max(1, len(key) - len(word) + 1)))` |
| `agent/rewards.py:294` | `<` -> `<=` | 21 個 | `alike = sorted(((sum(abs(t["effects"][k] - v) < 1e-6 for k, v in read.items()), n)` |
| `agent/rewards.py:296` | `0` -> `1` | 21 個 | `if alike and alike[0][0] and (len(alike) == 1 or alike[1][0] < alike[0][0]):` |
| `agent/rewards.py:296` | `<` -> `<=` | 21 個 | `if alike and alike[0][0] and (len(alike) == 1 or alike[1][0] < alike[0][0]):` |
| `agent/rewards.py:310` | `0` -> `1` | 12 個 | `def scores(trials, model, coins=0, overrides=None):` |
| `agent/rewards.py:317` | `0` -> `1` | 33 個 | `coin = t["effects"].get("coin", 0) if t["pool"] > model["early_pools"] else 0` |
| `agent/rewards.py:317` | `>` -> `>=` | 33 個 | `coin = t["effects"].get("coin", 0) if t["pool"] > model["early_pools"] else 0` |
| `agent/rewards.py:335` | `8` -> `9` | 12 個 | `TITLE_ROW = 8  # px: boxes whose tops are this near the topmost line's are one title (a na` |
| `agent/rewards.py:366` | `<` -> `<=` | 40 個 | `return " ".join(t for y, t in rows if y < top + TITLE_ROW)` |
| `agent/rewards.py:416` | `and` -> `or` | 34 個 | `if select_count(shown) is None and len(ranked) > 1:` |
| `agent/rewards.py:416` | `>` -> `>=` | 34 個 | `if select_count(shown) is None and len(ranked) > 1:` |
| `agent/rewards.py:416` | `1` -> `2` | 34 個 | `if select_count(shown) is None and len(ranked) > 1:` |
| `agent/rewards.py:429` | `<` -> `<=` | 29 個 | `if count and now and now[0] < count[0]:  # it was picked already: pick it again, go on to ` |
| `agent/battle.py:63` | `984` -> `985` | 41 個 | `n = 7 + round((win_rate_x - 984) / 40.5)` |
| `agent/battle.py:63` | `40.5` -> `41.5` | 41 個 | `n = 7 + round((win_rate_x - 984) / 40.5)` |
| `agent/battle.py:64` | `0` -> `1` | 41 個 | `return [round(605 + 81 * (i - (n - 1) / 2)) for i in range(max(n, 0))]` |
| `agent/battle.py:82` | `-` -> `+` | 21 個 | `left = (slot_xs(x) or [605])[0] - 86 - 40` |
| `agent/battle.py:82` | `605` -> `606` | 21 個 | `left = (slot_xs(x) or [605])[0] - 86 - 40` |
| `agent/battle.py:82` | `86` -> `87` | 21 個 | `left = (slot_xs(x) or [605])[0] - 86 - 40` |
| `agent/battle.py:82` | `40` -> `41` | 21 個 | `left = (slot_xs(x) or [605])[0] - 86 - 40` |
| `agent/battle.py:83` | `560` -> `561` | 21 個 | `return left, 560, -(-(x + w - left) // 40) * 40, 160` |
| `agent/battle.py:83` | `-` -> `+` | 21 個 | `return left, 560, -(-(x + w - left) // 40) * 40, 160` |
| `agent/battle.py:83` | `40` -> `41` | 21 個 | `return left, 560, -(-(x + w - left) // 40) * 40, 160` |
| `agent/battle.py:83` | `40` -> `41` | 21 個 | `return left, 560, -(-(x + w - left) // 40) * 40, 160` |
| `agent/battle.py:83` | `160` -> `161` | 21 個 | `return left, 560, -(-(x + w - left) // 40) * 40, 160` |
| `agent/battle.py:111` | `<` -> `<=` | 10 個 | `if t1 < t0 * 0.93 or t1 > t0 * 1.07:` |
| `agent/battle.py:111` | `>` -> `>=` | 10 個 | `if t1 < t0 * 0.93 or t1 > t0 * 1.07:` |
| `agent/battle.py:111` | `1.07` -> `2.0700000000000003` | 10 個 | `if t1 < t0 * 0.93 or t1 > t0 * 1.07:` |
| `agent/battle.py:112` | `<` -> `<=` | 10 個 | `shown.append(t1 < t0)` |
| `agent/battle.py:113` | `>=` -> `>` | 1 個 | `elif abs(b1 - b0) >= 0.1:` |
| `agent/battle.py:114` | `>` -> `>=` | 1 個 | `shown.append(b1 > b0)` |
| `agent/battle.py:123` | `23` -> `24` | 10 個 | `STAGGER_AT, STAGGER_SLIDE = (-23, 649), (12, 4)` |
| `agent/battle.py:123` | `649` -> `650` | 10 個 | `STAGGER_AT, STAGGER_SLIDE = (-23, 649), (12, 4)` |
| `agent/battle.py:123` | `12` -> `13` | 10 個 | `STAGGER_AT, STAGGER_SLIDE = (-23, 649), (12, 4)` |
| `agent/battle.py:123` | `4` -> `5` | 10 個 | `STAGGER_AT, STAGGER_SLIDE = (-23, 649), (12, 4)` |
| `agent/battle.py:125` | `0.114` -> `1.114` | 10 個 | `BGR_LUMA = np.array([0.114, 0.587, 0.299])  # a BGR pixel's weights in its greyscale value` |
| `agent/battle.py:125` | `0.587` -> `1.587` | 10 個 | `BGR_LUMA = np.array([0.114, 0.587, 0.299])  # a BGR pixel's weights in its greyscale value` |
| `agent/battle.py:125` | `0.299` -> `1.299` | 10 個 | `BGR_LUMA = np.array([0.114, 0.587, 0.299])  # a BGR pixel's weights in its greyscale value` |
| `agent/battle.py:141` | `0` -> `1` | 16 個 | `roi = image[top - sy:top + word.shape[0] + sy, left - sx:left + word.shape[1] + sx] @ BGR_` |
| `agent/battle.py:145` | `<` -> `<=` | 16 個 | `flat = spread < word.size` |
| `agent/battle.py:146` | `1` -> `2` | 16 個 | `return float(np.where(flat, 0, dot / np.sqrt(np.where(flat, 1, spread) * (word ** 2).sum()` |
| `agent/battle.py:158` | `>` -> `>=` | 16 個 | `return [stagger_score(image, x) > STAGGER_MATCH for x in xs]` |
| `agent/battle.py:168` | `>` -> `>=` | 12 個 | `return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)` |
| `agent/battle.py:168` | `10` -> `11` | 12 個 | `return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)` |
| `agent/battle.py:168` | `10` -> `11` | 12 個 | `return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)` |
| `agent/battle.py:168` | `10` -> `11` | 12 個 | `return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)` |
| `agent/battle.py:168` | `10` -> `11` | 12 個 | `return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)` |
| `agent/battle.py:168` | `160` -> `161` | 12 個 | `return bool(image[y - 10:y + 10, x - 10:x + 10].max(axis=2).mean() > 160)` |
| `agent/battle.py:171` | `0` -> `1` | 10 個 | `RING_ANGLES = np.linspace(0, 2 * np.pi, 72, endpoint=False)` |
| `agent/battle.py:171` | `2` -> `3` | 10 個 | `RING_ANGLES = np.linspace(0, 2 * np.pi, 72, endpoint=False)` |
| `agent/battle.py:171` | `72` -> `73` | 10 個 | `RING_ANGLES = np.linspace(0, 2 * np.pi, 72, endpoint=False)` |
| `agent/battle.py:171` | `False` -> `True` | 10 個 | `RING_ANGLES = np.linspace(0, 2 * np.pi, 72, endpoint=False)` |
| `agent/battle.py:185` | `6` -> `7` | 19 個 | `r = np.arange(6, 31)[:, None]` |
| `agent/battle.py:185` | `31` -> `32` | 19 個 | `r = np.arange(6, 31)[:, None]` |
| `agent/battle.py:187` | `-x` -> `x` | 19 個 | `for dy in (-1, 0, 1):` |
| `agent/battle.py:187` | `1` -> `2` | 19 個 | `for dy in (-1, 0, 1):` |
| `agent/battle.py:187` | `0` -> `1` | 19 個 | `for dy in (-1, 0, 1):` |
| `agent/battle.py:187` | `1` -> `2` | 19 個 | `for dy in (-1, 0, 1):` |
| `agent/battle.py:188` | `-x` -> `x` | 19 個 | `for dx in (-1, 0, 1):` |
| `agent/battle.py:188` | `1` -> `2` | 19 個 | `for dx in (-1, 0, 1):` |
| `agent/battle.py:188` | `0` -> `1` | 19 個 | `for dx in (-1, 0, 1):` |
| `agent/battle.py:188` | `1` -> `2` | 19 個 | `for dx in (-1, 0, 1):` |
| `agent/battle.py:189` | `+` -> `-` | 19 個 | `circles = v[np.round(y + dy + r * np.sin(RING_ANGLES)).astype(int),` |
| `agent/battle.py:189` | `+` -> `-` | 19 個 | `circles = v[np.round(y + dy + r * np.sin(RING_ANGLES)).astype(int),` |
| `agent/battle.py:190` | `+` -> `-` | 19 個 | `np.round(x + dx + r * np.cos(RING_ANGLES)).astype(int)]` |
| `agent/battle.py:190` | `+` -> `-` | 19 個 | `np.round(x + dx + r * np.cos(RING_ANGLES)).astype(int)]` |
| `agent/battle.py:191` | `+` -> `-` | 19 個 | `best = max(best, circles.mean(axis=1).var() / (circles.var(axis=1).mean() + 1))` |
| `agent/battle.py:191` | `1` -> `2` | 19 個 | `best = max(best, circles.mean(axis=1).var() / (circles.var(axis=1).mean() + 1))` |
| `agent/battle.py:192` | `>` -> `>=` | 19 個 | `return bool(best > 0.5)` |
| `agent/run_start.py:14` | `30` -> `31` | 11 個 | `GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)` |
| `agent/run_start.py:14` | `30` -> `31` | 11 個 | `GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)` |
| `agent/run_start.py:14` | `40` -> `41` | 11 個 | `GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)` |
| `agent/run_start.py:14` | `40` -> `41` | 11 個 | `GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)` |
| `agent/run_start.py:14` | `50` -> `51` | 11 個 | `GRACE_BASE = (10, 10, 20, 20, 30, 30, 40, 40, 50, 60)` |
| `agent/run_start.py:53` | `continue` -> `break` | 1 個 | `continue` |
| `agent/run_start.py:111` | `and` -> `or` | 59 個 | `if m.real_quick_ratio() >= min_ratio - margin and m.quick_ratio() >= min_ratio - margin:` |
| `agent/run_start.py:111` | `>=` -> `>` | 59 個 | `if m.real_quick_ratio() >= min_ratio - margin and m.quick_ratio() >= min_ratio - margin:` |
| `agent/run_start.py:111` | `>=` -> `>` | 59 個 | `if m.real_quick_ratio() >= min_ratio - margin and m.quick_ratio() >= min_ratio - margin:` |
| `agent/run_start.py:116` | `1` -> `2` | 56 個 | `if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:` |
| `agent/run_start.py:116` | `<` -> `<=` | 56 個 | `if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:` |
| `agent/run_start.py:146` | `6` -> `7` | 11 個 | `SHORT_NAME = 6` |
| `agent/run_start.py:147` | `3` -> `4` | 11 個 | `SHORT_READ_TIMES = 3` |
| `agent/run_start.py:163` | `1` -> `2` | 78 個 | `r = max(SequenceMatcher(None, key[i:i + len(n)], n).ratio() for i in range(max(1, len(key)` |
| `agent/run_start.py:163` | `-` -> `+` | 78 個 | `r = max(SequenceMatcher(None, key[i:i + len(n)], n).ratio() for i in range(max(1, len(key)` |
| `agent/run_start.py:163` | `1` -> `2` | 78 個 | `r = max(SequenceMatcher(None, key[i:i + len(n)], n).ratio() for i in range(max(1, len(key)` |
| `agent/run_start.py:164` | `<` -> `<=` | 78 個 | `if r < 1 and len(n) <= SHORT_NAME and len(key) > SHORT_READ_TIMES * len(n):` |
| `agent/run_start.py:164` | `1` -> `2` | 78 個 | `if r < 1 and len(n) <= SHORT_NAME and len(key) > SHORT_READ_TIMES * len(n):` |
| `agent/run_start.py:164` | `<=` -> `<` | 78 個 | `if r < 1 and len(n) <= SHORT_NAME and len(key) > SHORT_READ_TIMES * len(n):` |
| `agent/run_start.py:164` | `>` -> `>=` | 78 個 | `if r < 1 and len(n) <= SHORT_NAME and len(key) > SHORT_READ_TIMES * len(n):` |
| `agent/run_start.py:183` | `1` -> `2` | 6 個 | `stretches = [c[i:i + n] for n in range(KEYWORD_MIN, len(c) + 1) for i in range(len(c) - n ` |
| `agent/run_start.py:183` | `-` -> `+` | 6 個 | `stretches = [c[i:i + n] for n in range(KEYWORD_MIN, len(c) + 1) for i in range(len(c) - n ` |
| `agent/run_start.py:183` | `1` -> `2` | 6 個 | `stretches = [c[i:i + n] for n in range(KEYWORD_MIN, len(c) + 1) for i in range(len(c) - n ` |
| `agent/run_start.py:217` | `15` -> `16` | 11 個 | `CARD_GAP = 15  # px between two OCR boxes of one card's text; adjacent cards' texts sit 25` |
| `agent/run_start.py:218` | `105` -> `106` | 11 個 | `CARD_SPAN = 105  # px: texts of two cards are at least this far apart by centre (cards 182` |
| `agent/run_start.py:245` | `<` -> `<=` | 39 個 | `if cards and (left + right) / 2 - (cards[-1][0] + cards[-1][1]) / 2 < CARD_SPAN:` |
| `agent/run_start.py:246` | `0` -> `1` | 1 個 | `cards[-1] = [cards[-1][0], max(cards[-1][1], right), cards[-1][2] + group]` |
| `agent/run_start.py:249` | `//` -> `/` | 39 個 | `return [((left + right) // 2, [t for _, t in sorted((y, t) for _, _, y, t in group)]) for ` |
| `agent/run_start.py:267` | `break` -> `continue` | 44 個 | `break` |
| `agent/recovery.py:24` | `80` -> `81` | 10 個 | `WAIT_STILL, WAIT_CAP = 80, {"Loading": 150, "Connecting": 150}` |
| `agent/recovery.py:24` | `150` -> `151` | 10 個 | `WAIT_STILL, WAIT_CAP = 80, {"Loading": 150, "Connecting": 150}` |
| `agent/recovery.py:47` | `30` -> `31` | 10 個 | `UNKNOWN_KEEP = 30  # screens MirrorHub did not recognise that logs/unknown/ keeps` |
| `agent/recovery.py:48` | `100` -> `101` | 10 個 | `DISMISSED_KEEP = 100  # screens of notices, popups and recovery's back key that logs/dismi` |
| `agent/recovery.py:49` | `50` -> `51` | 10 個 | `COST_KEEP = 50  # crops of map Cost coins that read as no Cost that logs/cost/ keeps (#284` |
| `agent/recovery.py:52` | `*` -> `/` | 10 個 | `DOWNLOAD_HOLD = 3 * 60` |
| `agent/recovery.py:52` | `3` -> `4` | 10 個 | `DOWNLOAD_HOLD = 3 * 60` |
| `agent/recovery.py:52` | `60` -> `61` | 10 個 | `DOWNLOAD_HOLD = 3 * 60` |
| `agent/recovery.py:69` | `40` -> `41` | 493 個 | `h, w = image.shape[0] // 40 * 40, image.shape[1] // 40 * 40` |
| `agent/recovery.py:69` | `40` -> `41` | 493 個 | `h, w = image.shape[0] // 40 * 40, image.shape[1] // 40 * 40` |
| `agent/recovery.py:69` | `40` -> `41` | 493 個 | `h, w = image.shape[0] // 40 * 40, image.shape[1] // 40 * 40` |
| `agent/recovery.py:70` | `1` -> `2` | 493 個 | `return image[:h, :w].reshape(h // 40, 40, w // 40, 40, -1).mean(axis=(1, 3, 4))` |
| `agent/recovery.py:78` | `<` -> `<=` | 499 個 | `return a is not None and b is not None and a.shape == b.shape and (abs(a - b) > 8).mean() ` |
| `agent/recovery.py:78` | `>` -> `>=` | 499 個 | `return a is not None and b is not None and a.shape == b.shape and (abs(a - b) > 8).mean() ` |
| `agent/recovery.py:78` | `8` -> `9` | 499 個 | `return a is not None and b is not None and a.shape == b.shape and (abs(a - b) > 8).mean() ` |
| `agent/recovery.py:89` | `8` -> `9` | 77 個 | `return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)` |
| `agent/recovery.py:89` | `2` -> `3` | 77 個 | `return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)` |
| `agent/recovery.py:89` | `0` -> `1` | 77 個 | `return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)` |
| `agent/recovery.py:89` | `0` -> `1` | 77 個 | `return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)` |
| `agent/recovery.py:89` | `0` -> `1` | 77 個 | `return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)` |
| `agent/recovery.py:90` | `6` -> `7` | 77 個 | `+ chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)) + chunk(b"IEND", b""))` |
| `agent/recovery.py:98` | `-` -> `+` | 3 個 | `rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(h, 1 + w` |
| `agent/recovery.py:98` | `+` -> `-` | 3 個 | `rows = np.frombuffer(zlib.decompress(data[8 + 25 + 8:-12 - 4]), np.uint8).reshape(h, 1 + w` |
| `agent/recovery.py:120` | `0.0` -> `1.0` | 64 個 | `self.kind, self.kind_since, self.hits = None, 0.0, 0  # hits: this kind in a row` |
| `agent/recovery.py:120` | `0` -> `1` | 64 個 | `self.kind, self.kind_since, self.hits = None, 0.0, 0  # hits: this kind in a row` |
| `agent/recovery.py:121` | `0` -> `1` | 64 個 | `self.first, self.count, self.since = None, 0, 0.0  # the streak's first thumbnail` |
| `agent/recovery.py:121` | `0.0` -> `1.0` | 64 個 | `self.first, self.count, self.since = None, 0, 0.0  # the streak's first thumbnail` |
| `agent/recovery.py:122` | `0.0` -> `1.0` | 64 個 | `self.last, self.moved = None, 0.0  # the last thumbnail, and when the screen last changed ` |
| `agent/recovery.py:123` | `0.0` -> `1.0` | 64 個 | `self.hold_until = 0.0  # a download is under way until then: no screen counts as stuck` |
| `agent/recovery.py:124` | `0` -> `1` | 64 個 | `self.dead, self.dead_picture = 0, None  # dead taps in a row (tapped), and the thumbnail t` |
| `agent/recovery.py:135` | `0` -> `1` | 352 個 | `self.dead, self.dead_picture = 0, None` |
| `agent/recovery.py:169` | `>` -> `>=` | 9 個 | `return f"still up after {cap} s" if cap and now - self.kind_since > cap else None` |
| `agent/recovery.py:170` | `-` -> `+` | 13 個 | `if self.count >= SAME_SCREEN and now - self.since >= HASH_FLOOR.get(kind, 0):` |
| `agent/recovery.py:170` | `0` -> `1` | 13 個 | `if self.count >= SAME_SCREEN and now - self.since >= HASH_FLOOR.get(kind, 0):` |
| `agent/recovery.py:179` | `<` -> `<=` | 31 個 | `return now < self.hold_until` |
| `agent/recovery.py:327` | `continue` -> `break` | 沒有測試執行 | `continue` |
| `agent/gift_search.py:13` | `130` -> `131` | 9 個 | `CELL_X = [130 + round(83.4 * c) for c in range(8)]` |
| `agent/gift_search.py:13` | `8` -> `9` | 9 個 | `CELL_X = [130 + round(83.4 * c) for c in range(8)]` |
| `agent/gift_search.py:14` | `228` -> `229` | 9 個 | `GRID_Y = (228, 625)` |
| `agent/gift_search.py:14` | `625` -> `626` | 9 個 | `GRID_Y = (228, 625)` |
| `agent/gift_search.py:15` | `600` -> `601` | 9 個 | `LAST_Y = 600  # lowest cell centre still inside the grid` |
| `agent/gift_search.py:24` | `&` -> `|` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:24` | `>` -> `>=` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:24` | `200` -> `201` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:24` | `>` -> `>=` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:24` | `150` -> `151` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:24` | `<` -> `<=` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:24` | `80` -> `81` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:27` | `34` -> `35` | 2 個 | `strip = yellow[:, x - 34:x - 8]` |
| `agent/gift_search.py:27` | `-` -> `+` | 2 個 | `strip = yellow[:, x - 34:x - 8]` |
| `agent/gift_search.py:27` | `8` -> `9` | 2 個 | `strip = yellow[:, x - 34:x - 8]` |
| `agent/gift_search.py:31` | `<=` -> `<` | 2 個 | `if 16 <= run <= 22 and y <= LAST_Y:` |
| `agent/gift_search.py:31` | `<=` -> `<` | 2 個 | `if 16 <= run <= 22 and y <= LAST_Y:` |
| `agent/gift_search.py:31` | `16` -> `17` | 2 個 | `if 16 <= run <= 22 and y <= LAST_Y:` |
| `agent/gift_search.py:31` | `22` -> `23` | 2 個 | `if 16 <= run <= 22 and y <= LAST_Y:` |
| `agent/gift_search.py:31` | `<=` -> `<` | 2 個 | `if 16 <= run <= 22 and y <= LAST_Y:` |
| `agent/gift_search.py:32` | `2` -> `3` | 1 個 | `bars = len(_runs(np.flatnonzero(strip[top + run // 2])))` |
| `agent/gift_search.py:33` | `3` -> `4` | 1 個 | `if 1 <= bars <= 3:` |
| `agent/gift_search.py:35` | `//` -> `/` | 2 個 | `return sorted(cells, key=lambda c: (c[1] // 40, c[0]))` |
| `agent/gift_search.py:35` | `40` -> `41` | 2 個 | `return sorted(cells, key=lambda c: (c[1] // 40, c[0]))` |
| `agent/gift_search.py:35` | `0` -> `1` | 2 個 | `return sorted(cells, key=lambda c: (c[1] // 40, c[0]))` |
| `agent/gift_search.py:45` | `>` -> `>=` | 2 個 | `band = (b[:, 300:700] - r[:, 300:700]).mean(axis=1) > 40` |
| `agent/gift_search.py:45` | `40` -> `41` | 2 個 | `band = (b[:, 300:700] - r[:, 300:700]).mean(axis=1) > 40` |
| `agent/gift_search.py:46` | `&` -> `|` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `&` -> `|` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `>` -> `>=` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `200` -> `201` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `>` -> `>=` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `150` -> `151` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `<` -> `<=` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:46` | `80` -> `81` | 2 個 | `yellow = (r > 200) & (g > 150) & (b < 80)` |
| `agent/gift_search.py:49` | `12` -> `13` | 2 個 | `bars = len(_runs(np.flatnonzero(yellow[top + 12, CELL_X[0] - 34:CELL_X[0] - 8])))` |
| `agent/gift_search.py:49` | `34` -> `35` | 2 個 | `bars = len(_runs(np.flatnonzero(yellow[top + 12, CELL_X[0] - 34:CELL_X[0] - 8])))` |
| `agent/gift_search.py:49` | `-` -> `+` | 2 個 | `bars = len(_runs(np.flatnonzero(yellow[top + 12, CELL_X[0] - 34:CELL_X[0] - 8])))` |
| `agent/gift_search.py:49` | `0` -> `1` | 2 個 | `bars = len(_runs(np.flatnonzero(yellow[top + 12, CELL_X[0] - 34:CELL_X[0] - 8])))` |
| `agent/gift_search.py:49` | `8` -> `9` | 2 個 | `bars = len(_runs(np.flatnonzero(yellow[top + 12, CELL_X[0] - 34:CELL_X[0] - 8])))` |
| `agent/gift_search.py:50` | `and` -> `or` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:50` | `<=` -> `<` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:50` | `<=` -> `<` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:50` | `22` -> `23` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:50` | `27` -> `28` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:50` | `<=` -> `<` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:50` | `3` -> `4` | 2 個 | `if 22 <= run <= 27 and 1 <= bars <= 3:` |
| `agent/gift_search.py:55` | `252` -> `253` | 9 個 | `HEADER_Y = 252  # the first section header with the tab scrolled to the top` |
| `agent/shop.py:17` | `10` -> `11` | 9 個 | `ROUNDS = 10` |
| `agent/shop.py:19` | `2` -> `3` | 9 個 | `TIERS = {(1, 1): 1, (2, 2): 2, (3, 3): 3, (3, 2): 4, (2, 1): 5}  # numeral strokes at its ` |
| `agent/shop.py:19` | `5` -> `6` | 9 個 | `TIERS = {(1, 1): 1, (2, 2): 2, (3, 3): 3, (3, 2): 4, (2, 1): 5}  # numeral strokes at its ` |
| `agent/shop.py:25` | `-` -> `+` | 7 個 | `ys = np.minimum((np.arange(round(h * factor)) / factor).astype(int), h - 1)` |
| `agent/shop.py:25` | `1` -> `2` | 7 個 | `ys = np.minimum((np.arange(round(h * factor)) / factor).astype(int), h - 1)` |
| `agent/shop.py:26` | `*` -> `/` | 7 個 | `xs = np.minimum((np.arange(round(w * factor)) / factor).astype(int), w - 1)` |
| `agent/shop.py:26` | `-` -> `+` | 7 個 | `xs = np.minimum((np.arange(round(w * factor)) / factor).astype(int), w - 1)` |
| `agent/shop.py:26` | `1` -> `2` | 7 個 | `xs = np.minimum((np.arange(round(w * factor)) / factor).astype(int), w - 1)` |
| `agent/shop.py:41` | `>` -> `>=` | 171 個 | `return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)` |
| `agent/shop.py:41` | `25` -> `26` | 171 個 | `return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)` |
| `agent/shop.py:41` | `25` -> `26` | 171 個 | `return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)` |
| `agent/shop.py:41` | `25` -> `26` | 171 個 | `return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)` |
| `agent/shop.py:41` | `25` -> `26` | 171 個 | `return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)` |
| `agent/shop.py:41` | `15` -> `16` | 171 個 | `return bool(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15)` |
| `agent/shop.py:44` | `44` -> `45` | 9 個 | `UNSELECTABLE_BAND = (44, 29, 44)  # px over a cell's centre the fuse page's "Unselectable"` |
| `agent/shop.py:44` | `44` -> `45` | 9 個 | `UNSELECTABLE_BAND = (44, 29, 44)  # px over a cell's centre the fuse page's "Unselectable"` |
| `agent/shop.py:45` | `300` -> `301` | 9 個 | `UNSELECTABLE_MIN, UNSELECTABLE_SPAN, UNSELECTABLE_RUN = 300, 70, 20  # its letters' px, th` |
| `agent/shop.py:45` | `70` -> `71` | 9 個 | `UNSELECTABLE_MIN, UNSELECTABLE_SPAN, UNSELECTABLE_RUN = 300, 70, 20  # its letters' px, th` |
| `agent/shop.py:45` | `20` -> `21` | 9 個 | `UNSELECTABLE_MIN, UNSELECTABLE_SPAN, UNSELECTABLE_RUN = 300, 70, 20  # its letters' px, th` |
| `agent/shop.py:60` | `0` -> `1` | 117 個 | `b, g, r = band[:, :, 0], band[:, :, 1], band[:, :, 2]` |
| `agent/shop.py:61` | `>` -> `>=` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:61` | `<` -> `<=` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:61` | `180` -> `181` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:61` | `<` -> `<=` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:61` | `40` -> `41` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:61` | `<` -> `<=` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:61` | `40` -> `41` | 117 個 | `letters = (r > 90) & (r < 180) & (g < 40) & (b < 40)` |
| `agent/shop.py:63` | `<` -> `<=` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:63` | `<` -> `<=` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:63` | `+` -> `-` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:63` | `-` -> `+` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:63` | `1` -> `2` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:63` | `0` -> `1` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:63` | `1` -> `2` | 117 個 | `if letters.sum() < UNSELECTABLE_MIN or cols[-1] - cols[0] + 1 < UNSELECTABLE_SPAN:` |
| `agent/shop.py:64` | `return x` -> `return None` | 117 個 | `return False` |
| `agent/shop.py:65` | `<=` -> `<` | 3 個 | `return max(n for row in letters for _, n in _runs(np.flatnonzero(row))) <= UNSELECTABLE_RU` |
| `agent/shop.py:71` | `>` -> `>=` | 110 個 | `return (r > 200) & (g > 140) & (b < 90)` |
| `agent/shop.py:71` | `200` -> `201` | 110 個 | `return (r > 200) & (g > 140) & (b < 90)` |
| `agent/shop.py:71` | `>` -> `>=` | 110 個 | `return (r > 200) & (g > 140) & (b < 90)` |
| `agent/shop.py:82` | `0` -> `1` | 36 個 | `lo, hi = bars[0][0] - 1, bars[-1][0] + bars[-1][1] + 1  # icon art beside the numerals sta` |
| `agent/shop.py:82` | `1` -> `2` | 36 個 | `lo, hi = bars[0][0] - 1, bars[-1][0] + bars[-1][1] + 1  # icon art beside the numerals sta` |
| `agent/shop.py:82` | `1` -> `2` | 36 個 | `lo, hi = bars[0][0] - 1, bars[-1][0] + bars[-1][1] + 1  # icon art beside the numerals sta` |
| `agent/shop.py:89` | `0` -> `1` | 7 個 | `mid = cell.shape[0] // 2` |
| `agent/shop.py:90` | `8` -> `9` | 7 個 | `return cell[mid - 36:mid - 8, mid - 36:mid - 16]` |
| `agent/shop.py:90` | `36` -> `37` | 7 個 | `return cell[mid - 36:mid - 8, mid - 36:mid - 16]` |
| `agent/shop.py:90` | `16` -> `17` | 7 個 | `return cell[mid - 36:mid - 8, mid - 36:mid - 16]` |
| `agent/shop.py:95` | `19` -> `20` | 6 個 | `return numeral(yellow(numeral_place(cell)), 9, 19)` |
| `agent/shop.py:106` | `40` -> `41` | 67 個 | `return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)` |
| `agent/shop.py:106` | `>` -> `>=` | 67 個 | `return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)` |
| `agent/shop.py:106` | `5` -> `6` | 67 個 | `return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)` |
| `agent/shop.py:106` | `6` -> `7` | 67 個 | `return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)` |
| `agent/shop.py:106` | `>` -> `>=` | 67 個 | `return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)` |
| `agent/shop.py:106` | `10` -> `11` | 67 個 | `return (g > 40) & (5 * g > 6 * r) & (g > 2 * b + 10)` |
| `agent/shop.py:111` | `30` -> `31` | 9 個 | `EX_CELL_PX = 30` |
| `agent/shop.py:116` | `>=` -> `>` | 2 個 | `return int(green(numeral_place(cell)).sum()) >= EX_CELL_PX` |
| `agent/shop.py:119` | `338` -> `339` | 9 個 | `GET_MARK = (338, 228, 50, 50)  # x, y, w, h: the GET! popup's icon corner, its gift's tier` |
| `agent/shop.py:119` | `228` -> `229` | 9 個 | `GET_MARK = (338, 228, 50, 50)  # x, y, w, h: the GET! popup's icon corner, its gift's tier` |
| `agent/shop.py:119` | `50` -> `51` | 9 個 | `GET_MARK = (338, 228, 50, 50)  # x, y, w, h: the GET! popup's icon corner, its gift's tier` |
| `agent/shop.py:119` | `50` -> `51` | 9 個 | `GET_MARK = (338, 228, 50, 50)  # x, y, w, h: the GET! popup's icon corner, its gift's tier` |
| `agent/shop.py:122` | `500` -> `501` | 9 個 | `EX_GET_PX = 500` |
| `agent/shop.py:128` | `>=` -> `>` | 65 個 | `return int(green(image[y:y + h, x:x + w]).sum()) >= EX_GET_PX` |
| `agent/shop.py:147` | `>=` -> `>` | 63 個 | `if not len(rows) or rows[0] + 32 >= h:` |
| `agent/shop.py:147` | `32` -> `33` | 63 個 | `if not len(rows) or rows[0] + 32 >= h:` |
| `agent/shop.py:149` | `6` -> `7` | 9 個 | `return numeral(mask, rows[0] + 6, rows[0] + 32)` |
| `agent/shop.py:149` | `32` -> `33` | 9 個 | `return numeral(mask, rows[0] + 6, rows[0] + 32)` |
| `agent/shop.py:152` | `298` -> `299` | 9 個 | `FORECAST_NUMERAL = (298, 452, 34, 34)  # x, y, w, h: the Forecasts row's numeral on the fu` |
| `agent/shop.py:152` | `452` -> `453` | 9 個 | `FORECAST_NUMERAL = (298, 452, 34, 34)  # x, y, w, h: the Forecasts row's numeral on the fu` |
| `agent/shop.py:152` | `34` -> `35` | 9 個 | `FORECAST_NUMERAL = (298, 452, 34, 34)  # x, y, w, h: the Forecasts row's numeral on the fu` |
| `agent/shop.py:152` | `34` -> `35` | 9 個 | `FORECAST_NUMERAL = (298, 452, 34, 34)  # x, y, w, h: the Forecasts row's numeral on the fu` |
| `agent/shop.py:164` | `<` -> `<=` | 75 個 | `if len(rows) < 8:` |
| `agent/shop.py:164` | `8` -> `9` | 75 個 | `if len(rows) < 8:` |
| `agent/shop.py:166` | `0` -> `1` | 9 個 | `t = numeral(mask, rows[0] + 2, rows[-1] - 3)` |
| `agent/shop.py:166` | `2` -> `3` | 9 個 | `t = numeral(mask, rows[0] + 2, rows[-1] - 3)` |
| `agent/shop.py:166` | `1` -> `2` | 9 個 | `t = numeral(mask, rows[0] + 2, rows[-1] - 3)` |
| `agent/shop.py:166` | `3` -> `4` | 9 個 | `t = numeral(mask, rows[0] + 2, rows[-1] - 3)` |
| `agent/shop.py:260` | `and` -> `or` | 39 個 | `return sum(owned) == 5 and owned[2] == 0` |
| `agent/shop.py:328` | `1` -> `2` | 32 個 | `out.append(((0, n) if opens else (1, at), slot, entry if opens else None, why))` |
| `agent/shop.py:410` | `70` -> `71` | 9 個 | `PRICE_LIT_G, PRICE_LIT_RG, PRICE_LIT_B = 70, 60, 60` |
| `agent/shop.py:410` | `60` -> `61` | 9 個 | `PRICE_LIT_G, PRICE_LIT_RG, PRICE_LIT_B = 70, 60, 60` |
| `agent/shop.py:411` | `8` -> `9` | 9 個 | `PICKED_BAND, PICKED_MIN = 8, 0.2  # px just inside an option's frame; orange share 0.452-0` |
| `agent/shop.py:418` | `1` -> `2` | 6 個 | `px = image[y:y + h, x:x + w].reshape(-1, 3)` |
| `agent/shop.py:419` | `>` -> `>=` | 6 個 | `px = px[px.max(axis=1) > 100]` |
| `agent/shop.py:419` | `100` -> `101` | 6 個 | `px = px[px.max(axis=1) > 100]` |
| `agent/shop.py:421` | `return x` -> `return None` | 1 個 | `return False` |
| `agent/shop.py:423` | `>=` -> `>` | 6 個 | `return bool(g >= PRICE_LIT_G and r - g >= PRICE_LIT_RG and b < PRICE_LIT_B)` |
| `agent/shop.py:423` | `<` -> `<=` | 6 個 | `return bool(g >= PRICE_LIT_G and r - g >= PRICE_LIT_RG and b < PRICE_LIT_B)` |
| `agent/shop.py:432` | `1` -> `2` | 8 個 | `band = np.concatenate([image[y:y + d, x:x + w].reshape(-1, 3), image[y + h - d:y + h, x:x ` |
| `agent/shop.py:432` | `1` -> `2` | 8 個 | `band = np.concatenate([image[y:y + d, x:x + w].reshape(-1, 3), image[y + h - d:y + h, x:x ` |
| `agent/shop.py:433` | `+` -> `-` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `-` -> `+` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `+` -> `-` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `+` -> `-` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `1` -> `2` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `+` -> `-` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `-` -> `+` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `+` -> `-` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `-` -> `+` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:433` | `1` -> `2` | 8 個 | `image[y + d:y + h - d, x:x + d].reshape(-1, 3), image[y + d:y + h - d, x + w - d:x + w].re` |
| `agent/shop.py:435` | `>=` -> `>` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `>` -> `>=` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `120` -> `121` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `>` -> `>=` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `30` -> `31` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `<` -> `<=` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `140` -> `141` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `<` -> `<=` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `60` -> `61` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `>` -> `>=` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `+` -> `-` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:435` | `40` -> `41` | 8 個 | `return bool(((r > 120) & (g > 30) & (g < 140) & (b < 60) & (r > g + 40)).mean() >= PICKED_` |
| `agent/shop.py:454` | `//` -> `/` | 77 個 | `for t, x, y, h in sorted(lines, key=lambda line: (line[2] // 40, line[1])):` |
| `agent/shop.py:454` | `40` -> `41` | 77 個 | `for t, x, y, h in sorted(lines, key=lambda line: (line[2] // 40, line[1])):` |
| `agent/shop.py:454` | `1` -> `2` | 77 個 | `for t, x, y, h in sorted(lines, key=lambda line: (line[2] // 40, line[1])):` |
| `agent/shop.py:455` | `<` -> `<=` | 74 個 | `if (h < 18 and sum(c.isdigit() for c in t) < 3) or has_letters(t):` |
| `agent/shop.py:455` | `3` -> `4` | 74 個 | `if (h < 18 and sum(c.isdigit() for c in t) < 3) or has_letters(t):` |
| `agent/shop.py:457` | `<` -> `<=` | 74 個 | `near = [(u, uy) for u, ux, uy, _ in lines if abs(ux - x) < 75 and u != t]` |
| `agent/shop.py:457` | `75` -> `76` | 74 個 | `near = [(u, uy) for u, ux, uy, _ in lines if abs(ux - x) < 75 and u != t]` |
| `agent/shop.py:458` | `<` -> `<=` | 74 個 | `name = next((u for u, uy in near if 10 < uy - y < 40), "")` |
| `agent/shop.py:458` | `<` -> `<=` | 74 個 | `name = next((u for u, uy in near if 10 < uy - y < 40), "")` |
| `agent/shop.py:458` | `10` -> `11` | 74 個 | `name = next((u for u, uy in near if 10 < uy - y < 40), "")` |
| `agent/shop.py:458` | `40` -> `41` | 74 個 | `name = next((u for u, uy in near if 10 < uy - y < 40), "")` |
| `agent/shop.py:465` | `<` -> `<=` | 74 個 | `"purchased": any(has(u, "Purchased") for u, uy in near if -110 < uy - y < 0),` |
| `agent/shop.py:465` | `<` -> `<=` | 74 個 | `"purchased": any(has(u, "Purchased") for u, uy in near if -110 < uy - y < 0),` |
| `agent/shop.py:465` | `110` -> `111` | 74 個 | `"purchased": any(has(u, "Purchased") for u, uy in near if -110 < uy - y < 0),` |
| `agent/shop.py:465` | `0` -> `1` | 74 個 | `"purchased": any(has(u, "Purchased") for u, uy in near if -110 < uy - y < 0),` |
| `agent/shop.py:466` | `<` -> `<=` | 74 個 | `"short": any(has(u, "Enough") for u, uy in near if -110 < uy - y < 0),  # red "Not Enough ` |
| `agent/shop.py:466` | `<` -> `<=` | 74 個 | `"short": any(has(u, "Enough") for u, uy in near if -110 < uy - y < 0),  # red "Not Enough ` |
| `agent/shop.py:466` | `110` -> `111` | 74 個 | `"short": any(has(u, "Enough") for u, uy in near if -110 < uy - y < 0),  # red "Not Enough ` |
| `agent/shop.py:466` | `0` -> `1` | 74 個 | `"short": any(has(u, "Enough") for u, uy in near if -110 < uy - y < 0),  # red "Not Enough ` |
| `agent/shop.py:476` | `>` -> `>=` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `110` -> `111` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `<` -> `<=` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `60` -> `61` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `<` -> `<=` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `60` -> `61` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `>` -> `>=` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:476` | `3` -> `4` | 28 個 | `return int(((r > 110) & (g < 60) & (b < 60) & (r > 3 * g)).sum())` |
| `agent/shop.py:487` | `>=` -> `>` | 28 個 | `return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90` |
| `agent/shop.py:487` | `40` -> `41` | 28 個 | `return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90` |
| `agent/shop.py:487` | `66` -> `67` | 28 個 | `return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90` |
| `agent/shop.py:487` | `30` -> `31` | 28 個 | `return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90` |
| `agent/shop.py:487` | `30` -> `31` | 28 個 | `return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90` |
| `agent/shop.py:487` | `90` -> `91` | 28 個 | `return red_pixels(image[y + 40:y + 66, x - 30:x + 30]) >= 90` |
| `agent/shop.py:516` | `<` -> `<=` | 14 個 | `return (abs(a["x"] - b["x"]) < 30 and a["price"] == b["price"]` |
| `agent/shop.py:516` | `30` -> `31` | 14 個 | `return (abs(a["x"] - b["x"]) < 30 and a["price"] == b["price"]` |
| `agent/shop.py:517` | `>=` -> `>` | 5 個 | `and SequenceMatcher(None, a["name"].lower(), b["name"].lower()).ratio() >= 0.8)` |
| `agent/shop.py:565` | `+` -> `-` | 46 個 | `tx, ty = x + w // 2, y + h // 2` |
| `agent/shop.py:565` | `//` -> `/` | 46 個 | `tx, ty = x + w // 2, y + h // 2` |
| `agent/shop.py:565` | `2` -> `3` | 46 個 | `tx, ty = x + w // 2, y + h // 2` |
| `agent/shop.py:565` | `//` -> `/` | 46 個 | `tx, ty = x + w // 2, y + h // 2` |
| `agent/shop.py:565` | `2` -> `3` | 46 個 | `tx, ty = x + w // 2, y + h // 2` |
| `agent/shop.py:566` | `<` -> `<=` | 46 個 | `if not t.isdigit() or h < 15:` |
| `agent/shop.py:566` | `15` -> `16` | 46 個 | `if not t.isdigit() or h < 15:` |
| `agent/shop.py:568` | `<` -> `<=` | 46 個 | `i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60` |
| `agent/shop.py:568` | `40` -> `41` | 46 個 | `i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60` |
| `agent/shop.py:568` | `<` -> `<=` | 46 個 | `i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60` |
| `agent/shop.py:568` | `<` -> `<=` | 46 個 | `i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60` |
| `agent/shop.py:568` | `35` -> `36` | 46 個 | `i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60` |
| `agent/shop.py:568` | `60` -> `61` | 46 個 | `i = next((i for i, (cx, cy) in enumerate(cells) if abs(tx - cx) < 40 and 35 < ty - cy < 60` |
| `agent/shop.py:592` | `190` -> `191` | 9 個 | `SHOP_TITLE = (190, 108, 130, 30)  # x, y, w, h: the title on the main page's plate, top le` |
| `agent/shop.py:592` | `108` -> `109` | 9 個 | `SHOP_TITLE = (190, 108, 130, 30)  # x, y, w, h: the title on the main page's plate, top le` |
| `agent/shop.py:592` | `130` -> `131` | 9 個 | `SHOP_TITLE = (190, 108, 130, 30)  # x, y, w, h: the title on the main page's plate, top le` |
| `agent/shop.py:592` | `30` -> `31` | 9 個 | `SHOP_TITLE = (190, 108, 130, 30)  # x, y, w, h: the title on the main page's plate, top le` |
| `agent/shop.py:603` | `>` -> `>=` | 80 個 | `return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)` |
| `agent/shop.py:603` | `>` -> `>=` | 80 個 | `return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)` |
| `agent/shop.py:603` | `<` -> `<=` | 80 個 | `return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)` |
| `agent/shop.py:603` | `70` -> `71` | 80 個 | `return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)` |
| `agent/shop.py:603` | `<` -> `<=` | 80 個 | `return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)` |
| `agent/shop.py:603` | `70` -> `71` | 80 個 | `return bool(((r > 150) & (g < 70) & (b < 70)).mean() > 0.1)` |
| `agent/shop.py:659` | `367` -> `368` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `213` -> `214` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `228` -> `229` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `352` -> `353` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `505` -> `506` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `352` -> `353` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `367` -> `368` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `213` -> `214` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `235` -> `236` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `262` -> `263` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `495` -> `496` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `262` -> `263` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `235` -> `236` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `367` -> `368` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `495` -> `496` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:659` | `367` -> `368` | 9 個 | `FUSE_SLOTS = {3: [(367, 213), (228, 352), (505, 352)], 5: [(367, 213), (235, 262), (495, 2` |
| `agent/shop.py:668` | `<` -> `<=` | 12 個 | `return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3` |
| `agent/shop.py:668` | `237` -> `238` | 12 個 | `return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3` |
| `agent/shop.py:668` | `287` -> `288` | 12 個 | `return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3` |
| `agent/shop.py:668` | `210` -> `211` | 12 個 | `return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3` |
| `agent/shop.py:668` | `260` -> `261` | 12 個 | `return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3` |
| `agent/shop.py:668` | `10` -> `11` | 12 個 | `return 5 if image[237:287, 210:260].max(axis=2).mean() < 10 else 3` |
| `agent/shop.py:673` | `>` -> `>=` | 9 個 | `return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUS` |
| `agent/shop.py:673` | `25` -> `26` | 9 個 | `return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUS` |
| `agent/shop.py:673` | `25` -> `26` | 9 個 | `return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUS` |
| `agent/shop.py:673` | `25` -> `26` | 9 個 | `return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUS` |
| `agent/shop.py:673` | `25` -> `26` | 9 個 | `return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUS` |
| `agent/shop.py:673` | `15` -> `16` | 9 個 | `return sum(int(image[y - 25:y + 25, x - 25:x + 25].max(axis=2).std() > 15) for x, y in FUS` |
| `agent/shop.py:694` | `<=` -> `<` | 83 個 | `if [c["i"] for c in cells] != list(range(len(cells))) or not set(gone) <= {c["i"] for c in` |
| `agent/shop.py:721` | `600` -> `601` | 9 個 | `TOOLTIP_AREA = (600, 200, 680, 330)  # x, y, w, h: where a fuse page tooltip's head shows,` |
| `agent/shop.py:721` | `200` -> `201` | 9 個 | `TOOLTIP_AREA = (600, 200, 680, 330)  # x, y, w, h: where a fuse page tooltip's head shows,` |
| `agent/shop.py:721` | `680` -> `681` | 9 個 | `TOOLTIP_AREA = (600, 200, 680, 330)  # x, y, w, h: where a fuse page tooltip's head shows,` |
| `agent/shop.py:721` | `330` -> `331` | 9 個 | `TOOLTIP_AREA = (600, 200, 680, 330)  # x, y, w, h: where a fuse page tooltip's head shows,` |
| `agent/shop.py:722` | `120` -> `121` | 9 個 | `TOOLTIP_HEAD = 120  # px of unbroken red on one row: a tooltip's head 288-290 (189 cut), t` |
| `agent/shop.py:735` | `+` -> `-` | 128 個 | `b, g, r = (image[y:y + h, x:x + w, i].astype(int) for i in range(3))` |
| `agent/shop.py:736` | `>` -> `>=` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `120` -> `121` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `>` -> `>=` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `40` -> `41` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `>` -> `>=` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `+` -> `-` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `2` -> `3` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:736` | `40` -> `41` | 128 個 | `red = (r > 120) & (r > 2 * g + 40) & (r > 2 * b + 40)` |
| `agent/shop.py:737` | `0` -> `1` | 128 個 | `runs = np.cumsum(np.pad(red, ((0, 0), (1, 0))), axis=1)  # a row's red px up to each colum` |
| `agent/shop.py:737` | `0` -> `1` | 128 個 | `runs = np.cumsum(np.pad(red, ((0, 0), (1, 0))), axis=1)  # a row's red px up to each colum` |
| `agent/shop.py:737` | `1` -> `2` | 128 個 | `runs = np.cumsum(np.pad(red, ((0, 0), (1, 0))), axis=1)  # a row's red px up to each colum` |
| `agent/shop.py:737` | `0` -> `1` | 128 個 | `runs = np.cumsum(np.pad(red, ((0, 0), (1, 0))), axis=1)  # a row's red px up to each colum` |
| `agent/shop.py:741` | `720` -> `721` | 9 個 | `def picked(image, x, y, bottom=720):` |
| `agent/shop.py:749` | `-` -> `+` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `40` -> `41` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `34` -> `35` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `-` -> `+` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `30` -> `31` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `+` -> `-` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `30` -> `31` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `1` -> `2` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `34` -> `35` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `+` -> `-` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `40` -> `41` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `-` -> `+` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `30` -> `31` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `+` -> `-` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `30` -> `31` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:749` | `1` -> `2` | 9 個 | `ring = np.concatenate([image[y - 40:y - 34, x - 30:x + 30].reshape(-1, 3), image[y + 34:y ` |
| `agent/shop.py:750` | `-` -> `+` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `30` -> `31` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `+` -> `-` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `30` -> `31` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `-` -> `+` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `40` -> `41` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `34` -> `35` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `1` -> `2` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `-` -> `+` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `30` -> `31` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `+` -> `-` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `30` -> `31` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `34` -> `35` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `+` -> `-` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `40` -> `41` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:750` | `1` -> `2` | 9 個 | `image[y - 30:y + 30, x - 40:x - 34].reshape(-1, 3), image[y - 30:y + 30, x + 34:x + 40].re` |
| `agent/shop.py:752` | `>` -> `>=` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `>` -> `>=` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `200` -> `201` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `>` -> `>=` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `100` -> `101` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `<` -> `<=` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `200` -> `201` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `<` -> `<=` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/shop.py:752` | `80` -> `81` | 9 個 | `return ((r > 200) & (g > 100) & (g < 200) & (b < 80)).mean() > 0.08` |
| `agent/map_route.py:17` | `8` -> `9` | 12 個 | `FAINT_LINK = 8` |
| `agent/map_route.py:72` | `0` -> `1` | 46 個 | `return sorted(rows, key=lambda r: (best[r][0], -(slots[r][1] or 0), ROWS.index(r)))` |
| `agent/map_route.py:106` | `>=` -> `>` | 51 個 | `read = {pair for pair, c in reads.items() if c >= LINE_CONTRAST}` |
| `agent/map_route.py:110` | `>=` -> `>` | 50 個 | `if c >= FAINT_LINK:` |
| `agent/map_route.py:125` | `56` -> `57` | 12 個 | `def line_contrast(v, x0, y0, x1, y1, top=56, bottom=615):` |
| `agent/map_route.py:125` | `615` -> `616` | 12 個 | `def line_contrast(v, x0, y0, x1, y1, top=56, bottom=615):` |
| `agent/map_route.py:132` | `-` -> `+` | 64 個 | `n = np.array([y0 - y1, x1 - x0], float)` |
| `agent/map_route.py:134` | `25` -> `26` | 64 個 | `ts = np.linspace(0.3, 0.7, 25)` |
| `agent/map_route.py:139` | `&` -> `|` | 64 個 | `ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)` |
| `agent/map_route.py:139` | `>=` -> `>` | 64 個 | `ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)` |
| `agent/map_route.py:139` | `0` -> `1` | 64 個 | `ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)` |
| `agent/map_route.py:139` | `<` -> `<=` | 64 個 | `ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)` |
| `agent/map_route.py:139` | `>=` -> `>` | 64 個 | `ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)` |
| `agent/map_route.py:139` | `<` -> `<=` | 64 個 | `ok = (xs >= 0) & (xs < v.shape[1]) & (ys >= top) & (ys < bottom)` |
| `agent/map_route.py:140` | `>` -> `>=` | 64 個 | `return float(v[ys[ok], xs[ok]].mean()) if ok.mean() > 0.6 else None` |
| `agent/map_route.py:142` | `4` -> `5` | 64 個 | `on = [mean(o) for o in range(-4, 5, 2)]  # links are ~5 px wide; the centre may be off by ` |
| `agent/map_route.py:142` | `5` -> `6` | 64 個 | `on = [mean(o) for o in range(-4, 5, 2)]  # links are ~5 px wide; the centre may be off by ` |
| `agent/map_route.py:143` | `13` -> `14` | 64 個 | `sides = mean(13), mean(-13)` |
| `agent/map_route.py:149` | `230` -> `231` | 12 個 | `def shift(before, after, most, top=230, bottom=600, right=1200):` |
| `agent/map_route.py:149` | `600` -> `601` | 12 個 | `def shift(before, after, most, top=230, bottom=600, right=1200):` |
| `agent/map_route.py:149` | `1200` -> `1201` | 12 個 | `def shift(before, after, most, top=230, bottom=600, right=1200):` |
| `agent/map_route.py:156` | `4` -> `5` | 14 個 | `a, b = (f[top:bottom:4, :right].astype(np.int16) for f in (before, after))` |
| `agent/map_route.py:157` | `1` -> `2` | 14 個 | `errs = np.array([np.abs(a[:, s:] - b[:, :right - s]).mean() for s in range(most + 1)])` |
| `agent/map_route.py:159` | `<` -> `<=` | 14 個 | `return s if errs[s] < SHIFT_CLEAR * np.median(errs) else None` |
| `agent/map_route.py:164` | `+` -> `-` | 44 個 | `seen = [line_contrast(v, cx, cy, cx + COLUMN_DX, cy + dy) for dy in ROW_DY.values()]` |
| `agent/map_route.py:166` | `>=` -> `>` | 44 個 | `return sum(c >= LINE_CONTRAST for c in seen) if seen else None` |
| `agent/gifts.py:135` | `99` -> `100` | 96 個 | `room = slots or 99` |
| `agent/gift_cells.py:11` | `0.5` -> `1.5` | 11 個 | `ICON_MIN = 0.5` |
| `agent/gift_cells.py:12` | `0.1` -> `1.1` | 11 個 | `ICON_MARGIN = 0.1  # the best icon over the second best: a tie is two lookalikes, not a gi` |
| `agent/gift_cells.py:13` | `0.75` -> `1.75` | 11 個 | `ICON_SURE = 0.75  # an icon this good ends the matching of a cell's candidates: its lookal` |
| `agent/gift_cells.py:35` | `or` -> `and` | 7 個 | `if keyword is None or tier is None:` |
| `agent/gift_cells.py:57` | `<` -> `<=` | 7 個 | `if not ranked or ranked[0][1] < ICON_MIN or (len(ranked) > 1 and ranked[0][1] - ranked[1][` |
| `agent/gift_cells.py:57` | `<` -> `<=` | 7 個 | `if not ranked or ranked[0][1] < ICON_MIN or (len(ranked) > 1 and ranked[0][1] - ranked[1][` |
| `agent/gift_cells.py:64` | `-x` -> `x` | 11 個 | `PLATE_DX, PLATE_DY, PLATE_W, PLATE_H = -76, 64, 152, 26` |
| `agent/gift_cells.py:64` | `76` -> `77` | 11 個 | `PLATE_DX, PLATE_DY, PLATE_W, PLATE_H = -76, 64, 152, 26` |
| `agent/gift_cells.py:64` | `64` -> `65` | 11 個 | `PLATE_DX, PLATE_DY, PLATE_W, PLATE_H = -76, 64, 152, 26` |
| `agent/gift_cells.py:64` | `152` -> `153` | 11 個 | `PLATE_DX, PLATE_DY, PLATE_W, PLATE_H = -76, 64, 152, 26` |
| `agent/gift_cells.py:64` | `26` -> `27` | 11 個 | `PLATE_DX, PLATE_DY, PLATE_W, PLATE_H = -76, 64, 152, 26` |
| `agent/team_queue.py:58` | `return x` -> `return None` | 8 個 | `return f"team queue: {team_id!r} to the end, next {teams[0]['id']!r}"` |
| `agent/team_queue.py:106` | `3` -> `4` | 39 個 | `for _ in range(3):` |
| `agent/team_queue.py:114` | `return x` -> `return None` | 11 個 | `return teams` |
| `agent/luxcavation.py:12` | `2` -> `3` | 12 個 | `THREAD_COST = 2  # a Thread Luxcavation battle's, every level of Lust's Level Select (live` |
| `agent/pack_cover.py:37` | `1` -> `2` | 9 個 | `part = np.add.reduceat(part, edges[:-1], axis=axis) / np.diff(edges).reshape((-1, 1, 1) if` |
| `agent/pack_cover.py:37` | `1` -> `2` | 9 個 | `part = np.add.reduceat(part, edges[:-1], axis=axis) / np.diff(edges).reshape((-1, 1, 1) if` |
| `agent/pack_cover.py:50` | `1` -> `2` | 1 個 | `return {name: np.frombuffer(base64.b64decode(b), np.uint8).reshape(-1, COLUMNS, 3) for nam` |
| `agent/pack_cover.py:56` | `+` -> `-` | 11 個 | `return float(a @ b / (np.sqrt((a @ a) * (b @ b)) + 1e-6))` |
| `agent/pack_cover.py:56` | `1e-06` -> `1.000001` | 11 個 | `return float(a @ b / (np.sqrt((a @ a) * (b @ b)) + 1e-6))` |
| `agent/pack_cover.py:61` | `640` -> `641` | 19 個 | `centre = 640 + round((x - 640) / (PITCH / 2)) * PITCH / 2` |
| `agent/pack_cover.py:64` | `0` -> `1` | 19 個 | `return page[CARD_TOP:CARD_TOP + h, max(0, left):left + w]` |
| `agent/pack_cover.py:75` | `or` -> `and` | 8 個 | `if not scores or scores[0][0] < MIN_SCORE:` |
| `agent/pack_cover.py:75` | `<` -> `<=` | 8 個 | `if not scores or scores[0][0] < MIN_SCORE:` |
| `agent/pack_cover.py:77` | `>` -> `>=` | 7 個 | `if len(scores) > 1 and scores[0][0] - scores[1][0] < MIN_LEAD:` |
| `agent/pack_cover.py:77` | `1` -> `2` | 7 個 | `if len(scores) > 1 and scores[0][0] - scores[1][0] < MIN_LEAD:` |
| `agent/pack_cover.py:77` | `<` -> `<=` | 7 個 | `if len(scores) > 1 and scores[0][0] - scores[1][0] < MIN_LEAD:` |
| `agent/settings.py:110` | `if c:` -> `if not c:` | 12 個 | `if isinstance(team, dict):` |
| `agent/settings.py:199` | `not in` -> `in` | 119 個 | `dropped += sum(i not in known for i in ids)` |
| `agent/settings.py:245` | `3` -> `4` | 28 個 | `name = next(n for n in (base, *(f"{base} {i}" for i in range(2, len(names) + 3))) if n not` |
| `agent/settings.py:298` | `0` -> `1` | 29 個 | `team.setdefault("shop_refresh_keyword", team.pop("shop_refresh_limit", 0))` |
| `agent/settings.py:361` | call deleted | 158 個 | `super().__init__("Invalid settings:\n" + "\n".join(f"- {e}" for e in errors))` |
| `agent/settings.py:376` | `2` -> `3` | 12 個 | `f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")` |
| `agent/settings.py:377` | call deleted | 12 個 | `f.flush()` |
| `agent/settings.py:386` | `return x` -> `return None` | 11 個 | `return True` |
| `agent/settings.py:386` | `True` -> `False` | 11 個 | `return True` |
| `agent/settings.py:421` | `or` -> `and` | 233 個 | `if not isinstance(version, int) or isinstance(version, bool):` |
| `agent/settings.py:487` | `continue` -> `break` | 1 個 | `continue` |
| `agent/hub_text.py:33` | `960` -> `961` | 13 個 | `DET_SIDE = 960  # the det model's max side (fastdeploy DBDetector's max_side_len)` |
| `agent/hub_text.py:34` | `16` -> `17` | 13 個 | `GAP = 16  # black rows between two groups of rois on the det canvas, so det joins no text ` |
| `agent/hub_text.py:59` | `0` -> `1` | 3 個 | `iw = max(0, min(x + w, rx + rw) - max(x, rx))` |
| `agent/hub_text.py:60` | `0` -> `1` | 3 個 | `ih = max(0, min(y + h, ry + rh) - max(y, ry))` |
| `agent/hub_text.py:61` | `>` -> `>=` | 3 個 | `return w * h > 0 and iw * ih >= INSIDE * w * h` |
| `agent/hub_text.py:61` | `*` -> `/` | 3 個 | `return w * h > 0 and iw * ih >= INSIDE * w * h` |
| `agent/hub_text.py:61` | `0` -> `1` | 3 個 | `return w * h > 0 and iw * ih >= INSIDE * w * h` |
| `agent/hub_text.py:68` | `<` -> `<=` | 3 個 | `if score < threshold or not inside(box, roi):` |
| `agent/hub_text.py:74` | `return x` -> `return None` | 3 個 | `return False` |
| `agent/hub_text.py:119` | `<=` -> `<` | 2 個 | `if groups and union(groups[-1] + [roi])[2] <= DET_SIDE:` |
| `agent/hub_text.py:123` | `0` -> `1` | 2 個 | `placed, top = [], 0` |
| `agent/hub_text.py:127` | `2` -> `3` | 2 個 | `size = max(u[2] for u, _ in placed), top - GAP` |
| `agent/hub_text.py:127` | `-` -> `+` | 2 個 | `size = max(u[2] for u, _ in placed), top - GAP` |
| `agent/hub_text.py:128` | `>` -> `>=` | 2 個 | `return None if len(placed) == 1 or max(size) > DET_SIDE else (placed, size)` |
| `agent/hub_text.py:133` | `0` -> `1` | 2 個 | `detail = context.run_recognition_direct(JRecognitionType.OCR, JOCR(roi=tuple(roi), thresho` |
| `agent/hub_text.py:142` | `0` -> `1` | 1 個 | `canvas = np.zeros((max(h, masked.shape[0]), max(w, masked.shape[1]), 3), masked.dtype)` |
| `agent/hub_text.py:142` | `1` -> `2` | 1 個 | `canvas = np.zeros((max(h, masked.shape[0]), max(w, masked.shape[1]), 3), masked.dtype)` |
| `agent/hub_text.py:146` | `0` -> `1` | 1 個 | `for (bx, by, bw, bh), text, score in read(context, canvas, (0, 0, w, h)):` |
| `agent/hub_text.py:146` | `0` -> `1` | 1 個 | `for (bx, by, bw, bh), text, score in read(context, canvas, (0, 0, w, h)):` |
| `agent/hub_text.py:148` | `<=` -> `<` | 1 個 | `if top <= by + bh / 2 < top + gh:` |
| `agent/hub_text.py:148` | `<` -> `<=` | 1 個 | `if top <= by + bh / 2 < top + gh:` |
| `agent/hub_text.py:148` | `+` -> `-` | 1 個 | `if top <= by + bh / 2 < top + gh:` |
| `agent/hub_text.py:148` | `2` -> `3` | 1 個 | `if top <= by + bh / 2 < top + gh:` |
| `agent/hub_text.py:150` | `break` -> `continue` | 1 個 | `break` |
| `agent/hub_text.py:169` | call deleted | 沒有測試執行 | `nodes.append((entry, reco["type"], ocr_specs(reco)))` |
| `agent/hub_text.py:170` | `return x` -> `return None` | 3 個 | `return nodes, [s[0] for *_, specs in nodes for s in specs or []]` |
| `agent/hub_text.py:170` | `0` -> `1` | 3 個 | `return nodes, [s[0] for *_, specs in nodes for s in specs or []]` |
| `agent/hub_text.py:170` | `or` -> `and` | 3 個 | `return nodes, [s[0] for *_, specs in nodes for s in specs or []]` |
| `agent/hub_text.py:188` | `if c:` -> `if not c:` | 沒有測試執行 | `if argv.node_name not in self.lists:` |
| `agent/hub_text.py:188` | `not in` -> `in` | 沒有測試執行 | `if argv.node_name not in self.lists:` |
| `agent/hub_text.py:191` | `if c:` -> `if not c:` | 沒有測試執行 | `if not (picked := pick(nodes, ocr_pass(context, argv.image, rois))):` |
| `agent/hub_text.py:191` | `not x` -> `x` | 沒有測試執行 | `if not (picked := pick(nodes, ocr_pass(context, argv.image, rois))):` |
| `agent/hub_text.py:193` | call deleted | 沒有測試執行 | `context.override_next(argv.node_name, ["NoBatchOCR", *picked, *param["tail"]])` |
| `agent/hub_text.py:194` | `return x` -> `return None` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})` |
| `agent/hub_text.py:194` | `0` -> `1` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})` |
| `agent/hub_text.py:194` | `0` -> `1` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})` |
| `agent/hub_text.py:194` | `1` -> `2` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})` |
| `agent/hub_text.py:194` | `1` -> `2` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(0, 0, 1, 1), detail={"picked": picked})` |
| `agent/pass_missions.py:22` | `100` -> `101` | 12 個 | `LIT = 100  # orange pixels of the coin's 40 x 40 square: lit; a claimed row's grey coin ha` |
| `agent/pass_missions.py:23` | `50` -> `51` | 12 個 | `STAMP = 50  # red pixels of the CLEAR stamp (x 600-700): ~180 where it is, 0 where it is n` |
| `agent/pass_missions.py:24` | `170` -> `171` | 12 個 | `BAR = 170  # of the bar's 175 columns bright: full` |
| `agent/pass_missions.py:29` | `20` -> `21` | 18 個 | `b, g, r = (image[y - 20:y + 20, 350:390, i].astype(int) for i in range(3))` |
| `agent/pass_missions.py:29` | `20` -> `21` | 18 個 | `b, g, r = (image[y - 20:y + 20, 350:390, i].astype(int) for i in range(3))` |
| `agent/pass_missions.py:29` | `350` -> `351` | 18 個 | `b, g, r = (image[y - 20:y + 20, 350:390, i].astype(int) for i in range(3))` |
| `agent/pass_missions.py:29` | `390` -> `391` | 18 個 | `b, g, r = (image[y - 20:y + 20, 350:390, i].astype(int) for i in range(3))` |
| `agent/pass_missions.py:30` | `-` -> `+` | 18 個 | `stamp = image[y - 25:y + 25, 600:700].astype(int)` |
| `agent/pass_missions.py:30` | `25` -> `26` | 18 個 | `stamp = image[y - 25:y + 25, 600:700].astype(int)` |
| `agent/pass_missions.py:30` | `+` -> `-` | 18 個 | `stamp = image[y - 25:y + 25, 600:700].astype(int)` |
| `agent/pass_missions.py:30` | `25` -> `26` | 18 個 | `stamp = image[y - 25:y + 25, 600:700].astype(int)` |
| `agent/pass_missions.py:30` | `600` -> `601` | 18 個 | `stamp = image[y - 25:y + 25, 600:700].astype(int)` |
| `agent/pass_missions.py:30` | `700` -> `701` | 18 個 | `stamp = image[y - 25:y + 25, 600:700].astype(int)` |
| `agent/pass_missions.py:31` | `>` -> `>=` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `150` -> `151` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `<` -> `<=` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `1` -> `2` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `60` -> `61` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `<` -> `<=` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `0` -> `1` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:31` | `60` -> `61` | 18 個 | `red = ((stamp[..., 2] > 150) & (stamp[..., 1] < 60) & (stamp[..., 0] < 60)).sum()` |
| `agent/pass_missions.py:32` | `>` -> `>=` | 18 個 | `full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()` |
| `agent/pass_missions.py:32` | `10` -> `11` | 18 個 | `full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()` |
| `agent/pass_missions.py:32` | `22` -> `23` | 18 個 | `full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()` |
| `agent/pass_missions.py:32` | `420` -> `421` | 18 個 | `full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()` |
| `agent/pass_missions.py:32` | `595` -> `596` | 18 個 | `full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()` |
| `agent/pass_missions.py:32` | `150` -> `151` | 18 個 | `full = (image[y + 10:y + 22, 420:595].astype(int).mean(axis=2) > 150).any(axis=0).sum()` |
| `agent/pass_missions.py:33` | `>` -> `>=` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `>` -> `>=` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `200` -> `201` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `>` -> `>=` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `100` -> `101` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `<` -> `<=` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `80` -> `81` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `>=` -> `>` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:33` | `>=` -> `>` | 18 個 | `return ((r > 200) & (g > 100) & (b < 80)).sum() > LIT, red >= STAMP, full >= BAR` |
| `agent/pass_missions.py:63` | `or` -> `and` | 沒有測試執行 | `rows = claimable(np.asarray(argv.image), (json.loads(argv.custom_recognition_param or "nul` |
| `agent/pass_missions.py:63` | `or` -> `and` | 沒有測試執行 | `rows = claimable(np.asarray(argv.image), (json.loads(argv.custom_recognition_param or "nul` |
| `agent/pass_missions.py:63` | `0` -> `1` | 沒有測試執行 | `rows = claimable(np.asarray(argv.image), (json.loads(argv.custom_recognition_param or "nul` |
| `agent/pass_missions.py:64` | `return x` -> `return None` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `-` -> `+` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `0` -> `1` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `0` -> `1` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `20` -> `21` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `-` -> `+` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `0` -> `1` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `1` -> `2` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `20` -> `21` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `40` -> `41` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |
| `agent/pass_missions.py:64` | `40` -> `41` | 沒有測試執行 | `return CustomRecognition.AnalyzeResult(box=(rows[0][0] - 20, rows[0][1] - 20, 40, 40), det` |

</details>
