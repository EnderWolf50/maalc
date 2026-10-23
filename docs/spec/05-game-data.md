# 05 遊戲資料檔

本章定義放在 resource 裡、隨季節更新的遊戲資料檔：主題包清單與預設主題包方案、事件覆寫表、試煉風險表、選路權重，以及 Cost 對照表與商店數字。每份資料檔說明用途、欄位、範例、誰維護、使用者怎麼覆寫，最後是每季更新的檢查清單。使用者自己的設定（隊伍、方案、執行選項、覆寫）不在這裡，見 [04-settings.md](04-settings.md)。

## 1. 總則

- 遊戲資料放在 resource 裡的資料檔，和使用者的設定檔分開。換季時只更新資料檔，GUI 與設定檔都不用改。理由見 [ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)。（#11）
- 資料檔由開發者每季更新，使用者不直接修改。（#11、#19，2026-10-14 定案，[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)）
- 資料檔用 YAML，放在 `resource/base/data/`。檔名在實作時決定。本章的範例用表格表示欄位與內容。（#19）
- 使用者要調整的部分在設定 GUI 裡編輯，存在設定檔 `<root>/config/settings.json`，由 Agent 讀取時疊加在資料檔上：自己的主題包方案、事件覆寫、試煉風險覆寫。開發者更新資料檔時不動設定檔。不另設覆寫檔。（#11、#19，2026-10-14 定案，[ADR 0006](../adr/0006-settings-gui-writes-one-settings-file.md)）
- OCR 讀到的文字（主題包標題、事件問題、試煉名稱）用 `expected` 或模糊比對對照資料檔。（#13）
- 模糊比對：相似度 ≥ 0.9，而且必須比第二名高 0.04 以上才算比對到。數值在實作時再調整。（#19）主題包標題改用第 2 節的子字串比對（#89）。
- v1 不需要飾品清單資料檔：飾品挑選只依體系，Sale & Fusion-only 從畫面讀。（#10、#19）

| 資料檔 | 用途 | 維護者 | 開局內容 | 來源 |
|---|---|---|---|---|
| 主題包清單與預設主題包方案 | 主題包頁挑選；GUI 列出這一季的主題包 | 開發者每季提供；使用者不能改，可以在設定檔另建方案 | 預設方案有內容 | #11、#19 |
| 事件覆寫表 | 事件頁的例外選項 | 開發者依記錄補充；使用者在設定檔另加覆寫 | 空 | #11、#19 |
| 試煉風險表 | Boss 後的選擇評分 | 開發者每季更新；使用者在設定檔另加覆寫 | 有預設值 | #17、#19 |
| 選路權重 | 地圖頁選下一個節點 | 開發者 | 有預設值 | #12 |
| Cost 對照表與商店數字 | 節點 Cost 參考值（不用於辨識）、商店的刷新與治療判斷 | 開發者 | 有預設值 | #10、#12、#19 |
| 事件表 `event_table.json` | 事件頁依選項的實際效果排序 | 開發者每季從拆包的客戶端資料重新產生（第 7 節） | 1.117.0 的 195 個事件 | #93 |
| 觀測飾品表 `gift_search.json` 與圖示 `image/GiftSearch/<id>.png` | E.G.O Gift Search 頁找飾品（位置預測、圖示比對）；GUI 的飾品清單 | 開發者每季依遊戲客戶端的觀測表重新產生（產生方式寫在檔頭 `note` 與 [04-settings.md](04-settings.md) 第 9 節） | 這一季的 320 個，另有 5 個殘影圖示（9991–9995，#161） | #54 |
| 合成飾品表 `gift_recipes.json` 與圖示 `image/GiftRecipe/<id>.png` | 飾品清單把合成品標成想要時，查它的配方與材料（固定配方、月之記憶的 N 選 K） | 開發者每季跑 `tools/gift_recipes.py`（中文名取自 LLC release）（用法寫在工具檔頭與 `note`，要 `bench` 號碼牌） | 這一季 60 個合成品（59 個固定配方共 67 條，月之記憶 1 條 N 選 K），其中 39 條固定配方（`isSpecific`）用到主題包專屬飾品，該合成品帶 `specific: true` 與 `packs`（那些主題包的 id，取自各包 `specificEgoGiftPool`）；另有 12 個 `gift_search.json` 沒有的材料，72 個圖示，中文名全齊 | #277、#286 |
| 預設飾品清單 `gift_lists.yaml` 與 GUI 圖示 `gift_icons/<id>.webp` | 飾品清單的「預設」；GUI 顯示 397 個飾品的圖示（第 9 節） | 開發者每季確認 id 還在、重跑 `tools/gift_icons.py` | 預設清單 23 個想要、90 個保留；397 個圖示 | #291、#293 |

## 2. 主題包方案

**用途**：在主題包頁依每個主題包的分數（權重）挑選主題包。每隊選「預設」方案或使用者自己的方案。（#11、#19，2026-10-14 定案；#240 改成分數）

