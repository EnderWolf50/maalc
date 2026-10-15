# maalc

用 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 自動化 Limbus Company 鏡牢的工具。規格見 [docs/spec](docs/spec/README.md)。

## 下載與執行（Windows x64）

1. 從 [Releases](https://github.com/EnderWolf50/maalc/releases) 下載 `maalc-<版本>.zip`，解壓縮到任意資料夾，得到一個 `maalc/` 資料夾。
2. 執行 `maalc-gui.exe` 編輯設定（隊伍、方案、覆寫），設定存在 `config/settings.json`。
3. 執行 `mxu.exe`，連上模擬器後開始鏡牢任務。MXU 會用 `python/` 內附的 Python 啟動 Agent，不需要另外安裝 Python。

zip 不是安裝程式，也不會自動更新；換版時下載新 zip，把舊資料夾的 `config/` 複製過去，就能沿用 maalc 的設定。

## 自行組裝

```powershell
uv run python tools/fetch_ocr.py
pnpm -C gui install; pnpm -C gui tauri build --no-bundle   # 可略過，略過就沒有 maalc-gui.exe
uv run python tools/install.py            # 開發用：child_exec 指向本機 Python，自備 MXU
uv run python tools/install.py --release  # 發佈用：再加上內嵌 Python 與 MXU
```

推送 `v*` tag 時，[release workflow](.github/workflows/release.yml) 會在 windows-latest 上跑同樣的步驟，把 `install/` 壓成 zip 附到 draft release。
