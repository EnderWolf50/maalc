# maalc

用 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 自動化 Limbus Company 鏡牢的工具。規格見 [docs/spec](docs/spec/README.md)。

## 下載與執行（Windows x64）

1. 從 [Releases](https://github.com/EnderWolf50/maalc/releases) 下載 `maalc-<版本>.zip`，解壓縮到任意資料夾，得到一個 `maalc/` 資料夾。
2. 執行 `maalc-gui.exe`。視窗開在「執行」分頁；隊伍、方案與覆寫在其他分頁，設定都存在 `config/settings.json`。
3. 選模擬器：在「執行」分頁上方按「偵測模擬器」，從下拉選單選要用的那一個（MuMu 排在前面）。選了就填入 adb 位址、MuMu 實例編號與 MuMuManager 路徑，儲存後生效；也可以自己填。位址留空時，用偵測到的第一個模擬器。
4. 勾選要跑的任務，拖曳或用 ↑↓ 排順序；點一個任務，右邊設它的選項。
5. 按「開始」：視窗先儲存設定，再依序跑勾選的任務。位址上的 MuMu 沒開，而且實例編號與 MuMuManager 路徑都有填時，maalc 先用 MuMuManager 開好它再連線（最多等 120 秒）。所以先開著 MuMu 偵測一次，之後 MuMu 沒開也能直接按「開始」。

執行時，分頁下方列出這次的每個任務與狀態（等待、執行中、成功、失敗、已停止、已取消；bot 自己停下時，沒輪到的任務標「已取消」並寫原因），旁邊是即時記錄。視窗只留最近 2000 行，每次執行的完整記錄在 `logs/runner/`（保留最近 30 次）。

- **停止**：按「停止」，bot 停在手上的動作，最多約一分鐘；停不下來時，maalc 結束執行器和它開的程式（bot、adb）。還沒輪到的任務標「已取消」。
- **執行中**：任務清單、任務選項、全域選項和模擬器不能改，停止或跑完後再改；其他分頁照常能改、能存。
- **關視窗**：執行中關視窗會縮到系統匣，任務繼續跑。點系統匣圖示叫回視窗，它的選單也能停止。沒在執行時，關視窗就結束。
- **每個資料夾只開一個視窗**：再執行一次同一個資料夾的 `maalc-gui.exe`，會叫出已經開著的視窗；另一個 maalc 資料夾開它自己的視窗。
- **執行器意外結束**：視窗留著，寫明結束碼與最後幾行記錄，不會自己重跑。

視窗用 `python/` 內附的 Python 跑執行器（`runner/`）與 bot，不需要另外安裝 Python。

這一版起由設定視窗自己執行任務，zip 不再附 MXU，也不再支援 MFAAvalonia（[ADR 0015](docs/adr/0015-settings-window-runs-the-tasks.md)）。v1.0.0 仍用 zip 附的 MXU 執行，說明見 v1.0.0 的 README。

### 自動更新

視窗打開時查 GitHub 上最新的正式版，每天最多查一次。比目前新時，標頭出現「更新到 v<版本>」；查不到（沒有網路、GitHub 沒回應）時什麼都不顯示。

- 按「更新到 v<版本>」：zip 下載到 `cache/update/`，標頭顯示進度。下載完用 GitHub 給的 sha256 比對，不符就刪掉、不套用，分頁上方寫明原因；按「更新失敗，重試」重新下載。
- 比對通過就解壓、套用：有未儲存的變更時先存檔，視窗關閉，新版換掉程式檔案後自己開啟。執行中不套用：標頭改寫「執行結束後套用 v<版本>」，這次執行結束後再按。
- 套用只換掉 zip 裡有的項目（`maalc-gui.exe`、`python/`、`agent/`、`runner/`、`maafw/`、`resource/` 等），`config/`、`logs/`、`state/`、`cache/`、`debug/` 不動。換下來的舊版放在 `cache/update/old/`，新版下次打開時刪掉。
- 任何一步失敗，就把舊版搬回來、開啟舊版，分頁上方寫明原因。
- 例外：套用中途被打斷（例如斷電），或失敗後沒能全部搬回時，`cache/update/old/` 是那些舊檔唯一的一份，所以不會刪掉。要自己把它們搬回 maalc 的資料夾，再刪掉 `cache/update/old/`。在那之前，視窗每次打開都在分頁上方提醒，不能再套用更新（免得蓋掉那份唯一的舊檔），定時執行也會略過。
- 遊戲資料的資源包照舊在任務開始時自己更新（[ADR 0012](docs/adr/0012-resource-package-hot-update.md)），和程式更新互不影響。

從 v1.0.0 升級：把新 zip 解壓到新資料夾，再把舊資料夾的 `config/` 複製過去。設定視窗第一次打開時把設定檔升到版本 23，舊檔另存成 `config/settings.v22.json`。同時從 `config/mxu-maalc.json`（MXU 上次用的實例）讀回任務選項、任務清單的勾選與順序、模擬器位址；沒有 MXU 的檔就從 `config/settings.v20.json` 讀回任務選項，再沒有就用預設值。讀到什麼、哪些沒讀到要重填，在分頁上方列一次。MXU 的檔只讀不寫。webhook 在 MXU 裡加密存放，一定要重填。用 MFAAvalonia 的人要自己重設任務選項。

### 鏡牢與全域的任務選項

鏡牢怎麼跑（難度、目標層數、局數上限、每週獎勵、星光買不起時、全滅重打、這次從哪一支隊伍開始）存在設定檔的 `run`。失敗通知 webhook、自動同意使用者條款、自動接受下載與更新、關畫面前存截圖是**全域選項**，每個任務都會用到，也在 `run`。「執行」分頁編輯它們：鏡牢的選項在任務清單點鏡牢，全域選項在分頁的「全域選項」一區（#814）。

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

經驗本、紐本與狂氣換腦啡肽怎麼跑，存在設定檔的 `luxcavation.exp`、`luxcavation.thread` 與 `charge_enkephalin`（[spec 04 第 12 節](docs/spec/04-settings.md#12-日常的任務選項luxcavationcharge_enkephalin)），在「執行」分頁的任務清單點那個任務編輯（#814）。

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

在「執行」分頁的「定時執行」新增排程，選星期、時間與是否叫醒電腦（設定檔的 `schedules`），存檔就寫進 Windows 工作排程器。時間到時打開視窗跑勾選的任務，跑完自動關閉；視窗開著就在那個視窗跑，已經在跑、或程式更新正在套用（或上次沒做完）就略過。執行器意外結束時，排程開的視窗留著，寫明結束碼。電腦在那個時間沒開，登入後補跑一次；只在你登入 Windows 時執行。叫醒電腦還要 Windows 的電源選項允許喚醒計時器。每次的結果寫在 `logs\schedule.log`。搬動 maalc 資料夾後打開一次視窗，排程就改到新位置（[spec 04 第 14 節](docs/spec/04-settings.md#14-任務清單模擬器與排程tasksemulatorschedules)，#816）。

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