**檔案**：`resource/base/data/theme_packs.yaml`，`packs` 是主題包清單（名稱 → 樓層），`event_packs` 是活動包，`default_plan` 是預設方案。（#25、#240）

**內容**：

- 主題包清單：這一季所有主題包的英文名稱，用來和 OCR 讀到的卡片標題列比對；GUI 也用它列出可以標記的主題包。困難限定的主題包列在同一份清單裡（#11、#19）。每個名稱對到資料標的樓層，例如 `N12 H1` 是普通第 1–2 層、困難第 1 層；設定 GUI 用它篩選要顯示的主題包，分數本身不分難度與樓層。（#240）
- 清單從遊戲客戶端的靜態資料產生（`mirrordungeon-theme-floor`，1.117.0 有 121 個）：收錄有普通或困難樓層的主題包；只出現在 Extreme 的、沒有樓層的、以及同名的復刻版（BokGak）不收。名稱照資料，實機看到的標題不同時以實機為準（目前只有 `Walpurgis Night: Hatred and Despair`，資料寫 `Hatred and Despair`）。檔頭寫來源與版本，每個名稱後的註解是 id 與樓層（N 普通、H 困難）。（#89，2026-10-18）
- 活動包：資料裡 `unlockCode` 為 9xxx 的 22 個主題包是活動劇情通關後永久加入的，其中 15 個出現在一般鏡牢，另列在 `event_packs`，用英文名稱辨認。只在第 5 層出現的是 `Spring Cultivation`、`Twining Threads`、`Mnestic Experience`。（#89，2026-10-18 定案）
  - 怎麼認出活動包（#240 調查，2026-10-22）：9xxx 是 `unlockcode-subchapter` 裡的 `SUBCHAPTER_CLEAR`，也就是某段活動劇情（間章、Walpurgis Night 各期）通關後解鎖。Walpurgis Night 的每一期各有自己的解鎖碼（`walpu2`…`walpu8`）和自己的主題包名稱，所以清單逐包列名稱，不靠 `Walpurgis Night` 這個字。靜態資料（`mirrordungeon-theme-floor`、`mirror-dungeon-common-data`、`main-event`、`event`）沒有限時或「目前活動」欄位，資料只分得出「活動劇情包」，分不出「這一期正在開的活動包」。實機卡片也沒有專屬外框或標記（`captures/177_f3_theme_pack.png`，登錄在 [captures-2026-10-13.md](captures-2026-10-13.md)，截圖留在本機：`Walpurgis Night: Hatred and Despair` 的卡和一般主題包同一種卡框）。使用者說明（2026-10-22）：活動進行期間，活動包固定出現在第 5 層最左邊（AALC 也看這個位置）；已結束的活動包和一般主題包一樣，這張截圖的第 3 層就是這種情形。所以活動卡包設定只看第 5 層最左邊那張，並且只在它是活動劇情包或資料檔沒收錄的包時才套用（[03](03-decisions.md#6-主題包) 第 6 節）。
