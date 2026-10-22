# 非商用授權，飾品與星之恩惠的中文名稱用都市零漢化組的翻譯

飾品與星之恩惠的中文名稱原本取自灰機 wiki：它缺 8 個新飾品，頁面又有 Cloudflare 擋，工具要人用瀏覽器存檔。[都市零漢化組（LLC）](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)的 release 涵蓋全部飾品，可直接從 GitHub 下載；星之恩惠的名稱與效果文字也在其中。

LLC 採 CC BY-NC-SA 4.0，非商用且相同方式共享，與 MIT 不相容，所以：

- 程式碼改用 [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)（`LICENSE`）。
- 取自 LLC 的資料檔（`gift_search.json`、`gift_recipes.json`、`gui/src/graces.json`）標 CC BY-NC-SA 4.0，NOTICE.md 寫明作者、release、授權連結與修改（OpenCC s2twp 簡轉繁，加四個用詞修正）。
- 中文名稱由 `tools/llc_text.py` 從 LLC 的 release 產生，檔頭記下所用 release；不再使用灰機 wiki。
- 不沿用 AGPL 專案程式碼、圖片與模型的規則（[ADR 0001](0001-mit-and-no-agpl-derived-assets.md)）不變：授權改為非商用並沒有讓複製 AGPL 程式碼變得可行。

非商用授權不是 OSI 認可的開源授權；選它是接受 LLC 的條件。第三方元件的相容性查證寫在這次變更的 PR 內文。
