# maalc

用 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 自動化 Limbus Company 鏡牢的工具。規格見 [docs/spec](docs/spec/README.md)。

## 下載與執行（Windows x64）

1. 從 [Releases](https://github.com/EnderWolf50/maalc/releases) 下載 `maalc-<版本>.zip`，解壓縮到任意資料夾，得到一個 `maalc/` 資料夾。
2. 執行 `maalc-gui.exe` 編輯設定（隊伍、方案、覆寫），設定存在 `config/settings.json`。
3. 在 `maalc-gui.exe` 的「執行」分頁勾選要跑的任務、設好每個任務的選項與模擬器，按「開始」。視窗用 `python/` 內附的 Python 啟動 Agent，不需要另外安裝 Python。

下一版起由設定視窗自己執行任務，zip 不再附 MXU，也不再支援 MFAAvalonia（[ADR 0015](docs/adr/0015-settings-window-runs-the-tasks.md)）。「執行」分頁、定時執行與自動更新由 #811 的其他票加入；v1.0.0 仍用 zip 附的 MXU 執行，說明見 v1.0.0 的 README。

從 v1.0.0 升級：把新 zip 解壓到新資料夾，再把舊資料夾的 `config/` 複製過去。設定視窗第一次打開時把設定檔升到版本 23，舊檔另存成 `config/settings.v22.json`。MXU 裡設過的任務選項目前還不會讀回（#811 會做），升級後的任務選項是預設值；webhook 在 MXU 裡加密存放，一定要重填。

### 鏡牢與全域的任務選項

鏡牢怎麼跑（難度、目標層數、局數上限、每週獎勵、星光買不起時、全滅重打、這次從哪一支隊伍開始）存在設定檔的 `run`。失敗通知 webhook、自動同意使用者條款、自動接受下載與更新、關畫面前存截圖是**全域選項**，每個任務都會用到，也在 `run`。「執行」分頁編輯它們（#811），在那之前存檔會保留檔案裡的值。

「這次從哪一支隊伍開始」（`run.start_team`）選了隊伍時，任務開第一局新局前把它排到設定視窗「隊伍佇列」的第一位，之後照佇列輪替；任務開始時已經在跑的那一局不受影響。設定檔會記住這個選擇，之後每次開始任務都會再排一次，所以**平常留預設的「照隊伍佇列」**。選的隊伍停用或已經刪掉時，任務在點任何東西之前停下。

每個選項的意思與預設見 [spec 04 第 5 節](docs/spec/04-settings.md#5-執行選項run)。任務開始時，記錄裡有一行 `options: ...` 列出這次讀到的值，webhook 只寫有沒有設定。

### 辨識失敗時的截圖

辨識沒對上時，MaaFramework 會把當下的畫面存進 `debug/on_error/`，回報問題時請附上。

## 日常任務

鏡牢以外的日常各是一個獨立任務，在設定視窗的任務清單裡勾選、排序（設定檔的 `tasks`，[spec 04 第 14 節](docs/spec/04-settings.md#14-任務清單模擬器與排程tasksemulatorschedules)）：

| 任務 | 做什麼 |
|---|---|
| 換腦啡肽模組（`AssembleModules`） | 把腦啡肽換成腦啡肽模組，沒有參數 |
| 經驗本（`ExpLuxcavation`） | 打 EXP 分頁最右邊已開放的最難關；預設用連戰（Consecutive Battle）一場打完，可在任務選項（`consecutive`）關掉 |
| 紐本（`ThreadLuxcavation`） | 打 Thread 分頁今天開放的異想體，選最難的一級；連戰同經驗本 |
| 領通行證任務（`ClaimPassMissions`） | 領 Limbus Pass 的 Daily、Weekly、Seasonal 任務，沒有參數 |
| 領信（`ClaimMail`） | 信箱 Claim All，沒有參數 |
| 狂氣換腦啡肽（`ChargeEnkephalin`） | 用 Lunacy 換腦啡肽 |
| 鏡牢（`MirrorDungeon`） | 見 `maalc-gui.exe` 的其他分頁 |

每個日常都從主畫面開始、回到主畫面結束，所以任一個都可以單獨跑，順序也可以自己排。做完或「該跳過」（腦啡肽模組不夠、沒有可領的）都算成功，清單繼續下一個；卡住或出錯才算失敗。

### 建議順序

換腦啡肽模組 → 經驗本 → 紐本 → 換腦啡肽模組 → 領通行證任務 → 領信 → 鏡牢

- 第一次換腦啡肽模組：先把腦啡肽變成腦啡肽模組，後面的副本才有腦啡肽模組可花。
- 經驗本、紐本：每場花腦啡肽模組（經驗本 3、紐本 2），先於鏡牢，鏡牢開新局前會檢查腦啡肽模組至少 5 個（領獎要花 5 個），不夠就不開局。
- 第二次換腦啡肽模組：副本打完腦啡肽又回了一些，再換一次給鏡牢用。
- 領通行證任務：副本可能剛完成通行證任務，打完再領才領得到。
- 領信：放在鏡牢前，領到的獎勵先入帳。
- 鏡牢：最花時間，放最後。

### 日常的任務選項

經驗本、紐本與狂氣換腦啡肽怎麼跑，存在設定檔的 `luxcavation.exp`、`luxcavation.thread` 與 `charge_enkephalin`（[spec 04 第 12 節](docs/spec/04-settings.md#12-日常的任務選項luxcavationcharge_enkephalin)），「執行」分頁編輯它們（#811）。

- 經驗本、紐本（欄位相同）：
  - 模式（`mode`，**預設每日模式**）：
    - 每日模式：打今天還沒打的，今天已打贏的（手動打的也算）不再打。經驗本看通行證 Daily 分頁的 `Clear EXP Luxcavation`，還沒完成打 1 場、完成就不打；紐本看 Daily Bonuses，剩 n 次就打 n 場；讀不到就不打。
    - 自訂次數：這次打贏下面的場數，不看今天打過幾場（經驗本不開通行證頁）。
  - 這次要打贏的場數（`count`，經驗本預設 1、紐本預設 3）：自訂次數模式才用。打贏才算一場，戰敗不算。
  - 戰敗重打次數（`retries`，預設 0）：用完還輸就結束這個任務，清單繼續。
  - 連戰（`consecutive`，預設開）：一場 ×N 打完這次的場數，最多 ×10。
  - 隊伍（`team`）：`maalc-gui.exe` 裡的一支隊伍。bot 用那支隊伍的遊戲內隊伍欄位、出戰順序與防禦回合數，隊伍不必啟用。**預設沒選，沒選時任務一開始就停止**；選的隊伍刪掉了，任務也會停下，說那支隊伍已經刪掉，請改選。
  - 腦啡肽模組少於「最難關每場消耗 × 這次要打的場數」，就跳過整個任務。
- 狂氣換腦啡肽（`count`）：今天換到第幾次（0–10，**預設 0**，0 時什麼都不做）。**只有你設成大於 0，才會花 Lunacy**（先扣免費的，再扣付費的）；這是當天的目標：Use Lunacy 分頁的 Daily Count 已經到了就不換（手動換的也算），讀不到也不換。價格依當天已換次數是 26、52、78…最多 260，每次確認前核對價格是表上的下一格，不符就停；遊戲一天最多 10 次，到了就結束。
- 換腦啡肽模組、領通行證任務、領信、鏡牢的腦啡肽模組門檻：沒有參數。

### 兩個模擬器共用一個帳號

設定視窗一次只連一個模擬器（`emulator`）。兩個實例登入同一個帳號時，不要讓兩邊同時跑日常，否則會重複花腦啡肽模組。

### 定時執行

設定視窗建立的排程（星期、時間、是否叫醒電腦，設定檔的 `schedules`）寫進 Windows 工作排程器，時間到時打開視窗跑任務清單（#811）。

## 自行組裝

repo 的歷史裡有很多截圖，完整 clone 很大。開發用 partial clone，第一次只下載當前檔案，其餘的 blob 用到才取（歷史不會被改寫，見 ADR 0012）：

```powershell
git clone --filter=blob:none https://github.com/EnderWolf50/maalc.git
```

```powershell
uv run python tools/fetch_ocr.py
pnpm -C gui install; pnpm -C gui tauri build --no-bundle   # 可略過，略過就沒有 maalc-gui.exe
uv run python tools/install.py            # 開發用：child_exec 指向本機 Python
uv run python tools/install.py --release  # 發佈用：再加上內嵌 Python
```

推送 `v*` tag 時，[release workflow](.github/workflows/release.yml) 會在 windows-latest 上跑同樣的步驟，把 `install/` 壓成 zip 附到 draft release；tag 已經有 release（草稿或已公開）時照樣 build，但不再建 release，所以草稿公開後 tag 的 push 不會多一份草稿（`tools/release_draft.py`）。

## 授權

- 程式碼：[PolyForm Noncommercial 1.0.0](LICENSE)，只限非商業用途。
- 飾品與星之恩惠的中文名稱、效果文字取自[都市零漢化組](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)，採 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，用法與修改見 [NOTICE.md](NOTICE.md)。
- 遊戲素材 © Project Moon，不在本專案的授權範圍內；本專案是非官方的粉絲作品。其餘第三方內容各依其授權，見 [NOTICE.md](NOTICE.md)。