- 預設主題包方案：和使用者方案同樣的欄位（[04-settings.md](04-settings.md#8-主題包方案theme_pack_plans) 第 8 節）：每包的分數、刷新門檻、沒列出的包的分數、活動卡包的處理方式。開發者每季提供，使用者不能修改。（#11、#19、#240）
  - 1.117.0 的內容（#240，使用者 2026-10-22 決定）：分數沿用 AALC 的預設權重（`assets/config/theme_pack_list.example.yaml`，最後修改的 commit `45d9a58`，AGPL-3.0，見 NOTICE.md）；門檻 0、沒列出的包 0（不用 AALC 的 unknown −5）、活動包照分數。只取每包一個數字，屬於 [ADR 0001](../adr/0001-mit-and-no-agpl-derived-assets.md) 說的參數；檔案與程式不複製。#89 原本「不沿用其他專案的權重表」的規則由這個決定取代。
  - AALC 的鍵是標題的片段（`forgot`、`gambl`、`chick`），比對時找 OCR 文字裡第一個出現的片段（不分大小寫，困難模式是普通表再疊上困難表）。推測原因是卡面標題用了特殊字體，整串名稱不容易 OCR 完整（unverified，AALC 沒有寫原因）。對應的作法是照 AALC 的比對規則，把每個片段套到這一季 94 個完整名稱，資料檔每個分數後面的註解寫出它來自哪個片段。普通與困難兩份表沒有對同一包給不同分數。同一包的備用片段（`nag`、`dev`、`deg`、`shed`、`ssed`、`tread`、`mne`、`b·e`、`xte`、`unch`）分數相同；`compassion`（`Pilgrimage of Compassion`，1.117.0 沒有普通或困難樓層）不收；`Storefront Campout`、`An Anarchy of Colors`、`Creed of Preservation`、`Readvent of Gluttony` 沒有對應的片段，用沒列出的包的分數 0。
- 卡片縮圖（#241）：`resource/base/data/theme_pack_covers/<主題包 id>.webp`（寬 180，94 張共 1.59 MB）與 `index.json`（主題包名稱 → 檔名），給設定 GUI 的圖片模式用，清單裡 94 個包都有，沒有缺的。縮圖是遊戲內卡片的樣子（正面；不含頂端吊夾、放大鏡紅章，也不傾斜：實機的卡片會左右搖擺），由 `tools/theme_pack_covers.py`（排版在 `tools/theme_pack_card.py`）照卡片 prefab `MirrorDungeonThemeCardUI`（APK 玩家資料 `sharedassets7`）的疊法合成。每個欄位是讀到的值還是量到的值，分開記：
  - 讀自資料與 prefab：
    - 封面：`card_pack` 精靈圖，`mirrordungeon-theme-floor` 的 `uiConfigs.packSpriteId` 就是精靈圖名稱，分散在卡包、鏡牢、活動 bundle；隱藏包 `The B.E.`（`HiddenTheme`）在 `skinpreview-new-pack`。
    - `bossSpriteId`：boss 圖（`Everydungeon/boss/`），錨點 (0.13, 0.25)–(0.875, 0.836)。`isHideLogo`：不畫 Limbus Company logo（`MainUI_MirrorDungeon4_4_16`，錨點 (0.34, 0.26)–(0.66, 0.34)）。`isShowBaton`：疊 `Sprite/UI/ThemePack/Baton.png`（「CHAIN BATTLE」三角與青色虛線）和「Long Battle」標籤（`mirror_theme_pack_baton`，Pretendard，`#73fbed`，自動縮放 5–35）。外框是 `_4_8`（塑膠膜），輪廓遮罩是 `_4_7`，警告三角是 `_4_6`，徽章底是 `_4_4`。這些精靈圖按名稱抽並檢查尺寸，客戶端改編號時工具會報錯。
    - 徽章：`[Rect]Attributes` 是一個 GridLayoutGroup，格子 96 × 96、左上起、無間距：`attackType` 的圖示（`Icon_AttackType_pierce/hit/slash`，`sharedassets1`）在第一格，顏色是 `mapOptions` 的 `SetColor_Cleared`（1204 的 `a16a3b`，和截圖上量到的完全一致）；`attributeType` 的圖示是 `Icon_evil_2_8`–`14`，只有屬性的包放第一格，兩者都有時放第二格（順序 unverified）。
    - 標題（`[Text]Name`，TextMeshProUGUI）：矩形錨點 (0.15, 0.17)–(0.85, 0.255)、sizeDelta (9, 0)、anchoredPosition (4.5, 0)；自動縮放 1–65、換行開、置中、垂直置中、overflow、字距 −2、字間 1、行距 −5、行高 1.09 em（字型資產 `Mikodacs SDF` 的 FaceInfo：點數 195、lineHeight 212.55），字型資產另有 `normalSpacingOffset` 6，所以每個字多 +0.04 em；材質 `Mikodacs SDF UnderLine` 只有 Underlay（深色 `#040001`、偏移 (1, −1)、柔化 0，一個硬陰影），沒有外框、沒有光暈；`m_enableVertexGradient` 是關的，沒有漸層。英文名稱取自 `EN_MirrorDungeonTheme-1`（有 `specialName` 的用它，TMP 的 `<color>` 標籤分段上色，`1119` 的粉、藍兩色就是這樣來的），顏色取 `uiConfigs.textColor`，沒有時是 `ebcaa2`（截圖上量到 `ebcaa2`）。字型 Mikodacs（OFL 1.1）從玩家資料讀，不進 repo，見 NOTICE.md。
  - 量自截圖（prefab 讀不到或和 prefab 不同）：
    - 卡片根的寬度是 680，prefab 寫 650：徽章格的位置（`0.128 × 寬 + 48`）和標題的最大寬度（485）兩項獨立量測都指向 680；高度照 prefab 的 1069。原因 unverified。
    - 自動縮放的 `lineSpacingMax`（−20）沒套用：套用的話 `Flat-broke Gamblers` 會排成兩行，和截圖不符；不套用的結果（`Flat-broke Gamblers` 一行、`Charm, Wander, Doubt` 兩行、`Nest, Workshop, and / Technology` 兩行）和截圖一致。TMP 實際的規則 unverified。
    - 警告三角（`isShowWarning`）不在卡片 prefab 裡，位置 (0.38, 0.79)–(0.62, 0.92) 是對照兩張截圖估的；徽章比 96 格大約 12 %；`attributeType` 的四個（`CRIMSON`、`AMBER`、`SHAMROCK`、`VIOLET`）圖示和填色是對照截圖認的（火焰、裂岩、葉、荊棘圈），`SCARLET`、`AZURE`、`INDIGO` 的圖示和填色是猜的（unverified）。
  - 沒對照過：`isShowBaton` 的「Long Battle」疊圖（位置、字級照 prefab，沒有截圖有 Line 系列的包，unverified）。
  - 沒做：頂端吊夾、放大鏡紅章、傾斜；依帳號狀態變的部分：截圖裡的 `1404`、`1412` 實機把 boss 圖畫成黑色剪影（bundle 裡有 `<boss>_silhouette` 精靈圖；什麼條件換成剪影 unverified，推測是帳號還沒見過那個 boss），縮圖畫完整的 boss；卡片左上角的紅點（`[Script]RedDot`，新包提示）也不畫；`iconYPos`（全部 121 個資料項裡只有 6 個有，用途 unverified）；`uiRotation`、`unlockHintTextKey`、`sidePopupUnlockHintTextKey`、`nextImageColor`（地圖節點和鎖定提示用，不影響卡片外觀，unverified）；卡片上的 `Chip`、`rect_level`（執行中才出現的提示，沒有截圖）。
  - 同一份封面的 `1201`／`1203`／`1205`（`AttackType_normal`）和 `1202`／`1204`／`1206`（`AttackType_effective`）靠 boss 圖、攻擊類型圖示和標題分辨。版權屬 © Project Moon（NOTICE.md）。
- 標題藝術字（`title_art`，#246）：卡面藝術字拼不出包名時，OCR 讀到的字 → 那個包。比對規則和包名相同，比的是左邊的字（同分時算它的長度），比到後換成右邊的包名。1.117.0 有三個，前兩個從 2026-10-22 的實機錄影確認：S.E.A. 卡面寫 `The Magic Hello Bus`（讀成 `HellOBus`、`HellBus`）；The Noon of Violet 名稱上方有 `Walpurgis Night`，常讀成 `WalpurgisN The Noon of`；Line 1 的藝術字是大寫的 `LINE 1 MADNESS`，只讀得到 `MADNESS`（#266）。每季換資料時，從 log 裡比對不到的標題找新的。
- 一張卡怎麼認（#274，`run_start.pack_cards`／`rank_packs`、`pack_cover.py`）：
  - 文字框分組與過濾：OCR 框重疊或相距 < 15 px 併成一張卡，兩段文字的中心距離 < 105 px（`CARD_SPAN`；卡片寬 182、間距 211）也算同一張，所以單獨的雜訊框（`M`、等級徽章的 `IV`）不會自成一張。**只丟掉完全等於已知非標題字詞的框**（`NOT_TITLE`：`LIMBUS`、`COMPANY`、`LIMBUS COMPANY`、`CAUTION`、`CLEAR BONUS`、`LV`，只比英數字、不分大小寫）；其餘大寫字都留作那張卡的一行，交給下面各條路判斷。以前的規則是「沒有小寫字母就丟掉」（#270 另留下寬 ≥ 80 px 的大寫框），會把大寫的標題字（`MADNESS`、`THE DUSK OF AMBER`、`WARP EXPRESS`）一起丟掉；logo 第二個字讀壞的雜訊（`WOPIS` 之類）現在留著：在標題行的前面時，名稱比對從各行起點試，會跳過；夾在標題行中間的雜訊（112 頁裡 1 張 Miracle in District 20 的 `OROAOZO`、`中R电`）會讓整標題比對失敗，由關鍵字接手。112 頁的詞表與兩種過濾的比較在 [theme-pack-recognition.md](../perf/data/05-game-data/theme-pack-recognition.md)。
  - 認的路徑（每張卡取第一個認出的，log 的 `floor N card reads` 一行寫每張卡走哪條）：`name` 整個標題（上面的標題比對）→ `title_art` → `keyword` → `cover N` → `shared`（標題像好幾個包而它們分數相同）→ `unread`（用「沒列出的包」分數）。
  - `keyword`：每個包取一個全表唯一的關鍵字（`run_start.pack_keywords`）：名稱裡最短、且沒有其他名稱（含 `title_art` 的字）包含它的單字（至少 4 個英數字），沒有這樣的單字時取名稱裡最短的唯一片段（`Line 1` → `ine1`）；全表沒有的包就沒有（`S.E.A.`：`sea` 在 `Mountain of Corpses, Sea of Blood` 裡）。OCR 只讀到一部分標題時，卡片文字裡找到關鍵字就認那個包（`match_keyword`：關鍵字原樣出現的優先，同一張卡有兩個包的關鍵字就不猜；沒有原樣的，7 個字以上的關鍵字容許錯一個字，相似度 ≥ 0.85，覆蓋字數最多的贏）。112 頁 531 張卡掃過，關鍵字從沒指向別的包（誤認 0）。
  - `cover`：整個標題都對不上時，用卡面圖案比對封面（#241 的縮圖）。`data/theme_pack_signatures.json` 每個包一張 12×16 的彩色縮圖（卡面圖案區，BGR），畫面上的卡切同一塊區域、同樣縮圖，比相關係數；最高的 ≥ 0.5 且領先第二名 ≥ 0.1 才算（`pack_cover.read_cover`），標題已經縮小範圍（`Line` 像 Line 1–3、5）時只在那幾個包裡比。卡片位置取標題中心貼齊以 x = 640 為中心、半個間距（105 px）為格的格線。限制：boss 還沒見過的包，實機把 boss 畫成黑色剪影，封面是彩色的，相關性低，這種卡 cover 不出聲；圖案相同、只有標題字不同的包也分不出（`Line 4 - Section #3`／`#4`、`Repressed Wrath`／`Unbound Wrath`）；（112 頁 531 張卡裡 cover 不出聲的有 64 張，含剪影卡、圖案相同的包和其他沒有領先 0.1 的卡，沒有逐張分類）；卡片左右搖擺時（傾斜、重疊）不出聲，所以先等卡片停下再讀（spec 03 第 6 節）。
- 使用者的主題包方案不在資料檔，存在設定檔，格式見 [04-settings.md](04-settings.md#8-主題包方案theme_pack_plans)。方案裡沒列出的主題包（例如新一季才出現的）用方案的「沒列出的包」分數；空的方案等於全部用這個分數，不報錯。（#11、#19，2026-10-14 定案；#240）

**範例**（主題包名稱取自先前季節，僅示意；「燒傷隊」是使用者在設定檔建立的方案）：

| 主題包 | 預設（資料檔） | 燒傷隊（設定檔） |
|---|---|---|
| `Burning Haze` | −5 | 8 |
| `Sinking Deluge` | −5 | 3 |
| `Hell's Chicken` | 1 | 0 |
| 刷新門檻 | 0 | 3 |

**使用規則**（#11）：

- 選分數最高的，同分選最左邊。（#240）
- 卡片上標記 NEW，或標題比對不到清單的，用方案的「沒列出的包」分數。
- 標題比對（`run_start.match_title`，#89）：只比英數字、不分大小寫。每個主題包名稱在 OCR 文字裡找一段同樣長度、最像它的片段，相似度 ≥ 0.8 才算候選；所以標題上方的 logo 碎字、沒讀到的第二行都不影響，短標題錯一兩個字（`Lime 2`、`Lake Wor1d`）仍比對得到。候選之中取「相似度 × 名稱長度」最大的，而且要比第二名多 1 個字以上：`Mountain of Corpses, Sea of Blood` 裡的 `Sea` 不會被認成 `S.E.A.`；`Line` 這種分不出 Line 1–3 的就算比對不到；分不出的幾個包分數相同時，用那個分數（預設方案的 Line 1–5 都是 −5），否則用「沒列出的包」的分數。
  - 離線檢查（#240，2026-10-22）：用現行的標題 OCR 與比對跑 `tests/screens/` 與實機截圖的 10 張主題包頁（其中 3 張是同一個畫面），32 張卡全部比對正確，包括有 logo 碎字（`LImBUS`、`enUPAm`）和標題分兩行的卡。以前實機 log 的 353 張卡中有 21 張比對不到：BokGak 後綴與 logo 前綴（共 4 張）是舊版比對造成的，現行比對已經比得到；`World Lake`／`Abyss Crawling`（共 3 張）是兩行標題的順序讀反（推測是卡片傾斜，unverified）；`HellOBus`、`Mirac inDistrict…`、`WalpurgisN The Noon of`、`Emotio`（共 10 張）是藝術字標題讀錯或讀不完整；2 張 `Time` 是同一張卡的標題被拆成兩欄；2 張 `Line` 分不出是哪個 Line 包，照它們共同的分數。AALC 的片段只救得回順序讀反的 3 張（`lake`、`abyss`），救不回藝術字那幾張，還會把拆出來的 `Time` 當成 `Timekilling Time`，所以不加片段比對當後備。順序讀反改成各行也倒過來比一次、取名稱較長的那個（`run_start.match_card`，#240）：第 5 層最左邊的一般包要是讀反，否則會被當成資料檔沒收錄的活動包。逐卡的 OCR 原文與比對結果、比對不到的 log 讀法在 [theme-pack-ocr.md](../perf/data/05-game-data/theme-pack-ocr.md)；截圖、實機 log 和離線檢查用的腳本留在本機。
  - 錄影檢查（#246，2026-10-22）：49 次讀包的錄影逐幀重跑 OCR。卡片發下後先滑入再左右搖擺，約 2.8 s 才停；bot 原本在標題出現後 0.6–1.1 s 就讀，搖擺中單幀只有 75% 的畫面每張卡都對，停下後 43/43 幀全對。所以先等卡片停下才讀（spec 03 第 6 節）。上面的推測更正：`HellOBus` 是 S.E.A. 不是 Hell's Chicken，`WalpurgisN The Noon of` 是 The Noon of Violet（兩者改用 `title_art` 認）；`Emotio` 是第三張卡還沒滑進來就讀了，漏掉整張 Hell's Chicken；`Time` 是卡片傾斜時同一行標題拆成兩個框。比較表與方法在 [theme-pack-ocr.md](../perf/data/05-game-data/theme-pack-ocr.md)。
- 畫面上最好的包分數低於方案的刷新門檻時，才用免費刷新，次數照執行選項 `theme_pack_refresh`；刷新用完後選分數最高的，絕不卡住。（#11、#19、#240）

## 3. 事件覆寫表

**用途**：只放例外。沒列出的事件照通用規則處理：一般選項依事件表（第 7 節）的實際效果排序，比不到事件表時照提示文字套同樣的 5 級（03 第 10 節）；技能判定選成功率等級最高的罪人。通用規則見 [03-decisions.md](03-decisions.md)。（#11、#93）

**內容**：問題文字 → 選項文字。問題文字用模糊比對；選項用選項文字指定，不用位置。一開始是空的，依 `runs.jsonl` 與錯誤截圖逐步補充。不為每個事件寫動作腳本。（#11，[ADR 0005](../adr/0005-game-data-files-separate-from-user-settings.md)）

**檔案**：`resource/base/data/events.yaml`，問題文字 → 選項文字。選項文字出現在畫面上某個選項裡就選它。（#28）

**使用者覆寫**：在 GUI 的表格編輯，存在設定檔的 `event_overrides`；同一個問題文字兩邊都有時以設定檔為準（[04-settings.md](04-settings.md#10-事件覆寫event_overrides)）。（#11、#19，2026-10-14 定案）

**範例**（虛構內容，僅示意）：

| 問題文字 | 選項 |
|---|---|
| `What will you do with the box?` | `Leave it` |

## 4. 試煉風險表

**用途**：Boss 後的選擇評分（困難；1.117.0 實機在普通局也看到，未見官方公告，待確認）。選項評分 = 飾品分數 − 權重 × 試煉風險；分數最高的勝出，同分時選試煉風險較低的。權重是每隊的「試煉風險權重」（低／中／高），見 [04-settings.md](04-settings.md)。（#17）

**內容**：試煉（Mounting Trial）的名稱 → 風險值（0–5）。從選項上 OCR 讀出試煉名稱再查表；查不到就當作最高風險 5。（#17、#19）

**檔案**：`resource/base/data/trial_risks.yaml`，試煉名稱 → 風險值。名稱先找完全相同的（`Growth I` 和 `Growth II` 太像，模糊比對分不開），再用模糊比對。（#28）

識別字用試煉名稱，含羅馬數字，例如 `Defense Level Up`、`Defense Skill Up`、`Take Less Damage`、`Growth I`、`Keen I`、`Offense Level Up II`。每個試煉旁另有紅色 `Enemy Level Up +1`／`+2` 標記，只有兩種值，不能當識別字。（實機：captures/122_boss_gift_trials_page.png、captures/176_f2boss_rewards_gift.png）

評分的初始數值如下，等截圖確認後再調整：（#19）

| 項目 | 初始值 |
|---|---|
| 飾品分數 | 主要體系 3、其他 2、已擁有 0 |
| 試煉風險 | 0–5 |
| 權重 | 低 0.5、中 1、高 2 |

**範例**（試煉名稱取自實機，風險值僅示意）：

| 試煉 | 風險 |
|---|---|
| `Defense Level Up` | 1 |
| `Growth I` | 3 |

**維護**：開發者每季更新。（#17）

**使用者覆寫**：在 GUI 的表格編輯，存在設定檔的 `trial_risk_overrides`；同一個試煉兩邊都有時以設定檔為準（[04-settings.md](04-settings.md#11-試煉風險覆寫trial_risk_overrides)）。（#17、#19，2026-10-14 定案）

## 5. 選路權重

**用途**：地圖頁只看相鄰一欄，依權重貪婪選擇，越低越優先。（#12）

**內容與預設值**（#12）：

| 節點類型 | 普通 | 困難 |
|---|---|---|
| 事件 | 1 | 1 |
| 普通戰鬥 | 2 | 2 |
| Focused 集中（`AB_BATTLE`） | 4 | 4 |
| 異想體戰 Abnormality（`HARD_AB_BATTLE`） | 5 | 5 |
| Risky 精銳（`HARD_BATTLE`） | 6 | 8 |
| 無法辨識 | 9 | 9 |

- 困難模式的權重和普通模式相同，只把 Risky 改為 8，所以無法辨識仍然排最後。（#12、#19）
- 商店不在上表：bot 不特地找商店，所以資料檔給它 7，排在可辨識的戰鬥之後、無法辨識之前，兩種難度相同。資料檔是 `resource/base/data/map_weights.yaml`。（#26）
- Boss 只在它是唯一可走的節點時才走；這是規則，不是權重。（#12）
- 同權重時選下一欄可走路線最多的節點，見 [03-decisions.md](03-decisions.md)。（#12）

## 6. Cost 對照表與商店數字

這些數字放在資料檔，不寫成程式常數。（#19）

**節點 Cost**：戰鬥節點的種類由 Cost 數字＋難度查這張表（資料檔 `map_weights.yaml` 的 `node_costs`，#91，2026-10-21；原本只供參考）。同一難度內各不相同；外圈與禮物盒只在數字讀不到時才用，見 [03-decisions.md](03-decisions.md) 第 7 節。

| 節點類型 | 普通 | 困難 | 外圈 | 禮物盒 |
|---|---|---|---|---|
| 普通戰鬥 Regular（`battle`） | 75 | 85 | – | – |
| Focused 集中（`focused`） | 100 | 120 | – | ✔ |
| Risky 精銳（`risky`） | 120 | 150 | ✔ | ✔ |
| 異想體戰 Abnormality（`abno`） | 150 | 180 | ✔ | ✔ |

**困難模式的實測 Cost**：下表是 2026-10-13 困難鏡牢實機看到的節點 Cost 標記，不是資料檔的預設值，也不是 wiki 的數字。節點欄是當時的稱呼；照上表（#91）重新對照後與上表一致：外圈 150 是困難 Risky、180 是困難 Abnormality，禮物盒無外圈的 120 是困難 Focused。

| 節點 | 實測 Cost | 實機截圖 |
|---|---|---|
| 普通戰鬥 | 85 | `captures/23_after_pack_pull.png`、`178_f3_map.png` |
| 橘色 `WARNING` 外圈（當時稱 Focused；Risky、Abnormality） | 150、180 | `captures/152_focused_node_selected.png`、`178_f3_map.png`、`223_f5_map.png` |
| 禮物盒、無外圈（當時稱異想體戰；Focused） | 120 | `captures/179_f3_abno_node_selected.png`、`225_f5ev_map.png` |
| 事件、商店 | 沒有 Cost 標記 | `captures/131_f2_event_selected.png`、`74_battle4_map.png` |
| Boss | 第 1–4 層依序 250、300、375、500；第 5 層沒有標記 | `captures/74_battle4_map.png`、`175_f2_map_after_supershop.png`、`196_f3_map_before_boss.png`、`216_f4_map_before_boss.png`、`230_f5abno_rewards_map.png` |

商店節點的選取面板顯示的是下一個 Boss 的 Cost，不是商店本身的。

**商店數字**（#10、#19）

| 項目 | 值 |
|---|---|
| 普通刷新費用 | 15 起，每次 +15 |
| 定向刷新費用 | 90 起，每次 +15 |
| 刷新條件 | Cost ≥ 刷新費用 + 120（定向與普通刷新相同） |
| 全體治療門檻 | 100 |

**檔案**：`resource/base/data/shop.yaml`，只放全體治療（每項治療）費用 `heal_cost` 與刷新條件的 `refresh_margin`。刷新費用 bot 從商店按鈕下方讀，不放資料檔。（#29）

實機的刷新費用（普通 15 → 30、定向 90 → 105）與治療費用（每項 100）和上表一致（實機：captures/107_shop_after_refresh.png、captures/82_shop_heal_page.png）。

## 7. 事件表

**用途**：事件頁依每個選項的實際效果排序（規則見 [03-decisions.md](03-decisions.md) 第 10 節）。（#93）

**檔案**：`resource/base/data/event_table.json`，由 `tools/event_table.py` 從拆包的事件表（limbus-unpack 的 `scripts/events_md8.py` 產生的 `events-md8.json`，遊戲客戶端 1.117.0 的靜態資料與英文在地化）裁出。檔頭的 `note` 與 `client` 寫來源與版本。使用者不能修改；例外改用事件覆寫表。

**內容**：每個有敘事文字的選擇事件一筆（195 筆，同一頁不同 id 的合併），只留 bot 要用的欄位：

| 欄位 | 內容 |
|---|---|
| `id` | 遊戲的事件 id，只供查閱 |
| `key` | 故事文字的最後 60 個英數字（小寫）：敘事框顯示的是故事結尾 |
| `options[].text`、`hint` | 選項文字與下方提示（去掉標籤）；畫面上的選項靠這兩項對到表上 |
| `options[].kind` | `direct`、`random`、`check`、`check_fail_gift`、`followup`、`battle`、`check_other`、`followup_other`、`other`；`random` 的提示是 `???`（971055）或寫明機率（971003），兩者在 03 第 10 節分屬不同級 |
| `options[].gifts` | `[體系, 取得方式]`，取得方式如 `direct`、`check_pass`、`check_fail`、`win_battle`、`later_direct` |

飾品的體系取自靜態資料 `ego-gift-mirrordungeon` 的 `keyword`：`events_md8.py` 取到的是同 id 第一筆、沒有 keyword 的紀錄，會把 Grimy Iron Stake 這類飾品讀成 Keywordless，`tools/event_table.py` 重新查一次。沒有敘事文字的 13 個事件（Boss 戰中途與部分後續頁）不收，照提示文字規則處理。

## 8. 每季更新檢查清單

新一季鏡牢開始時，開發者依序：

1. 更新主題包清單（含樓層），並提供這一季的預設主題包方案。使用者方案裡沒有的新主題包自動用方案的「沒列出的包」分數，不必改設定檔。（#11、#19、#240）
   - 重產卡片縮圖：先把新版客戶端的 `UnityCache`、APK 玩家資料（`apk-data/assets/bin/Data`）、靜態資料與英文在地化拆到 `.local/unpack/`（見 `docs/agents/local-dev.md`），再 `uv run python tools/live/queue.py run --resource bench --name theme_covers -- uv run --group unpack python tools/theme_pack_covers.py --contact-sheet <檔名>.png`（要 `bench` 號碼牌，讀 12 GB bundle 與玩家資料）。工具依 `theme_packs.yaml` 每行註解的 id 找資料，印出 `no cover:` 的包（新包沒有封面時 GUI 顯示名稱）；卡片零件的精靈圖名稱或尺寸對不上時直接報錯，表示客戶端改了圖集編號，要重讀卡片 prefab（`MirrorDungeonThemeCardUI`，在 `sharedassets7`）。`tests/test_theme_pack_covers.py` 檢查每個包都有檔、寬度和總量。（#241）
   - 重產卡片縮圖之後，再跑 `uv run python tools/theme_pack_signatures.py` 更新 `theme_pack_signatures.json`（只讀縮圖，不需要遊戲檔）；`tests/test_pack_cover.py` 檢查檔案和縮圖一致。新一季的 `NOT_TITLE`、關鍵字和 cover 效果用 `uv run python tools/pack_stats.py <截圖資料夾> --glob "*raw*.png"` 重跑（離線 OCR）。（#274）
2. 更新試煉風險表。（#17）
3. 檢查選路權重、Cost 對照表與商店數字是否仍符合遊戲。（#10、#12）
4. 依上一季的記錄補充事件覆寫表。（#11）
5. 拆包新版客戶端，重跑 `events_md8.py`（換成這一季的鏡牢編號）與 `tools/event_table.py` 更新事件表，NOTICE.md 的版本一併更新。（#93）
   - 重產合成飾品表：`uv run python tools/live/queue.py run --resource bench --name gift_recipes -- uv run --group unpack python tools/gift_recipes.py`（用法見工具檔頭）。（#277）
   - 更新中文名：`uv run --group unpack python tools/llc_text.py --release <LLC 最新 release>`，改寫 `gift_search.json`、`gift_recipes.json`、`gui/src/graces.json` 的中文名與星之恩惠效果文字，並記下所用 release；NOTICE.md 的 release 一併更新。（#280）
   - 預設飾品清單：確認 `gift_lists.yaml` 的 id 都還在 `gift_search.json`、`gift_recipes.json`、殘影裡（`tests/test_gift_lists.py` 會檢查，也檢查內容符合第 9 節）；重產 GUI 圖示：`uv run python tools/live/queue.py run --resource bench --name gift_icons -- uv run --group unpack python tools/gift_icons.py`。（#293）
6. 重截約 20 個關鍵畫面加進測試，跑 `maa-tools test`；分數餘裕小於 0.05 的節點標出來檢查。（#13）
7. 截圖必須經 MaaFramework 控制器縮到短邊 720，遮掉 UID 與帳號名稱。（#13）

這一季 Mirror of Names and Spiders 在 2026-10-15 結束；主題包頁、事件頁、獎勵卡頁、地圖頁的實機截圖要等新一季開始再截。（#11、#12）主題包清單已依 1.117.0 客戶端資料更新（#89）。

## 9. 預設飾品清單與圖示

**用途**：設定的飾品清單（[04-settings.md](04-settings.md)，#291）有一份唯讀的「預設」，使用者只能複製；設定 GUI 的飾品格要顯示每個飾品的圖示。（#291、#293）

**預設清單**：`resource/base/data/gift_lists.yaml` 的 `default_list`，欄位同設定檔 `gift_lists[]` 的一項去掉 `id`、`name`（`order`、`want`、`keep`、`gorder`、`fusion_condition`）。內容照原本的預設隊伍轉過來（使用者 2026-10-23 決定）：

- `order`：Gift Search 頁的分頁順序，Burn 第一、`Keywordless` 最後。
- `want`：Burn 在商店買得到的 22 個（I–III 階）與月之記憶（9083），共 23 個。
- `keep`：所有無體系飾品，共 90 個：`gift_search.json` 的 82 個、`gift_recipes.json` 其餘 3 個無體系合成品、5 個殘影（9991–9995）。無體系飾品一律 `keep`：不賣，也不當合成材料。
- 其餘是 `drop`。`gorder`：每個體系 III、II、I 階，階內照 `gift_search.json` 的順序。`fusion_condition`：`any`。

**圖示**：`resource/base/data/gift_icons/<id>.webp` 與 `index.json`（`{id: 檔名}`），由 `tools/gift_icons.py` 產生。涵蓋 `gift_search.json` 的 320 個、`gift_recipes.json` 的 60 個合成品與 12 個材料、5 個殘影，共 397 個。圖示取自遊戲的 EgoGiftIcon 精靈圖，保留透明，縮成 56 px（最長邊）、WebP quality 72；整批 574,696 位元組，平均約 1.4 KB。`image/GiftSearch/`、`image/GiftRecipe/` 的綠底模板是 Agent 比對用，不動。`tests/test_gift_lists.py` 檢查預設清單的 id 與內容、圖示齊全與總量。（#293）
