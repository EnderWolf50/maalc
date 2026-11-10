# maalc

用 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 自動化 Limbus Company 鏡牢的工具。規格見 [docs/spec](docs/spec/README.md)。

## 下載與執行（Windows x64）

1. 從 [Releases](https://github.com/EnderWolf50/maalc/releases) 下載 `maalc-<版本>.zip`，解壓縮到任意資料夾，得到一個 `maalc/` 資料夾。
2. 執行 `maalc-gui.exe` 編輯設定（隊伍、方案、覆寫），設定存在 `config/settings.json`。
3. 執行 `mxu.exe`，連上模擬器後開始鏡牢任務。MXU 會用 `python/` 內附的 Python 啟動 Agent，不需要另外安裝 Python。

zip 不是安裝程式，也不會自動更新；換版時下載新 zip，把舊資料夾的 `config/` 複製過去，就能沿用 maalc 的設定。

### 用 MFAAvalonia 執行

zip 只附 MXU。要用 MFAAvalonia，下載它的 win-x64 zip 解壓到 `maalc/` 裡，再把 `maafw\MaaFramework.dll` 複製到 `runtimes\win-x64\native\`，蓋掉同名的檔案。MFAAvalonia 本體或它附的 MaaFramework 更新時會換回自己的 `runtimes\`，更新後要再複製一次。

MFAAvalonia 只從自己的 `runtimes\` 載入 MaaFramework，不讀 `maafw\`。不換也能跑，但會少了 `maafw\MaaFramework.dll` 的兩個修正，跑久了記憶體會漲：

- 一個任務會留下每個節點的詳情。一整局鏡牢是一個任務，記憶體約每小時漲 0.5 GB（#176）。
- 批次 OCR 會把被 roi 切掉一半以上的字框切成 1 px 細條重讀，曾讓記憶體從 4 GB 漲到 12 GB（#157）。現在只有等遊戲開機的畫面用到批次 OCR。

這份 `MaaFramework.dll` 是 MaaFramework 5.14.3 加上這兩個修正，MFAAvalonia v2.16.4 附的也是 5.14.3。換之前先看 MFAAvalonia「設定」→「更新設定」的「框架版本」，不是 `v5.14.3` 就先不要換：不同版本的 MaaFramework DLL 混用沒有試過。換完後這裡仍然顯示 `v5.14.3`，修過的版本號沒有變。

### 辨識失敗時的截圖（`save_on_error`）

辨識沒對上時，MaaFramework 會把當下的畫面存進 `debug/on_error/`，回報問題時請附上。這是 client 的選項，maalc 設不到。兩個 client 預設都開著，值存在 `config/maa_option.json` 的 `save_on_error`，同一個資料夾裡的兩個 client 讀同一份（用發佈 zip 在 MXU v2.7.1 與 MFAAvalonia v2.16.4 實機確認）：

- MXU：第一次啟動時寫入這個檔案，值是 `true`；改這個檔案，下次啟動 MXU 就會照新的值。
- MFAAvalonia：「設定」→「執行設定」→「啟用錯誤時儲存截圖 (用於除錯)」（依 MFAAvalonia v2.16.4 原始碼，介面上沒有實機看過）。

## 日常任務

鏡牢以外的日常各是一個獨立任務，在 MXU 或 MFAAvalonia 的任務清單裡勾選、排序：

| 任務 | 做什麼 |
|---|---|
| 換腦啡肽模組（`AssembleModules`） | 把腦啡肽換成腦啡肽模組，沒有參數 |
| 經驗本（`ExpLuxcavation`） | 打 EXP 分頁最右邊已開放的最難關；預設用連戰（Consecutive Battle）一場打完，可在 GUI 的「日常」分頁關掉 |
| 紐本（`ThreadLuxcavation`） | 打 Thread 分頁今天開放的異想體，選最難的一級；連戰同經驗本 |
| 領通行證任務（`ClaimPassMissions`） | 領 Limbus Pass 的 Daily、Weekly、Seasonal 任務，沒有參數 |
| 領信（`ClaimMail`） | 信箱 Claim All，沒有參數 |
| 狂氣換腦啡肽（`ChargeEnkephalin`） | 用 Lunacy 換腦啡肽 |
| 鏡牢（`MirrorDungeon`） | 見 `maalc-gui.exe` 的其他分頁 |

每個日常都從主畫面開始、回到主畫面結束，所以任一個都可以單獨跑，順序也可以自己排。做完或「該跳過」（腦啡肽模組不夠、沒有可領的）都算成功，清單繼續下一個；卡住或出錯才算失敗。

### 建議順序

換腦啡肽模組 → 經驗本 → 紐本 → 換腦啡肽模組 → 通行證任務 → 信箱 → 鏡牢

- 第一次換腦啡肽模組：先把腦啡肽變成腦啡肽模組，後面的副本才有腦啡肽模組可花。
- 經驗本、紐本：每場花腦啡肽模組（經驗本 3、紐本 2），先於鏡牢，鏡牢開新局前會檢查腦啡肽模組至少 5 個（領獎要花 5 個），不夠就不開局。
- 第二次換腦啡肽模組：副本打完腦啡肽又回了一些，再換一次給鏡牢用。
- 通行證任務：副本可能剛完成通行證任務，打完再領才領得到。
- 信箱：放在鏡牢前，領到的獎勵先入帳。
- 鏡牢：最花時間，放最後。

### 「日常」分頁的參數

在 `maalc-gui.exe` 的「日常」分頁設定，存在 `config/settings.json`。要跑哪些、什麼順序不在這裡，由 client 的清單決定。

- 經驗本、紐本（欄位相同）：
  - 模式（**預設每日模式**）：
    - 每日模式：打今天還沒打的，今天已打贏的（手動打的也算）不再打。經驗本看通行證 Daily 分頁的 `Clear EXP Luxcavation`，還沒完成打 1 場、完成就不打；紐本看 Daily Bonuses，剩 n 次就打 n 場；讀不到就不打。不用下面的場數。
    - 自訂次數：這次打贏下面的場數，不看今天打過幾場（經驗本不開通行證頁）。
  - 這次要打贏的場數（經驗本預設 1、紐本預設 3）：只有自訂次數模式用。打贏才算一場，戰敗不算。
  - 隊伍：選一支 GUI 裡的隊伍，用它的遊戲隊伍編號、出戰順序與防禦回合數，不必啟用。**預設沒選，沒選時任務一開始就停止**。
  - 戰敗重打次數（預設 0）：用完還輸就結束這個任務，清單繼續。
  - 腦啡肽模組少於「最難關每場消耗 × 這次要打的場數」，就跳過整個任務。
- 狂氣換腦啡肽：今天換到第幾次（0–10，**預設 0**，0 時什麼都不做）。**只有你設成大於 0，才會花 Lunacy**（先扣免費的，再扣付費的）；這是當天的目標：Use Lunacy 分頁的 Daily Count 已經到了就不換（手動換的也算），讀不到也不換。價格依當天已換次數是 26、52、78…最多 260，每次確認前核對價格是表上的下一格，不符就停；遊戲一天最多 10 次，到了就結束。
- 換腦啡肽模組、領通行證任務、領信、鏡牢的腦啡肽模組門檻：沒有參數。

### 兩個模擬器共用一個帳號

兩個實例登入同一個帳號時，**只在其中一個實例的清單勾選日常**，另一個只放鏡牢（或不放），否則兩邊會重複花腦啡肽模組。

### 在 client 裡排日常

兩個 client 都可以讓你勾選、拖曳排序、排程和設定結束後動作（以下依兩個 client 的原始碼確認，MXU `5e923e8`、MFAAvalonia `098fe84`，沒有實機驗證）：

| | MXU | MFAAvalonia |
|---|---|---|
| 任務清單 | 每個任務前有勾選框；拖曳排序（右鍵另有上移、下移、置頂、置底）；工具列「新增任務」加入任務，同一任務可加多份 | 任務項有勾選，清單上方有全選／全不選；拖曳排序；右鍵複製、貼上 |
| 排程 | 工具列右側「定時」→「定時執行」面板：重複日期（週日到週六）加開始時間，每個實例各自的策略；MXU 必須開著 | 「設定」→「定時執行」：每天／每週／每月計時器，可選開始或停止任務；全域共用，要指定實例得開「自定義配置選擇」；程式必須開著 |
| 結束後動作 | 沒有全域設定；在清單最後加「特殊任務」：電腦操作（關機、重新啟動、關閉螢幕、睡眠、休眠）、結束程序等 | 「設定」→「啟動設定」→「結束後操作」：無、關閉本程式、關閉模擬器、關機、重啟電腦等；任務失敗結束時也會執行，手動停止不會 |
| 任務失敗後 | 見下方說明 | 「設定」→「執行設定」→「任務執行失敗後是否繼續執行其他任務」，預設開；關掉的話，任一任務失敗就中斷整串清單 |

MXU 失敗後是否繼續下一個：unverified，沒有確認。

## 自行組裝

```powershell
uv run python tools/fetch_ocr.py
pnpm -C gui install; pnpm -C gui tauri build --no-bundle   # 可略過，略過就沒有 maalc-gui.exe
uv run python tools/install.py            # 開發用：child_exec 指向本機 Python，自備 MXU
uv run python tools/install.py --release  # 發佈用：再加上內嵌 Python 與 MXU
```

推送 `v*` tag 時，[release workflow](.github/workflows/release.yml) 會在 windows-latest 上跑同樣的步驟，把 `install/` 壓成 zip 附到 draft release；tag 已經有 release（草稿或已公開）時什麼都不建，所以草稿公開後 tag 的 push 不會多一份草稿（`tools/release_draft.py`）。

## 授權

- 程式碼：[PolyForm Noncommercial 1.0.0](LICENSE)，只限非商業用途。
- 飾品與星之恩惠的中文名稱、效果文字取自[都市零漢化組](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)，採 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，用法與修改見 [NOTICE.md](NOTICE.md)。
- 遊戲素材 © Project Moon，不在本專案的授權範圍內；本專案是非官方的粉絲作品。其餘第三方內容各依其授權，見 [NOTICE.md](NOTICE.md)。
