---
status: accepted（修訂 ADR 0005）
---

# 資源包從 maalc 發佈到 maalc-resource，已安裝的 maalc 與 lc-helper 在執行時更新

[lc-helper](https://github.com/EnderWolf50/lc-helper)（戰鬥時疊在遊戲上的輔助視窗）讀 maalc 的事件表、飾品表、試煉表、圖示與模板，目前用 `tools/sync_maalc.py` 從旁邊的 maalc checkout 複製、轉換後 commit 進自己的 repo。每季換主題包與事件時，兩個工具各更新一次，已安裝的 bot 也要等新的 zip。使用者 2026-11-14 至 11-15 決定：兩個工具共用一份**資源包**，換季時只在 maalc 更新一次，已安裝的 maalc 與 lc-helper 不必換 zip 就拿得到。來源仍在 maalc，由 workflow 發佈到另一個公開 repo，做法和 MAA 的 [MaaResource](https://github.com/MaaAssistantArknights/MaaResource)（由 MAA 主 repo 的 `resource/` 同步）、AALC 的 AALCImageResources（[研究筆記](../research/aalc/01-architecture.md) §10.2）相同。

## 資源包

- 內容：`assets/resource/base/` 的 `data/`、`image/` 與 `pipeline/`，不含 OCR 模型所在的 `model/`。設定 GUI 自己放的 `gui/src/gift_effects.json`、`graces.json`、`grace_icons/`、`grace_card/` 搬進 `data/`。lc-helper 自己從客戶端匯出的罪孽圖示與飾品格底板也搬到 maalc 的 `data/`，匯出它們的工具搬到 maalc 的 `tools/`，NOTICE 跟著補上它們的來源（#755）。英文與中文都在包內，LLC 簡體轉繁體只在 maalc 做一次。lc-helper 只取它用到的檔。
- 版本號：發佈日期，例如 `2026.11.14`，同一天第二次是 `2026.11.14.2`。包內另記它取自哪一版遊戲客戶端。
- **格式版本**管資料：欄位結構改變才加一。欄位的意義改變時改欄位名，讓欄位結構的檢查抓到，格式版本跟著加一。
- **模板版本**管模板與 pipeline：要配新的 Agent 程式或 `assets/interface.json` 時才加一。CI 檢查：一個 PR 同時改了 `image/` 或 `pipeline/`，又改了 `agent/` 或 `assets/interface.json`，模板版本卻沒變，就失敗；commit 寫一行理由可以略過，和 `tools/review_lint.py` 的 `Removed-name-ok:` 一樣。
- 程式只套用自己認得的格式版本與模板版本，兩者各自判斷：格式版本比它新的資料、模板版本比它新的模板與 pipeline，留給帶著對應程式的下一個 zip。在那之前，舊 zip 的資料與模板各自停在最後一份認得的，所以模板版本加一不會擋住新的事件表。
- 包內附下載來源清單。以後加鏡像站，舊 zip 下次更新成功就會知道。

## 發佈

- 資料的來源與產生工具留在 maalc。改格式時，資料、讀它的程式與測試仍在同一個 PR（ADR 0005）。
- 合併到 main 後，workflow 把資源包連同 `LICENSE` 與 `NOTICE.md` 推到公開的 `maalc-resource`（GitHub），打上版本號的 tag。LLC 的中文採 CC BY-NC-SA 4.0，轉發時要保留署名、授權連結與修改說明（§3(a)(1)），NOTICE 已逐檔寫了。
- 發佈的 zip 內附一份資源包。

## 套用

- **maalc**：Agent 在任務開始（`TaskStart`）時檢查，最多等 10 秒。逾時或失敗就用上次下載的那份，沒有就用 zip 內附的，記一行 log，任務照常跑。下載完驗 sha256 才換檔。換檔後清掉資料檔的快取（`agent/settings.py` 的 `@cache`；MFAAvalonia 的 Agent 會跨任務存活），再用 `resource.clear()` 與 `post_bundle()` 重新載入，等載入完成才往下走，同一次任務就用新的模板與 pipeline。要重新載入，是因為 MXU 只在選資源時、MFAAvalonia 只在連線時載入一次：pipeline 在載入時就解析進記憶體，模板第一次比對時讀檔後快取（MaaFramework v5.14.3 `PipelineResMgr.cpp`、`TemplateResMgr.cpp`）。MaaFramework 對任務中途重新載入沒有保護（※ 原始碼裡沒看到），實作時先實機驗證；不行就改成任務結束時換檔並重新載入，下一次任務生效。
- **設定 GUI**：遊戲資料與圖改成執行時從 `resource/base/data/` 讀，像現在的 `load_theme_packs`，顯示 Agent 下載好的那份。換季後第一次任務跑完之前，GUI 顯示的是舊的。
- **lc-helper**：已公開，發佈 dist zip；zip 內附一份資源包，啟動時檢查。從 maalc 複製的 8 張模板改從資源包取，lc-helper 自己的模板留在 lc-helper。OCR 模型不在資源包裡，由 lc-helper 自己抓。數字用的 Barlow Condensed 字型不是遊戲素材，也留在 lc-helper。lc-helper 改讀資源包之前，LLC 中文與遊戲素材的授權寫在它自己的 `NOTICE.md`；改讀之後，這兩段改為指向資源包附的 `NOTICE.md`。開發時用 lock 檔記資源包的版本，由工具抓到 gitignore 的資料夾，測試與 build 都用它。lc-helper 的測試截圖仍是 maalc 的 `tests/screens`，CI 只抓指定 commit 的那個資料夾。

## Considered Options

- **來源與產生工具搬到獨立 repo**（StarRailRes 的做法）：改格式要拆成兩個 repo 的 PR 並依序合併，#387 那種一次改資料、GUI、Agent 與測試的 PR 會被拆開。
- **資料的 Release 放在 maalc 自己的 repo**（LLC 的做法）：MXU 以 maalc 的 Release 判斷程式有沒有新版，資料的 Release 可能被當成程式更新（※ 由 PI 文件「通用 UI 只從該 GitHub release 提供更新」推論）。
- **交給 MXU 或 MFAAvalonia 內建的更新，接 Mirror Chyan**：MXU 沒找到只更新資源的證據，玩家沒有 CDK 時退回 GitHub 下載整包；lc-helper 要另外接。
- **只有最新版程式才套用新圖**（AALC 的做法）：資源包從 main 發佈，模板配的 pipeline 或 Agent 可能還沒發 zip，連最新版的 zip 也配不上。
- **模板與資料共用一個格式版本**：2026-10-13 到 11-14 合併進 main、動到 `image/` 的 19 次裡，有 17 次同時改了 `agent/`。共用一個版本的話，舊 zip 很快就連新的事件表都收不到。
- **資源包只放兩個工具都用到的檔**：pipeline 不熱更新。同期 63 次動到 `pipeline/` 的合併有 10 次沒有改 `agent/`，例如 GoHome 等 CONNECTING 的上限改為 60 秒，都要等新 zip。
- **只換檔、重開 MXU 才生效**：重開之前，沒用過的模板會讀到新圖，pipeline 卻是舊的；MFAAvalonia 一直開著的人會一直用舊的。
- **測試截圖拆成獨立 repo，用 submodule 引用**：截圖不在玩家的 zip 裡；不改寫歷史，clone 也不會變小；每加一張截圖都要兩個 PR。截圖留在 maalc，以後要拆仍可以拆。

## Consequences

- 修訂 [ADR 0005](0005-game-data-files-separate-from-user-settings.md)：「資料檔沒有版本號」改為資源包帶格式版本與模板版本。改格式仍在同一個 PR，但要把版本加一。使用者設定不受影響。
- 熱更新會改變已安裝 bot 的行為（pipeline、選路權重、模板），不經過新 zip。改壞了，所有人會在下一次任務一起拿到。
- 發出去的 zip 會一直連 `maalc-resource`，並照兩個版本號判斷。改 repo 位址或版本規則，舊 zip 就收不到更新；下載來源清單只減輕位址的部分。
- 設定 GUI 不再在 build 時打包遊戲資料與圖。
- lc-helper 的 `tools/sync_maalc.py` 不再使用。lc-helper 改讀 maalc 的資料格式，事件、飾品、試煉合併好的英中文字改由 maalc 的產生工具輸出。
- 先只發佈到 GitHub。中國大陸連 GitHub 可能不穩，失敗時照常用手上的那份。
- maalc 的歷史不改寫，README 的開發段改為建議 `git clone --filter=blob:none`。
