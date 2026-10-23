# 第三方聲明

本專案的程式碼採 [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)（`LICENSE`）。取自都市零漢化組的中文名稱與效果文字（`gift_search.json`、`gift_recipes.json`、`gui/src/graces.json`）採 CC BY-NC-SA 4.0，見下方「都市零漢化組」。以下第三方內容各依其授權。

## MaaPracticeBoilerplate

專案骨架（`assets/interface.json` 的結構、`agent/main.py` 的 AgentServer 進入點、`maatools.config.mts`、`tools/` 的 OCR 模型與安裝腳本）參考 [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate) 改寫，依其 MIT 授權保留以下聲明：

```
MIT License

Copyright (c) 2024 MaaXYZ

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## OCR 模型 ppocr_v6/small

`assets/resource/base/model/ocr/` 的模型由 `tools/fetch_ocr.py` 從 [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets/tree/main/OCR/ppocr_v6/small) 下載，不放進 repo。模型出自 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 的 PP-OCRv6，採 [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) 授權。

## Limbus Company 遊戲素材

`assets/resource/base/image/` 的模板與 `tests/screens/` 的測試截圖取自 Limbus Company 的遊戲畫面，著作權屬於 © Project Moon，不在本專案的授權範圍內。測試截圖中的 UID 與帳號已遮蔽。`assets/resource/base/image/GiftSearch/` 的 320 個飾品圖示與 5 個殘影圖示（`9991.png`–`9995.png`）取自遊戲客戶端 1.117.0 的資源包（`Sprite/EgoGiftIcon`），縮成畫面上的大小（0.21 倍）、透明處填綠色作為比對遮罩，同樣屬於 © Project Moon。`assets/resource/base/data/gift_search.json` 的飾品清單、id、等級與英文名稱，以及 `assets/resource/base/data/theme_packs.yaml` 的主題包清單、id、樓層與英文名稱，取自同一版客戶端的靜態資料。`assets/resource/base/data/event_table.json` 的事件表取自同一版（1.117.0）客戶端的靜態資料與英文在地化（鏡牢事件的 id、故事結尾、選項與提示文字、選項效果與飾品體系），由 `tools/event_table.py` 只摘錄這些欄位，同樣屬於 © Project Moon。`assets/resource/base/image/Shop/` 的 10 個體系徽章（`Badge<體系>.png`）裁自 1.117.0 實機的商店、合成頁截圖（2026-10-13 至 10-18），縮成飾品圖示模板的比例，徽章以外填綠色作為比對遮罩；`tests/shop/` 是同一批截圖的格子區域，同樣屬於 © Project Moon。`assets/resource/base/data/theme_pack_covers/` 的主題包卡片縮圖（`<主題包 id>.webp`，寬 180 像素）由 `tools/theme_pack_covers.py` 用遊戲客戶端 1.117.0 的素材合成：資源包的封面與 boss 圖（`card_pack`、`boss` 精靈圖）、玩家資料的卡片外框、logo、警告與攻擊類型圖示，以及主題包的名稱（英文在地化）與顏色（靜態資料），同樣屬於 © Project Moon。縮圖上的標題字型是 Mikodacs（© 2012–2016 gluk，[SIL Open Font License 1.1](https://openfontlicense.org/)），「Long Battle」標籤的字型是 Pretendard（© 2021 Kil Hyung-jin，同為 OFL 1.1），版權聲明都寫在字型檔內的 name table；兩個字型取自同一版客戶端，字型檔本身不放進 repo。縮圖另含資源包的「Long Battle」疊圖（`Sprite/UI/ThemePack/Baton.png`）與玩家資料的屬性圖示（`Icon_evil_2_8`–`14`），同屬 © Project Moon。

本專案是非官方的粉絲作品，與 Project Moon 無關。以上素材僅供自動化辨識之用；著作權人如要求移除，會立即從 repo 移除。

## 預設主題包分數

`assets/resource/base/data/theme_packs.yaml` 預設方案（`default_plan`）的每包分數取自 [AhabAssistantLimbusCompany](https://github.com/KIYI671/AhabAssistantLimbusCompany)（AALC）的預設權重表 [assets/config/theme_pack_list.example.yaml](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/45d9a5809456d008fc2c16f28d52882bf388cd1d/assets/config/theme_pack_list.example.yaml)（commit `45d9a58`，2026-08-05；2026-10-22 取用時 `main` 為 `e1d1749`，這個檔案沒有更動）。AALC 採 [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) 授權。本專案只取每個主題包的分數（數字），依 AALC 自己的片段比對規則對到本專案的主題包完整名稱，不複製它的檔案或程式碼（[ADR 0001](docs/adr/0001-mit-and-no-agpl-derived-assets.md)：權重這類參數可以參考）。

## 觀測飾品與合成飾品的資料

`assets/resource/base/data/gift_recipes.json` 與 `assets/resource/base/data/gift_search.json` 的飾品清單、id、等級、體系與英文名稱、配方、主題包專屬標記（`isSpecific`、`specificEgoGiftPool`）取自遊戲客戶端 1.117.0 的靜態資料與英文在地化（© Project Moon），只摘錄這些欄位；`assets/resource/base/image/GiftRecipe/` 的 72 個圖示取自同一版資源包的 `Sprite/EgoGiftIcon`，縮 0.21 倍、透明處填綠色，同屬 © Project Moon。`assets/resource/base/data/gift_icons/` 的 397 個圖示（56 px WebP，保留透明）取自同一版資源包的 `Sprite/EgoGiftIcon`，同屬 © Project Moon。`assets/resource/base/data/keyword_icons/` 的 10 個體系圖示（64 px WebP，保留透明）取自遊戲客戶端的體系圖示，同屬 © Project Moon。

## 都市零漢化組（LLC）的中文名稱與效果文字

飾品與星之恩惠的繁體中文名稱取自 [都市零漢化組（Localize Limbus Company，LLC）](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany) 的簡體中文在地化，版權屬於 Copyright (c) 2024 to now Localize Limbus Company 與其貢獻者，採 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)（非商用、姓名標示、相同方式共享）授權。本專案使用 release [2026101602](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/tag/2026101602)（2026-10-16）的內容：

- `assets/resource/base/data/gift_search.json` 與 `assets/resource/base/data/gift_recipes.json` 的飾品中文名稱：`LLC_zh-CN/EGOgift_*.json` 的 `name`，依飾品 id 對應。
- `gui/src/graces.json` 的星之恩惠名稱：`LLC_zh-CN/MirrorDungeonUI_5.json` 的 `mirror_dungeon_5_buffs_title_<id>`。效果文字：`LLC_zh-CN/DungeonStartBuffs_MD7.json` 的句型，填入遊戲客戶端 1.117.0 靜態資料（`mirrordungeon-start-buffs-08`）的效果數值與 `LLC_zh-CN/Bufs*.json`、`BattleKeywords*.json` 的狀態名稱。英文名稱取自遊戲畫面。

修改：以 OpenCC `s2twp` 由簡體轉成繁體，再改五個用詞（「指標」改回「指針」、「重新整理」改回「刷新」、「映象」改為「鏡像」、「透過階層」改為「通過階層」、「松肉」改為「鬆肉」）；星之恩惠的效果文字去掉顏色標籤並填入數值。轉換由 `tools/llc_text.py` 完成，所用 release 記在各資料檔的 `zh_release`。這三個資料檔的中文名稱與效果文字同樣以 CC BY-NC-SA 4.0 授權；檔內的 id、英文名稱與數值仍是 © Project Moon。

## 發佈 zip 內附的第三方程式

`tools/install.py --release` 組出的發佈 zip 另外附上以下程式，都是原樣下載、不經修改：

- [MXU](https://github.com/MistEO/MXU) v2.7.1 的 `mxu.exe`，採 [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) 授權，授權全文在 zip 內的 `LICENSE-MXU`。對應原始碼：<https://github.com/MistEO/MXU/tree/v2.7.1>。
- [Python](https://www.python.org/) 3.12.10 embeddable package（`python/`），採 PSF License，授權全文在 `python/LICENSE.txt`；`python/Lib/site-packages/` 內的套件各依其授權。
- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)（`maafw/` 與 `maafw` 套件），採 LGPL-3.0 授權。例外：`maafw/MaaFramework.dll` 是修改過的版本（v5.14.3 加上批次 OCR 細條修正），對應原始碼：<https://github.com/EnderWolf50/MaaFramework/tree/v5.14.3-maalc.2>。
