# AALC 資產索引 (Asset Index)

## 概要 (Overview)

本文檔列舉 AALC 自動化工具中使用的所有遊戲內按鈕、文本框、提示框和狀態指示器的圖片資源，包括模型、配置文件和應用資源。

**來源版本 (Source)**: commit `b0f439321987f5f7b126ebbc424f6ef144c1bff0`  
**資源統計**:
- 圖片文件總數: 491
- 相對路徑數量: 391
- 有程式引用的資源: 220 (56.3%)
- 無引用的資源: 171 (43.7%)
- 模型文件: 1 (best.onnx)
- 配置文件: 4
- 應用資源子目錄: 5

## 資源路徑解析方式 (Asset Path Resolution)

### 主題與語言系統 (Theme and Language System)

AALC 使用雙層路徑系統來管理多主題與多語言的遊戲圖片:
- **主題**: `default` (標準) / `dark` (深色)
- **語言**: `zh_cn` (簡體中文) / `en` (英文) / `share` (共用資源)

完整路徑格式: `./assets/images/{theme}/{language}/{category}/{filename}`

**例**: 
- `./assets/images/default/zh_cn/base/waiting_assets.png`
- `./assets/images/dark/share/battle/pause_assets.png`

### 路徑優先級與解析流程

由 [`utils/path_manager.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/utils/path_manager.py) 和 [`utils/image_utils.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/utils/image_utils.py) 管理。

搜尋優先級 (按順序):
1. `dark/zh_cn` (深色簡體中文)
2. `dark/en` (深色英文)
3. `dark/share` (深色共用)
4. `default/zh_cn` (標準簡體中文)
5. `default/en` (標準英文)
6. `default/share` (標準共用)

程式碼透過相對路徑參考資源 (如 `"base/waiting_assets.png"`), `image_utils.py` 在上述目錄順序中查找實際文件。若 `dark` 路徑已被消除 (theme 設為 default), 則跳過所有 dark 開頭的路徑。

### 動態路徑構建

部分資源路徑由程式碼動態構建，例如:
- 系統別禮物圖片: `f"mirror/road_to_mir/select_init_gift/{team_system}_ego_gift_{order}.png"`
- 獲獲獲卡片: `f"mirror/get_reward_card/{card}.png"`
- 商店系統篩選: `f"mirror/shop/enhance_gifts/shop_{system}.png"`

參見 [`tasks/mirror/in_shop.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py) 和 [`tasks/mirror/mirror.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py)。

---

## 資源分類表 (Asset Tables by Category)

### BASE (14 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `base/clear_all_caches_assets.png` | default/share | [tasks/base/retry.py:177](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L177), [tasks/base/back_init_menu.py:111](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L111) | 03-daily-tasks.md |
| `base/connecting_assets.png` | default/share | [tasks/base/retry.py:161](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L161) | — |
| `base/leave_up_assets.png` | default/share | [tasks/battle/battle.py:495](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L495) | 12-md-battle.md |
| `base/leave_up_confirm_assets.png` | default/share | [tasks/battle/battle.py:496](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L496) | 12-md-battle.md |
| `base/notification_close_assets.png` | default/en, default/zh_cn | [tasks/base/back_init_menu.py:42](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L42) | 03-daily-tasks.md |
| `base/only_option_assets.png` | default/share | [tasks/base/retry.py:182](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L182), [tasks/base/back_init_menu.py:118](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L118) | 03-daily-tasks.md |
| `base/renew_confirm_assets.png` | dark/share, default/share | [tasks/daily/luxcavation.py:103](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L103), [tasks/daily/luxcavation.py:106](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L106), ...及 6 項 | 03-daily-tasks.md |
| `base/retry.png` | default/en, default/zh_cn | [tasks/base/retry_monitor.py:15](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry_monitor.py#L15), [tasks/base/retry.py:167](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L167), ...及 2 項 | — |
| `base/retry_countdown.png` | default/en, default/zh_cn | [tasks/base/retry.py:163](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L163), [tasks/base/retry.py:171](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L171) | — |
| `base/try_again.png` | default/en, default/zh_cn | [tasks/base/retry.py:173](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L173) | — |
| `base/update_close_assets.png` | default/share | [tasks/base/make_enkephalin_module.py:121](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L121), [tasks/base/make_enkephalin_module.py:124](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L124) | 03-daily-tasks.md |
| `base/update_confirm_assets.png` | default/share | [tasks/base/retry.py:178](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/retry.py#L178), [tasks/base/back_init_menu.py:112](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L112) | 03-daily-tasks.md |
| `base/waiting_2_assets.png` | default/share | [tasks/base/back_init_menu.py:88](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L88), [tasks/mirror/mirror.py:548](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L548) | 03-daily-tasks.md, 10-mirror-dungeon-overview.md |
| `base/waiting_assets.png` | default/share | [tasks/battle/battle.py:262](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L262), [tasks/base/back_init_menu.py:88](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L88), ...及 1 項 | 03-daily-tasks.md, 12-md-battle.md |

### BATTLE (25 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `battle/battle_finish_confirm_assets.png` | default/share | [tasks/battle/battle.py:491](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L491), [tasks/battle/battle.py:508](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L508), ...及 1 項 | 12-md-battle.md |
| `battle/chaim_to_battle_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:60](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L60), [tasks/battle/battle.py:70](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L70), ...及 1 項 | 12-md-battle.md |
| `battle/clear_rewards_EXP_1_assets.png` | default/share | [tasks/battle/battle.py:501](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L501) | 12-md-battle.md |
| `battle/clear_rewards_EXP_2_assets.png` | default/share | [tasks/battle/battle.py:502](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L502) | 12-md-battle.md |
| `battle/clear_rewards_EXP_3_assets.png` | default/share | [tasks/battle/battle.py:503](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L503) | 12-md-battle.md |
| `battle/clear_rewards_thread_assets.png` | default/share | [tasks/battle/battle.py:506](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L506) | 12-md-battle.md |
| `battle/continue_assets.png` | default/share | [tasks/battle/battle.py:527](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L527) | 12-md-battle.md |
| `battle/dead.png` | default/en, default/zh_cn | [tasks/battle/battle.py:310](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L310) | 12-md-battle.md |
| `battle/dead_all.png` | default/share | [tasks/battle/battle.py:284](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L284), [tasks/battle/battle.py:285](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L285) | 12-md-battle.md |
| `battle/dead_all_confirm_assets.png` | default/share | [tasks/battle/battle.py:290](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L290), [tasks/battle/battle.py:300](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L300) | 12-md-battle.md |
| `battle/gear_left.png` | default/share | [tasks/battle/battle.py:130](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L130), [tasks/battle/battle.py:156](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L156), ...及 3 項 | 12-md-battle.md |
| `battle/gear_right.png` | default/share | [tasks/battle/battle.py:185](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L185), [tasks/battle/battle.py:606](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L606), ...及 2 項 | 12-md-battle.md |
| `battle/give_up_assets.png` | dark/share, default/share | [tasks/battle/battle.py:326](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L326), [tasks/base/back_init_menu.py:102](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L102), ...及 1 項 | 03-daily-tasks.md, 12-md-battle.md |
| `battle/in_mirror_assets.png` | default/share | [tasks/battle/battle.py:267](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L267), [tasks/mirror/mirror.py:408](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L408), ...及 1 項 | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `battle/more_information_assets.png` | default/share | [tasks/battle/battle.py:375](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L375), [tasks/mirror/mirror.py:407](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L407) | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `battle/normal_give_up_assets.png` | dark/share, default/share | [tasks/base/back_init_menu.py:103](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L103) | 03-daily-tasks.md |
| `battle/normal_to_battle_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:59](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L59), [tasks/battle/battle.py:66](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L66), ...及 2 項 | 12-md-battle.md |
| `battle/pause_assets.png` | default/share | [tasks/battle/battle.py:151](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L151), [tasks/battle/battle.py:171](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L171), ...及 3 項 | 12-md-battle.md |
| `battle/select_none_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:401](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L401) | 10-mirror-dungeon-overview.md |
| `battle/setting_assets.png` | default/share | [tasks/battle/battle.py:329](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L329), [tasks/base/back_init_menu.py:100](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L100) | 03-daily-tasks.md, 12-md-battle.md |
| `battle/turn_assets.png` | default/share | [tasks/battle/battle.py:354](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L354), [tasks/battle/battle.py:369](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L369), ...及 6 項 | 12-md-battle.md |
| `battle/turn_ocr_assets.png` | default/share | [tasks/battle/battle.py:219](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L219) | 12-md-battle.md |
| `battle/view_status_assets.png` | default/share | [tasks/battle/battle.py:270](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L270) | 12-md-battle.md |
| `battle/win_rate_assets.png` | default/share | [tasks/battle/battle.py:369](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L369), [tasks/battle/battle.py:376](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L376), ...及 1 項 | 12-md-battle.md |
| `battle/win_rate_card.png` | default/share | [tasks/battle/battle.py:182](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L182), [tasks/battle/battle.py:398](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L398), ...及 2 項 | 12-md-battle.md |

### ENKEPHALIN (9 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `enkephalin/all_in_assets.png` | dark/share, default/share | [tasks/base/make_enkephalin_module.py:142](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L142), [tasks/base/make_enkephalin_module.py:154](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L154) | 03-daily-tasks.md |
| `enkephalin/enkephalin_cancel_assets.png` | dark/share, default/share | [tasks/base/make_enkephalin_module.py:141](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L141), [tasks/base/make_enkephalin_module.py:166](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L166), ...及 2 項 | 03-daily-tasks.md |
| `enkephalin/enkephalin_confirm_assets.png` | dark/share, default/share | [tasks/base/make_enkephalin_module.py:160](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L160), [tasks/base/make_enkephalin_module.py:211](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L211) | 03-daily-tasks.md |
| `enkephalin/enkephalin_now_bbox.png` | dark/share, default/share | [tasks/base/make_enkephalin_module.py:47](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L47) | 03-daily-tasks.md |
| `enkephalin/lunacy_assets.png` | dark/share, default/share | [tasks/tools/production_module.py:89](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/tools/production_module.py#L89), [tasks/base/make_enkephalin_module.py:12](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L12) | 03-daily-tasks.md |
| `enkephalin/lunacy_spend_26_assets.png` | default/share | — | — |
| `enkephalin/lunacy_spend_52_assets.png` | default/share | — | — |
| `enkephalin/lunacy_spend_78_assets.png` | default/share | — | — |
| `enkephalin/use_lunacy_assets.png` | dark/en, dark/zh_cn, default/en, default/zh_cn | [tasks/tools/production_module.py:90](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/tools/production_module.py#L90), [tasks/base/make_enkephalin_module.py:140](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L140), ...及 1 項 | 03-daily-tasks.md |

### EVENT (17 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `event/advantage_check.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1288](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1288) | 10-mirror-dungeon-overview.md |
| `event/choices_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:424](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L424), [tasks/mirror/mirror.py:1296](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1296) | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `event/commence_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:472](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L472), [tasks/mirror/mirror.py:1311](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1311) | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `event/commence_battle_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1313](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1313) | 10-mirror-dungeon-overview.md |
| `event/continue_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:441](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L441), [tasks/battle/battle.py:468](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L468), ...及 2 項 | 12-md-battle.md |
| `event/gain_a_ego_depending_on_result.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1291](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1291) | 10-mirror-dungeon-overview.md |
| `event/high.png` | default/en, default/zh_cn | [tasks/event/event_handling.py:11](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/event/event_handling.py#L11) | 14-md-navigation.md |
| `event/low.png` | default/en, default/zh_cn | [tasks/event/event_handling.py:13](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/event/event_handling.py#L13) | 14-md-navigation.md |
| `event/normal.png` | default/en, default/zh_cn | [tasks/event/event_handling.py:12](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/event/event_handling.py#L12) | 14-md-navigation.md |
| `event/perform_the_check_feature_assets.png` | default/share | [tasks/battle/battle.py:465](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L465), [tasks/mirror/mirror.py:1302](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1302) | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `event/proceed_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:470](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L470), [tasks/mirror/mirror.py:1309](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1309) | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `event/select_first_option_assets.png` | default/share | [tasks/battle/battle.py:425](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L425), [tasks/battle/battle.py:428](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L428), ...及 7 項 | 12-md-battle.md |
| `event/select_to_gain_ego.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1280](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1280) | 10-mirror-dungeon-overview.md |
| `event/skip_assets.png` | default/share | [tasks/battle/battle.py:474](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L474), [tasks/mirror/mirror.py:166](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L166), ...及 2 項 | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `event/unknown_event.png` | default/share, default/zh_cn | [tasks/mirror/mirror.py:1276](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1276) | 10-mirror-dungeon-overview.md |
| `event/very_high.png` | default/en, default/zh_cn | [tasks/event/event_handling.py:10](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/event/event_handling.py#L10) | 14-md-navigation.md |
| `event/very_low.png` | default/en, default/zh_cn | [tasks/event/event_handling.py:14](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/event/event_handling.py#L14) | 14-md-navigation.md |

### HOME (11 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `home/back_assets.png` | dark/share, default/share | [tasks/daily/luxcavation.py:59](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L59), [tasks/daily/luxcavation.py:153](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L153), ...及 7 項 | 03-daily-tasks.md |
| `home/close_anniversary_event_assets.png` | default/share | [tasks/base/back_init_menu.py:107](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L107), [tasks/mirror/mirror.py:680](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L680), ...及 1 項 | 03-daily-tasks.md, 10-mirror-dungeon-overview.md |
| `home/drive_assets.png` | dark/share, default/share | [tasks/daily/luxcavation.py:104](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L104), [tasks/daily/luxcavation.py:111](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L111), ...及 10 項 | 03-daily-tasks.md |
| `home/enkephalin_box_assets.png` | default/share | [tasks/base/make_enkephalin_module.py:146](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L146) | 03-daily-tasks.md |
| `home/first_prompt_assets.png` | default/share | [tasks/daily/luxcavation.py:58](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L58), [tasks/daily/luxcavation.py:84](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L84), ...及 5 項 | 03-daily-tasks.md |
| `home/inferno_bus_assets.png` | dark/share, default/share | [tasks/daily/luxcavation.py:98](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L98), [tasks/daily/luxcavation.py:226](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L226), ...及 1 項 | 03-daily-tasks.md |
| `home/luxcavation_assets.png` | default/en, default/zh_cn | [tasks/daily/luxcavation.py:96](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L96), [tasks/daily/luxcavation.py:98](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L98), ...及 4 項 | 03-daily-tasks.md |
| `home/mail_assets.png` | dark/share, default/share | [tasks/daily/get_prize.py:46](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L46), [tasks/daily/get_prize.py:91](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L91), ...及 1 項 | 03-daily-tasks.md |
| `home/mirror_dungeons_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:186](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L186), [tasks/mirror/mirror.py:189](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L189), ...及 1 項 | 10-mirror-dungeon-overview.md |
| `home/season_assets.png` | default/share | [tasks/daily/get_prize.py:28](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L28), [tasks/daily/get_prize.py:31](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L31) | 03-daily-tasks.md |
| `home/window_assets.png` | dark/share, default/share | [tasks/daily/luxcavation.py:101](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L101), [tasks/daily/luxcavation.py:229](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L229), ...及 5 項 | 03-daily-tasks.md |

### LUXCAVATION (8 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `luxcavation/continuous_combat_up_box.png` | default/share | [tasks/daily/luxcavation.py:29](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L29) | 03-daily-tasks.md |
| `luxcavation/exp_enter.png` | dark/share, default/share | [tasks/daily/luxcavation.py:60](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L60), [tasks/daily/luxcavation.py:64](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L64), ...及 1 項 | 03-daily-tasks.md |
| `luxcavation/thread_assets.png` | default/share | [tasks/daily/luxcavation.py:221](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L221) | 03-daily-tasks.md |
| `luxcavation/thread_consume.png` | dark/share, default/share | [tasks/daily/luxcavation.py:155](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L155), [tasks/daily/luxcavation.py:169](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L169), ...及 2 項 | 03-daily-tasks.md |
| `luxcavation/thread_continuous_combat_show_box.png` | default/share | [tasks/daily/luxcavation.py:17](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L17) | 03-daily-tasks.md |
| `luxcavation/thread_enter_assets.png` | dark/share, default/share | — | — |
| `luxcavation/thread_enter_up80_assets.png` | default/share | [tasks/daily/luxcavation.py:154](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L154), [tasks/daily/luxcavation.py:159](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L159) | 03-daily-tasks.md |
| `luxcavation/thread_scroll_bar.png` | dark/share, default/share | [tasks/daily/luxcavation.py:170](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L170) | 03-daily-tasks.md |

### MAIL (3 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `mail/claim_all_assets.png` | dark/en, dark/zh_cn, default/en, default/zh_cn | [tasks/daily/get_prize.py:85](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L85) | 03-daily-tasks.md |
| `mail/close_assets.png` | default/en, default/zh_cn | [tasks/daily/get_prize.py:83](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L83), [tasks/daily/get_prize.py:89](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L89) | 03-daily-tasks.md |
| `mail/get_mail_prize_confirm.png` | default/share | [tasks/daily/get_prize.py:82](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L82) | 03-daily-tasks.md |

### MIRROR (287 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `mirror/claim_reward/battle_statistics_assets.png` | default/share | [tasks/battle/battle.py:492](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L492), [tasks/mirror/mirror.py:256](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L256) | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `mirror/claim_reward/claim_forfeit_assets.png` | default/en | [tasks/mirror/mirror.py:586](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L586) | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/claim_rewards_assets.png` | default/share | [tasks/mirror/mirror.py:257](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L257), [tasks/mirror/mirror.py:259](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L259), ...及 7 項 | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/claim_rewards_confirm_assets.png` | dark/share, default/share | [tasks/mirror/mirror.py:569](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L569), [tasks/mirror/mirror.py:1535](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1535) | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/clear_assets.png` | default/share | [tasks/mirror/mirror.py:158](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L158), [tasks/mirror/mirror.py:557](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L557) | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/coins.png` | default/share | [tasks/mirror/mirror.py:645](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L645) | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/coins_bbox.png` | default/share | [tasks/mirror/mirror.py:627](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L627) | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/complete_mirror_100%_assets.png` | default/share | [tasks/mirror/mirror.py:267](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L267), [tasks/mirror/mirror.py:331](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L331), ...及 3 項 | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/rewards_acquired_assets.png` | default/share | [tasks/mirror/mirror.py:566](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L566), [tasks/mirror/mirror.py:1532](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1532) | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/use_enkephalin_assets.png` | dark/share, default/en | [tasks/mirror/mirror.py:271](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L271), [tasks/mirror/mirror.py:593](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L593), ...及 5 項 | 10-mirror-dungeon-overview.md |
| `mirror/claim_reward/weekly_bonuses.png` | default/share | [tasks/mirror/mirror.py:604](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L604), [tasks/mirror/mirror.py:616](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L616), ...及 2 項 | 10-mirror-dungeon-overview.md |
| `mirror/get_reward_card/continue_choosing_assets.png` | default/share | [tasks/mirror/reward_card.py:63](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/reward_card.py#L63) | 10-mirror-dungeon-overview.md |
| `mirror/get_reward_card/gain_cost.png` | default/share | — | — |
| `mirror/get_reward_card/gain_cost_and_ego.png` | default/share | — | — |
| `mirror/get_reward_card/gain_ego.png` | default/share | — | — |
| `mirror/get_reward_card/gain_ego_resource.png` | default/share | — | — |
| `mirror/get_reward_card/gain_starlight.png` | default/share | — | — |
| `mirror/get_reward_card/get_reward_card_confirm_assets.png` | default/share | [tasks/mirror/reward_card.py:69](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/reward_card.py#L69), [tasks/mirror/reward_card.py:81](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/reward_card.py#L81) | 10-mirror-dungeon-overview.md |
| `mirror/infinity_mirror_assets.png` | default/share | [tasks/mirror/mirror.py:503](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L503) | 10-mirror-dungeon-overview.md |
| `mirror/infinity_mirror_close_assets.png` | default/share | [tasks/mirror/mirror.py:504](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L504) | 10-mirror-dungeon-overview.md |
| `mirror/mybus_default_distance.png` | default/share | [tasks/mirror/search_road.py:71](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L71), [tasks/mirror/search_road.py:91](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L91), ...及 10 項 | — |
| `mirror/mybus_maximum_distance.png` | default/share | [tasks/mirror/search_road.py:262](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L262) | — |
| `mirror/road_in_mir/acquire_ego_gift/bleed.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/blunt.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/burn.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/charge.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/pierce.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/poise.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/rupture.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/sinking.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/slash.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift/tremor.png` | default/share | — | — |
| `mirror/road_in_mir/acquire_ego_gift_box_assets.png` | default/share | [tasks/mirror/mirror.py:439](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L439) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/acquire_ego_gift_card.png` | default/share | [tasks/battle/battle.py:517](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L517), [tasks/mirror/reward_card.py:60](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/reward_card.py#L60), ...及 2 項 | 10-mirror-dungeon-overview.md, 12-md-battle.md |
| `mirror/road_in_mir/acquire_ego_gift_refuse_assets.png` | default/share | [tasks/mirror/mirror.py:441](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L441), [tasks/mirror/mirror.py:1348](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1348) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/acquire_ego_gift_select_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1353](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1353), [tasks/mirror/mirror.py:1392](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1392), ...及 4 項 | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/battle.png` | default/share | [tasks/mirror/search_road.py:121](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L121) | — |
| `mirror/road_in_mir/clear_floor.png` | default/share | — | — |
| `mirror/road_in_mir/down.png` | default/share | — | — |
| `mirror/road_in_mir/ego_gift_get_bbox.png` | default/share | [tasks/mirror/mirror.py:1475](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1475) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/ego_gift_get_confirm_assets.png` | default/share | [tasks/mirror/in_shop.py:165](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L165), [tasks/mirror/in_shop.py:176](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L176), ...及 21 項 | 13-md-ego-gifts.md |
| `mirror/road_in_mir/enter_assets.png` | default/share | [tasks/mirror/search_road.py:69](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L69), [tasks/mirror/search_road.py:73](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L73), ...及 10 項 | — |
| `mirror/road_in_mir/event.png` | default/share | [tasks/mirror/search_road.py:118](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L118) | — |
| `mirror/road_in_mir/event_effect_button.png` | default/share | [tasks/mirror/mirror.py:314](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L314) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/focused_encounter.png` | default/share | [tasks/mirror/search_road.py:127](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L127) | — |
| `mirror/road_in_mir/forfeit_assets.png` | dark/share, default/share | [tasks/mirror/mirror.py:250](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L250), [tasks/mirror/mirror.py:1192](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1192) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/get_floor_bbox.png` | default/share | — | — |
| `mirror/road_in_mir/legend_assets.png` | default/share | [tasks/battle/battle.py:256](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L256), [tasks/battle/battle.py:324](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L324), ...及 9 項 | 12-md-battle.md |
| `mirror/road_in_mir/mid.png` | default/share | — | — |
| `mirror/road_in_mir/not_passed_floor.png` | dark/share, default/share | — | — |
| `mirror/road_in_mir/refuse_gift_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1413](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1413) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/refuse_gift_confirm_assets.png` | default/share | [tasks/mirror/mirror.py:1418](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1418) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/risky_encounter.png` | default/share | [tasks/mirror/search_road.py:125](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L125) | — |
| `mirror/road_in_mir/select_encounter_reward_card_assets.png` | default/en, default/zh_cn | [tasks/battle/battle.py:476](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/battle/battle.py#L476), [tasks/base/back_init_menu.py:76](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L76), ...及 2 項 | 03-daily-tasks.md, 12-md-battle.md |
| `mirror/road_in_mir/select_event_effect_confirm.png` | default/share, default/zh_cn | [tasks/mirror/mirror.py:315](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L315) | 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/setting_assets.png` | default/share | [tasks/base/back_init_menu.py:73](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L73), [tasks/mirror/get_floor.py:37](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/get_floor.py#L37), ...及 3 項 | 03-daily-tasks.md |
| `mirror/road_in_mir/shop.png` | default/share | [tasks/mirror/search_road.py:116](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L116) | — |
| `mirror/road_in_mir/to_window_assets.png` | dark/share, default/share | [tasks/base/back_init_menu.py:70](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L70), [tasks/mirror/get_floor.py:44](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/get_floor.py#L44), ...及 2 項 | 03-daily-tasks.md |
| `mirror/road_in_mir/towindow&forfeit_confirm_assets.png` | dark/share, default/share | [tasks/base/back_init_menu.py:68](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L68), [tasks/mirror/mirror.py:248](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L248), ...及 2 項 | 03-daily-tasks.md, 10-mirror-dungeon-overview.md |
| `mirror/road_in_mir/up.png` | default/share | — | — |
| `mirror/road_to_mir/activate_gift_search_off_assets.png` | default/share | [tasks/mirror/mirror.py:488](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L488), [tasks/mirror/mirror.py:930](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L930) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/activate_gift_search_on_assets.png` | default/share | [tasks/mirror/mirror.py:487](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L487), [tasks/mirror/mirror.py:890](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L890) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/bleed_gift_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:807](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L807) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/blunt_gift_1_assets.png` | default/share | [tasks/mirror/mirror.py:902](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L902) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/blunt_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/burn_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/charge_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/dreaming_star/coins_assets.png` | default/share | [tasks/mirror/mirror.py:209](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L209), [tasks/mirror/mirror.py:427](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L427), ...及 2 項 | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/dreaming_star/convert_star_to_cost_assets.png` | default/share | [tasks/mirror/mirror.py:815](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L815) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/dreaming_star/dreaming_star_enter_assets.png` | dark/share, default/share | [tasks/mirror/mirror.py:850](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L850) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/dreaming_star/level_one_bonus_assets.png` | default/share | [tasks/mirror/mirror.py:833](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L833) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/dreaming_star/level_two_bonus_assets.png` | default/share | [tasks/mirror/mirror.py:836](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L836) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/dreaming_star/no_convert_star_to_cost_assets.png` | default/share | [tasks/mirror/mirror.py:811](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L811) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/dreaming_star/select_star_confirm_assets.png` | default/share | [tasks/mirror/mirror.py:820](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L820) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/enter_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:183](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L183), [tasks/mirror/mirror.py:481](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L481) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/enter_mirror_assets.png` | dark/share, default/share | [tasks/mirror/mirror.py:172](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L172) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/enter_mirror_confirm.png` | dark/share, default/share | [tasks/mirror/mirror.py:1093](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1093) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/infinity_mirror_bbox.png` | default/share | [tasks/mirror/mirror.py:174](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L174) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/infinity_mirror_enter_assets.png` | default/share | [tasks/mirror/mirror.py:182](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L182) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/level_confirm_assets.png` | dark/share, default/share | [tasks/mirror/mirror.py:1100](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1100) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/observe_ego_gift/Level_I.png` | default/share | — | — |
| `mirror/road_to_mir/observe_ego_gift/Level_II.png` | default/share | — | — |
| `mirror/road_to_mir/observe_ego_gift/Level_III.png` | default/share | — | — |
| `mirror/road_to_mir/observe_ego_gift/gift_box_bbox.png` | default/share | [tasks/mirror/mirror.py:994](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L994) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/observe_ego_gift/observe_bleed_assets.png` | default/share | [tasks/mirror/mirror.py:495](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L495), [tasks/mirror/mirror.py:893](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L893), ...及 1 項 | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/observe_ego_gift/observe_burn_assets.png` | default/share | [tasks/mirror/mirror.py:496](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L496), [tasks/mirror/mirror.py:894](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L894), ...及 1 項 | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/observe_ego_gift/reject_gift_bbox.png` | default/share | [tasks/mirror/mirror.py:1056](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1056) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/observe_ego_gift/select_gift_bbox.png` | default/share | [tasks/mirror/mirror.py:1044](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1044) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/pierce_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/poise_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/quick_start_assets.png` | default/share | [tasks/mirror/mirror.py:202](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L202) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/resume_assets.png` | dark/en, dark/zh_cn, default/en, default/zh_cn | [tasks/mirror/mirror.py:170](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L170) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/rupture_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/select_all_stars_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:830](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L830), [tasks/mirror/mirror.py:832](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L832), ...及 1 項 | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/select_init_ego_gifts_confirm_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:932](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L932) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/select_init_gift/bleed_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/bleed_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/bleed_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/blunt_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/blunt_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/blunt_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/burn_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/burn_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/burn_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/charge_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/charge_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/charge_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/pierce_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/pierce_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/pierce_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/poise_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/poise_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/poise_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/random_ego_gift.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/rupture_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/rupture_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/rupture_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/sinking_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/sinking_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/sinking_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/slash_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/slash_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/slash_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/tremor_ego_gift_1.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/tremor_ego_gift_2.png` | default/share | — | — |
| `mirror/road_to_mir/select_init_gift/tremor_ego_gift_3.png` | default/share | — | — |
| `mirror/road_to_mir/select_team_confirm_assets.png` | default/en, default/zh_cn | [tasks/mirror/mirror.py:1102](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1102), [tasks/teams/team_formation.py:292](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L292) | 10-mirror-dungeon-overview.md, 11-md-team-formation.md |
| `mirror/road_to_mir/select_team_stars_assets.png` | default/share | [tasks/mirror/mirror.py:207](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L207), [tasks/mirror/mirror.py:356](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L356) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/sinking_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/slash_gift_1.png` | default/share | [tasks/mirror/mirror.py:898](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L898) | 10-mirror-dungeon-overview.md |
| `mirror/road_to_mir/slash_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/road_to_mir/tremor_gift_assets.png` | default/en, default/zh_cn | — | — |
| `mirror/shop/ID_skill_replace_0_purchased_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:1272](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1272), [tasks/mirror/in_shop.py:1321](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1321), ...及 1 項 | 13-md-ego-gifts.md |
| `mirror/shop/ID_skill_replace_1_purchased_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:1312](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1312) | 13-md-ego-gifts.md |
| `mirror/shop/ID_skill_replace_2_purchased_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:1316](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1316) | 13-md-ego-gifts.md |
| `mirror/shop/ID_skill_replace_search_return_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:1294](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1294) | 13-md-ego-gifts.md |
| `mirror/shop/ID_skill_search_assets.png` | default/share | [tasks/mirror/in_shop.py:1322](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1322) | 13-md-ego-gifts.md |
| `mirror/shop/enhance_and_fuse_and_sell_confirm_assets.png` | default/share | [tasks/mirror/in_shop.py:495](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L495), [tasks/mirror/in_shop.py:654](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L654), ...及 3 項 | 13-md-ego-gifts.md |
| `mirror/shop/enhance_gifts/big_bleed.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_blunt.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_burn.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_charge.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_pierce.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_poise.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_rupture.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_sinking.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_slash.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/big_tremor.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/bleed.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/blunt.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/burn.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/charge.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/pierce.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/poise.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/rupture.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_bleed.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_blunt.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_burn.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_charge.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_pierce.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_poise.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_rupture.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_sinking.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_slash.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/shop_tremor.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/sinking.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/slash.png` | default/share | — | — |
| `mirror/shop/enhance_gifts/tremor.png` | default/share | — | — |
| `mirror/shop/enhance_gifts_assets.png` | default/share | [tasks/mirror/in_shop.py:1054](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1054) | 13-md-ego-gifts.md |
| `mirror/shop/fuse_90%_assets.png` | default/share | [tasks/mirror/in_shop.py:451](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L451), [tasks/mirror/in_shop.py:458](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L458), ...及 1 項 | 13-md-ego-gifts.md |
| `mirror/shop/fuse_ego_gift_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:509](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L509), [tasks/mirror/in_shop.py:659](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L659), ...及 1 項 | 13-md-ego-gifts.md |
| `mirror/shop/fuse_gift_assets.png` | default/share | [tasks/mirror/in_shop.py:917](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L917) | 13-md-ego-gifts.md |
| `mirror/shop/fuse_gift_confirm_assets.png` | default/share | [tasks/mirror/in_shop.py:894](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L894), [tasks/mirror/in_shop.py:901](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L901) | 13-md-ego-gifts.md |
| `mirror/shop/fuse_label.png` | default/share | [tasks/mirror/in_shop.py:394](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L394), [tasks/mirror/in_shop.py:702](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L702) | 13-md-ego-gifts.md |
| `mirror/shop/fuse_to_select_keyword_assets.png` | default/share | [tasks/mirror/in_shop.py:904](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L904) | 13-md-ego-gifts.md |
| `mirror/shop/fuse_use_starlight_assets.png` | default/share | [tasks/mirror/in_shop.py:485](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L485) | 13-md-ego-gifts.md |
| `mirror/shop/fuse_use_starlight_confirm_assets.png` | default/share | [tasks/mirror/in_shop.py:488](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L488) | 13-md-ego-gifts.md |
| `mirror/shop/fusion_level_IV_gift_assets.png` | default/share | [tasks/mirror/in_shop.py:460](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L460), [tasks/mirror/in_shop.py:622](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L622) | 13-md-ego-gifts.md |
| `mirror/shop/fusion_result/bleed_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/bleed_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/bleed_3.png` | default/share | — | — |
| `mirror/shop/fusion_result/bleed_hard_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/bleed_hard_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/bleed_hard_3.png` | default/share | — | — |
| `mirror/shop/fusion_result/burn_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/burn_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/burn_hard_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/burn_hard_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/charge_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/charge_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/charge_hard_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/poise_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/poise_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/poise_3.png` | default/share | — | — |
| `mirror/shop/fusion_result/poise_4.png` | default/share | — | — |
| `mirror/shop/fusion_result/poise_hard_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/rupture_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/rupture_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/rupture_hard_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/rupture_hard_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/rupture_hard_3.png` | default/share | — | — |
| `mirror/shop/fusion_result/sinking_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/sinking_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/sinking_3.png` | default/share | — | — |
| `mirror/shop/fusion_result/sinking_hard_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/tremor_1.png` | default/share | — | — |
| `mirror/shop/fusion_result/tremor_2.png` | default/share | — | — |
| `mirror/shop/fusion_result/tremor_3.png` | default/share | — | — |
| `mirror/shop/fusion_result/tremor_hard_1.png` | default/share | — | — |
| `mirror/shop/gifts_list_block.png` | default/share | [tasks/mirror/in_shop.py:671](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L671), [tasks/mirror/in_shop.py:699](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L699), ...及 4 項 | 13-md-ego-gifts.md |
| `mirror/shop/heal_sinner/heal_all_sinner_assets.png` | default/share | [tasks/mirror/in_shop.py:990](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L990) | 13-md-ego-gifts.md |
| `mirror/shop/heal_sinner/heal_sinner_assets.png` | default/share | [tasks/mirror/in_shop.py:1003](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1003) | 13-md-ego-gifts.md |
| `mirror/shop/heal_sinner/heal_sinner_return_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:982](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L982), [tasks/mirror/in_shop.py:985](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L985), ...及 2 項 | 13-md-ego-gifts.md |
| `mirror/shop/keyword/keyword_bleed.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_blunt.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_burn.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_charge.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_pierce.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_poise.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_rupture.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_sinking.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_slash.png` | default/share | — | — |
| `mirror/shop/keyword/keyword_tremor.png` | default/share | — | — |
| `mirror/shop/leave_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:1427](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1427) | 13-md-ego-gifts.md |
| `mirror/shop/leave_shop_confirm_assets.png` | dark/share, default/share | [tasks/mirror/in_shop.py:1425](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1425), [tasks/mirror/mirror.py:1049](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1049), ...及 1 項 | 10-mirror-dungeon-overview.md, 13-md-ego-gifts.md |
| `mirror/shop/level_III_to_buy.png` | default/share | [tasks/mirror/in_shop.py:203](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L203) | 13-md-ego-gifts.md |
| `mirror/shop/level_IV_gifts/bleed_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/blunt_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/burn_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/charge_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/lunar_memory.png` | default/share | [tasks/mirror/in_shop.py:418](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L418) | 13-md-ego-gifts.md |
| `mirror/shop/level_IV_gifts/pierce_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/poise_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/rupture_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/sinking_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/slash_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_gifts/tremor_level_IV.png` | default/share | — | — |
| `mirror/shop/level_IV_to_buy.png` | default/share | [tasks/mirror/in_shop.py:187](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L187) | 13-md-ego-gifts.md |
| `mirror/shop/must_be_abandoned/leave0_fragment1.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave0_fragment2.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave0_fragment3.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave0_fragment4.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave0_fragment5.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave0_fragment6.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave0_fragment7.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave1_1.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave1_grand_welcome.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave1_vestige3.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave2_child_within_a_flask.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave2_coffee_and_cranes.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave2_gloden_urn.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave2_oracle.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave2_vestige2.png` | default/share | [tasks/mirror/in_shop.py:420](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L420) | 13-md-ego-gifts.md |
| `mirror/shop/must_be_abandoned/leave2_white_gossypium.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave3_blue_zippo_lighter.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave3_perversion.png` | default/share | — | — |
| `mirror/shop/must_be_abandoned/leave3_vestige.png` | default/share | [tasks/mirror/in_shop.py:421](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L421) | 13-md-ego-gifts.md |
| `mirror/shop/must_purchase/carmilla.png` | default/share | — | — |
| `mirror/shop/must_purchase/homeward.png` | default/share | — | — |
| `mirror/shop/must_purchase/lithograph.png` | default/share | — | — |
| `mirror/shop/must_purchase/phlebotomy_pack.png` | default/share | — | — |
| `mirror/shop/must_purchase/piece_of_relationship.png` | default/share | — | — |
| `mirror/shop/my_money_bbox.png` | default/share | [tasks/mirror/in_shop.py:1505](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1505) | 13-md-ego-gifts.md |
| `mirror/shop/my_money_heal_bbox.png` | default/share | [tasks/mirror/in_shop.py:1503](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1503) | 13-md-ego-gifts.md |
| `mirror/shop/power_up_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:81](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L81) | 13-md-ego-gifts.md |
| `mirror/shop/power_up_confirm_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:84](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L84), [tasks/mirror/in_shop.py:89](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L89) | 13-md-ego-gifts.md |
| `mirror/shop/purchase_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:160](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L160), [tasks/mirror/in_shop.py:191](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L191), ...及 3 項 | 13-md-ego-gifts.md |
| `mirror/shop/refresh_assets.png` | default/share | [tasks/mirror/in_shop.py:336](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L336) | 13-md-ego-gifts.md |
| `mirror/shop/refresh_keyword_assets.png` | default/share | [tasks/mirror/in_shop.py:299](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L299) | 13-md-ego-gifts.md |
| `mirror/shop/refresh_keyword_confirm_assets.png` | default/share | [tasks/mirror/in_shop.py:306](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L306), [tasks/mirror/in_shop.py:309](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L309), ...及 1 項 | 13-md-ego-gifts.md |
| `mirror/shop/return_assets.png` | default/en | [tasks/mirror/in_shop.py:1355](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1355) | 13-md-ego-gifts.md |
| `mirror/shop/sell_gift_assets.png` | default/share | [tasks/mirror/in_shop.py:817](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L817) | 13-md-ego-gifts.md |
| `mirror/shop/sell_gift_confirm_assets.png` | dark/share, default/share | [tasks/mirror/in_shop.py:820](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L820) | 13-md-ego-gifts.md |
| `mirror/shop/shop_coins_assets.png` | default/share | [tasks/mirror/in_shop.py:111](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L111), [tasks/mirror/in_shop.py:115](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L115), ...及 4 項 | 13-md-ego-gifts.md |
| `mirror/shop/skill_replacement_assets.png` | default/share | [tasks/mirror/in_shop.py:1330](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1330) | 13-md-ego-gifts.md |
| `mirror/shop/skill_replacement_coins.png` | default/share | [tasks/mirror/in_shop.py:1225](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1225), [tasks/mirror/in_shop.py:1279](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1279) | 13-md-ego-gifts.md |
| `mirror/shop/skill_replacement_confirm_assets.png` | default/share | [tasks/mirror/in_shop.py:1235](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1235), [tasks/mirror/in_shop.py:1236](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1236), ...及 2 項 | 13-md-ego-gifts.md |
| `mirror/shop/sort_button_assets.png` | default/share | [tasks/mirror/in_shop.py:1050](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1050) | 13-md-ego-gifts.md |
| `mirror/shop/super_shop_assets.png` | default/en, default/zh_cn | [tasks/mirror/in_shop.py:1307](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1307) | 13-md-ego-gifts.md |
| `mirror/shop/super_shop_skill_replacement_1_assets.png` | default/share | [tasks/mirror/in_shop.py:1313](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1313) | 13-md-ego-gifts.md |
| `mirror/shop/super_shop_skill_replacement_2_assets.png` | default/share | [tasks/mirror/in_shop.py:1317](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L1317) | 13-md-ego-gifts.md |
| `mirror/theme_pack/feature_theme_pack_assets.png` | default/share | [tasks/mirror/mirror.py:212](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L212), [tasks/mirror/mirror.py:283](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L283), ...及 1 項 | 10-mirror-dungeon-overview.md |
| `mirror/theme_pack/hard_assets.png` | default/share | [tasks/mirror/select_theme_pack.py:14](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/select_theme_pack.py#L14) | 14-md-navigation.md |
| `mirror/theme_pack/normal_assets.png` | default/share | [tasks/mirror/select_theme_pack.py:12](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/select_theme_pack.py#L12) | 14-md-navigation.md |
| `mirror/theme_pack/refresh_assets.png` | default/share | [tasks/mirror/select_theme_pack.py:129](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/select_theme_pack.py#L129) | 14-md-navigation.md |
| `mirror/theme_pack/theme_pack_features.png` | default/share | [tasks/mirror/select_theme_pack.py:70](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/select_theme_pack.py#L70), [tasks/mirror/select_theme_pack.py:83](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/select_theme_pack.py#L83) | 14-md-navigation.md |
| `mirror/theme_pack/theme_pack_setting_assets.png` | default/share | [tasks/mirror/mirror.py:288](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L288) | 10-mirror-dungeon-overview.md |

### PASS (3 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `pass/pass_coin.png` | default/share | [tasks/daily/get_prize.py:20](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L20), [tasks/daily/get_prize.py:57](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L57) | 03-daily-tasks.md |
| `pass/pass_missions_assets.png` | default/en, default/zh_cn | [tasks/daily/get_prize.py:25](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L25) | 03-daily-tasks.md |
| `pass/weekly_assets.png` | default/en, default/zh_cn | [tasks/daily/get_prize.py:52](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/get_prize.py#L52) | 03-daily-tasks.md |

### SCENES (3 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `scenes/story_meun_assets.png` | default/share | [tasks/base/back_init_menu.py:84](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L84) | 03-daily-tasks.md |
| `scenes/story_skip_assets.png` | default/share | [tasks/base/back_init_menu.py:82](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L82) | 03-daily-tasks.md |
| `scenes/story_skip_confirm_assets.png` | dark/share, default/share | [tasks/base/back_init_menu.py:80](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/back_init_menu.py#L80) | 03-daily-tasks.md |

### TEAMS (11 項)

| 相對路徑 | 變體 | 程式引用 | 對應報告 |
|---------|------|---------|--------|
| `teams/10_sinner_live_assets.png` | default/share | [tasks/mirror/mirror.py:386](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L386) | 10-mirror-dungeon-overview.md |
| `teams/11_sinner_live_assets.png` | default/share | [tasks/mirror/mirror.py:385](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L385) | 10-mirror-dungeon-overview.md |
| `teams/12_sinner_live_assets.png` | default/share | [tasks/mirror/mirror.py:384](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L384) | 10-mirror-dungeon-overview.md |
| `teams/clear_selection_confirm_assets.png` | dark/share, default/share | [tasks/teams/team_formation.py:39](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L39), [tasks/teams/team_formation.py:46](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L46) | 11-md-team-formation.md |
| `teams/identify_assets.png` | default/share | [tasks/daily/luxcavation.py:55](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L55), [tasks/daily/luxcavation.py:83](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L83), ...及 8 項 | 03-daily-tasks.md |
| `teams/load_team_code_button_assets.png` | default/en, default/zh_cn | [tasks/teams/team_formation.py:308](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L308) | 11-md-team-formation.md |
| `teams/none_sinner_assets.png` | default/share | [tasks/mirror/mirror.py:376](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L376) | 10-mirror-dungeon-overview.md |
| `teams/selected.png` | default/share | [tasks/teams/team_formation.py:234](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L234) | 11-md-team-formation.md |
| `teams/team_code_assets.png` | dark/share, default/share | [tasks/teams/team_formation.py:304](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L304), [tasks/teams/team_formation.py:330](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L330) | 11-md-team-formation.md |
| `teams/team_code_cancel_button_assets.png` | dark/share, default/share | [tasks/teams/team_formation.py:312](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L312), [tasks/teams/team_formation.py:333](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L333) | 11-md-team-formation.md |
| `teams/team_code_confirm_button_assets.png` | dark/share, default/share | [tasks/teams/team_formation.py:324](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/teams/team_formation.py#L324) | 11-md-team-formation.md |

---

## 無程式引用的資源 (Unreferenced Assets)

> **協調者校正（人工複核）**：下方 171 項是「字面字串搜尋找不到」的清單，並非真正無人使用。複核後分為四類：
>
> | 類別 | 目錄 / 檔案 | 實際用法 |
> |---|---|---|
> | f-string 動態組路徑（**有在用**） | `enkephalin/lunacy_spend_{26,52,78}_assets.png` | [tasks/base/make_enkephalin_module.py:L201](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/base/make_enkephalin_module.py#L201) |
> | 同上 | `mirror/get_reward_card/*` | [tasks/mirror/reward_card.py:L94](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/reward_card.py#L94) |
> | 同上 | `mirror/road_in_mir/acquire_ego_gift/{system}.png` | [tasks/mirror/mirror.py:L1451](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1451)、[tasks/mirror/mirror.py:L1463](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1463) |
> | 同上 | `mirror/road_in_mir/{up,mid,down}.png` | [tasks/mirror/search_road.py:L527](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/search_road.py#L527) |
> | 同上 | `mirror/road_to_mir/{system}_gift_assets.png`、`select_init_gift/*` | [tasks/mirror/mirror.py:L908-L926](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L908-L926) |
> | 同上 | `mirror/road_to_mir/observe_ego_gift/Level_*.png` | [tasks/mirror/mirror.py:L1022](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1022)、[tasks/mirror/mirror.py:L1033](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/mirror.py#L1033) |
> | 同上 | `mirror/shop/enhance_gifts/*`、`shop/keyword/*`、`shop/level_IV_gifts/*` | [tasks/mirror/in_shop.py:L224](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L224)、[tasks/mirror/in_shop.py:L302](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L302)、[tasks/mirror/in_shop.py:L364](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L364) 等 |
> | **只靠壞掉的目錄遍歷（執行時實際未載入）** | `mirror/shop/must_purchase/*`、`must_be_abandoned/*`（`leave2_vestige2`、`leave3_vestige` 除外，見 [tasks/mirror/in_shop.py:L417-L422](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py#L417-L422)）、`fusion_result/*` | [tasks/mirror/__init__.py:L1-L31](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/__init__.py#L1-L31) 遍歷 `./assets/images/share/mirror/shop/...`，但此路徑在 repo 與打包產物中都不存在（`assets/images/` 下只有 `default/`、`dark/`；[scripts/build.py:L38](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/scripts/build.py#L38) 原樣複製 `assets`），`os.walk` 對不存在目錄靜默回傳空，三份清單為空。詳見 [13 §6.10](13-md-ego-gifts.md#610-tasksmirror__init__py-路徑問題三份清單在-runtime-為空確認) |
> | **真正無程式引用** | `mirror/road_in_mir/clear_floor.png`、`get_floor_bbox.png`、`not_passed_floor.png`、`luxcavation/thread_enter_assets.png` | 全 repo `rg` 無結果（樓層辨識改用紅色 CLEAR 色塊計數，見 [10](10-mirror-dungeon-overview.md)；紐本改用 `thread_enter_up80_assets.png`，[tasks/daily/luxcavation.py:L154-L167](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/daily/luxcavation.py#L154-L167)） |

以下為原始字面搜尋結果（保留供對照）：

#### enkephalin (3 項)

- `enkephalin/lunacy_spend_26_assets.png` (default/share)
- `enkephalin/lunacy_spend_52_assets.png` (default/share)
- `enkephalin/lunacy_spend_78_assets.png` (default/share)

#### luxcavation (1 項)

- `luxcavation/thread_enter_assets.png` (dark/share, default/share)

#### mirror (167 項)

- `mirror/get_reward_card/gain_cost.png` (default/share)
- `mirror/get_reward_card/gain_cost_and_ego.png` (default/share)
- `mirror/get_reward_card/gain_ego.png` (default/share)
- `mirror/get_reward_card/gain_ego_resource.png` (default/share)
- `mirror/get_reward_card/gain_starlight.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/bleed.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/blunt.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/burn.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/charge.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/pierce.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/poise.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/rupture.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/sinking.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/slash.png` (default/share)
- `mirror/road_in_mir/acquire_ego_gift/tremor.png` (default/share)
- `mirror/road_in_mir/clear_floor.png` (default/share)
- `mirror/road_in_mir/down.png` (default/share)
- `mirror/road_in_mir/get_floor_bbox.png` (default/share)
- `mirror/road_in_mir/mid.png` (default/share)
- `mirror/road_in_mir/not_passed_floor.png` (dark/share, default/share)
- `mirror/road_in_mir/up.png` (default/share)
- `mirror/road_to_mir/blunt_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/burn_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/charge_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/observe_ego_gift/Level_I.png` (default/share)
- `mirror/road_to_mir/observe_ego_gift/Level_II.png` (default/share)
- `mirror/road_to_mir/observe_ego_gift/Level_III.png` (default/share)
- `mirror/road_to_mir/pierce_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/poise_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/rupture_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/select_init_gift/bleed_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/bleed_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/bleed_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/blunt_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/blunt_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/blunt_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/burn_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/burn_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/burn_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/charge_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/charge_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/charge_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/pierce_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/pierce_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/pierce_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/poise_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/poise_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/poise_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/random_ego_gift.png` (default/share)
- `mirror/road_to_mir/select_init_gift/rupture_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/rupture_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/rupture_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/sinking_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/sinking_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/sinking_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/slash_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/slash_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/slash_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/select_init_gift/tremor_ego_gift_1.png` (default/share)
- `mirror/road_to_mir/select_init_gift/tremor_ego_gift_2.png` (default/share)
- `mirror/road_to_mir/select_init_gift/tremor_ego_gift_3.png` (default/share)
- `mirror/road_to_mir/sinking_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/slash_gift_assets.png` (default/en, default/zh_cn)
- `mirror/road_to_mir/tremor_gift_assets.png` (default/en, default/zh_cn)
- `mirror/shop/enhance_gifts/big_bleed.png` (default/share)
- `mirror/shop/enhance_gifts/big_blunt.png` (default/share)
- `mirror/shop/enhance_gifts/big_burn.png` (default/share)
- `mirror/shop/enhance_gifts/big_charge.png` (default/share)
- `mirror/shop/enhance_gifts/big_pierce.png` (default/share)
- `mirror/shop/enhance_gifts/big_poise.png` (default/share)
- `mirror/shop/enhance_gifts/big_rupture.png` (default/share)
- `mirror/shop/enhance_gifts/big_sinking.png` (default/share)
- `mirror/shop/enhance_gifts/big_slash.png` (default/share)
- `mirror/shop/enhance_gifts/big_tremor.png` (default/share)
- `mirror/shop/enhance_gifts/bleed.png` (default/share)
- `mirror/shop/enhance_gifts/blunt.png` (default/share)
- `mirror/shop/enhance_gifts/burn.png` (default/share)
- `mirror/shop/enhance_gifts/charge.png` (default/share)
- `mirror/shop/enhance_gifts/pierce.png` (default/share)
- `mirror/shop/enhance_gifts/poise.png` (default/share)
- `mirror/shop/enhance_gifts/rupture.png` (default/share)
- `mirror/shop/enhance_gifts/shop_bleed.png` (default/share)
- `mirror/shop/enhance_gifts/shop_blunt.png` (default/share)
- `mirror/shop/enhance_gifts/shop_burn.png` (default/share)
- `mirror/shop/enhance_gifts/shop_charge.png` (default/share)
- `mirror/shop/enhance_gifts/shop_pierce.png` (default/share)
- `mirror/shop/enhance_gifts/shop_poise.png` (default/share)
- `mirror/shop/enhance_gifts/shop_rupture.png` (default/share)
- `mirror/shop/enhance_gifts/shop_sinking.png` (default/share)
- `mirror/shop/enhance_gifts/shop_slash.png` (default/share)
- `mirror/shop/enhance_gifts/shop_tremor.png` (default/share)
- `mirror/shop/enhance_gifts/sinking.png` (default/share)
- `mirror/shop/enhance_gifts/slash.png` (default/share)
- `mirror/shop/enhance_gifts/tremor.png` (default/share)
- `mirror/shop/fusion_result/bleed_1.png` (default/share)
- `mirror/shop/fusion_result/bleed_2.png` (default/share)
- `mirror/shop/fusion_result/bleed_3.png` (default/share)
- `mirror/shop/fusion_result/bleed_hard_1.png` (default/share)
- `mirror/shop/fusion_result/bleed_hard_2.png` (default/share)
- `mirror/shop/fusion_result/bleed_hard_3.png` (default/share)
- `mirror/shop/fusion_result/burn_1.png` (default/share)
- `mirror/shop/fusion_result/burn_2.png` (default/share)
- `mirror/shop/fusion_result/burn_hard_1.png` (default/share)
- `mirror/shop/fusion_result/burn_hard_2.png` (default/share)
- `mirror/shop/fusion_result/charge_1.png` (default/share)
- `mirror/shop/fusion_result/charge_2.png` (default/share)
- `mirror/shop/fusion_result/charge_hard_1.png` (default/share)
- `mirror/shop/fusion_result/poise_1.png` (default/share)
- `mirror/shop/fusion_result/poise_2.png` (default/share)
- `mirror/shop/fusion_result/poise_3.png` (default/share)
- `mirror/shop/fusion_result/poise_4.png` (default/share)
- `mirror/shop/fusion_result/poise_hard_1.png` (default/share)
- `mirror/shop/fusion_result/rupture_1.png` (default/share)
- `mirror/shop/fusion_result/rupture_2.png` (default/share)
- `mirror/shop/fusion_result/rupture_hard_1.png` (default/share)
- `mirror/shop/fusion_result/rupture_hard_2.png` (default/share)
- `mirror/shop/fusion_result/rupture_hard_3.png` (default/share)
- `mirror/shop/fusion_result/sinking_1.png` (default/share)
- `mirror/shop/fusion_result/sinking_2.png` (default/share)
- `mirror/shop/fusion_result/sinking_3.png` (default/share)
- `mirror/shop/fusion_result/sinking_hard_1.png` (default/share)
- `mirror/shop/fusion_result/tremor_1.png` (default/share)
- `mirror/shop/fusion_result/tremor_2.png` (default/share)
- `mirror/shop/fusion_result/tremor_3.png` (default/share)
- `mirror/shop/fusion_result/tremor_hard_1.png` (default/share)
- `mirror/shop/keyword/keyword_bleed.png` (default/share)
- `mirror/shop/keyword/keyword_blunt.png` (default/share)
- `mirror/shop/keyword/keyword_burn.png` (default/share)
- `mirror/shop/keyword/keyword_charge.png` (default/share)
- `mirror/shop/keyword/keyword_pierce.png` (default/share)
- `mirror/shop/keyword/keyword_poise.png` (default/share)
- `mirror/shop/keyword/keyword_rupture.png` (default/share)
- `mirror/shop/keyword/keyword_sinking.png` (default/share)
- `mirror/shop/keyword/keyword_slash.png` (default/share)
- `mirror/shop/keyword/keyword_tremor.png` (default/share)
- `mirror/shop/level_IV_gifts/bleed_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/blunt_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/burn_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/charge_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/pierce_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/poise_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/rupture_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/sinking_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/slash_level_IV.png` (default/share)
- `mirror/shop/level_IV_gifts/tremor_level_IV.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment1.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment2.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment3.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment4.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment5.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment6.png` (default/share)
- `mirror/shop/must_be_abandoned/leave0_fragment7.png` (default/share)
- `mirror/shop/must_be_abandoned/leave1_1.png` (default/share)
- `mirror/shop/must_be_abandoned/leave1_grand_welcome.png` (default/share)
- `mirror/shop/must_be_abandoned/leave1_vestige3.png` (default/share)
- `mirror/shop/must_be_abandoned/leave2_child_within_a_flask.png` (default/share)
- `mirror/shop/must_be_abandoned/leave2_coffee_and_cranes.png` (default/share)
- `mirror/shop/must_be_abandoned/leave2_gloden_urn.png` (default/share)
- `mirror/shop/must_be_abandoned/leave2_oracle.png` (default/share)
- `mirror/shop/must_be_abandoned/leave2_white_gossypium.png` (default/share)
- `mirror/shop/must_be_abandoned/leave3_blue_zippo_lighter.png` (default/share)
- `mirror/shop/must_be_abandoned/leave3_perversion.png` (default/share)
- `mirror/shop/must_purchase/carmilla.png` (default/share)
- `mirror/shop/must_purchase/homeward.png` (default/share)
- `mirror/shop/must_purchase/lithograph.png` (default/share)
- `mirror/shop/must_purchase/phlebotomy_pack.png` (default/share)
- `mirror/shop/must_purchase/piece_of_relationship.png` (default/share)

---

## 模型與配置 (Models and Configuration)

### 模型 (Models)

| 檔案 | 用途 |
|-----|-----|
| [`assets/model/best.onnx`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/model/best.onnx) | ONNX 格式的神經網路模型，用於圖像識別 |

### 配置文件 (Configuration Files)

| 檔案 | 用途 |
|-----|-----|
| [`assets/config/config.example.yaml`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/config/config.example.yaml) | 應用程式配置範例 |
| [`assets/config/default_rapidocr.yaml`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/config/default_rapidocr.yaml) | RapidOCR 預設配置 |
| [`assets/config/theme_pack_list.example.yaml`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/config/theme_pack_list.example.yaml) | 主題包配置範例 |
| [`assets/config/version.txt`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/config/version.txt) | 版本資訊 |

### 應用資源 (Application Assets)

| 子目錄 | 內容 | 計數 |
|-------|------|------|
| [`assets/app/sinner/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/app/sinner) | 12 名罪人角色圖片 + UI 元件 (Logo, Sinner.png, ID_Photo_3.png 等) | 39 檔 |
| [`assets/app/status_effects/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/app/status_effects) | 出血、鈍性、燃燒、charge 等 11 種戰鬥狀態圖示 | 11 檔 |
| [`assets/app/svgs/icons/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/app/svgs) | SVG 格式圖示 | 多個 |
| [`assets/app/theme_packs/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/app/theme_packs) | GUI 主題包 | 多個 |
| [`assets/app/fonts/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/assets/app/fonts) | ChineseFont.ttf (漢字字體) | 1 檔 |

---

## 相關文檔與工具 (References and Tools)

- **主要說明**: [README.md](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/README.md)
- **路徑管理**: [`utils/path_manager.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/utils/path_manager.py) - 處理主題/語言路徑優先級
- **圖片工具**: [`utils/image_utils.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/utils/image_utils.py) - 圖片加載、匹配、模板識別
- **自動化框架**: [`module/automation/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/automation) - 自動化工作流引擎
- **遊戲交互**: [`module/game_and_screen/`](https://github.com/KIYI671/AhabAssistantLimbusCompany/tree/b0f439321987f5f7b126ebbc424f6ef144c1bff0/module/game_and_screen) - 螢幕截取與點擊控制

---

## 附註 (Notes)

- 資源變體未完全對稱: 許多資源僅存在於 `default/share` 或特定語言版本，反映遊戲 UI 的實際多語言支援狀況。
- 無引用的資源可能透過以下方式使用:
  - **動態路徑**: `f"{base}/{system}.png"` 形式構建，見 [`tasks/mirror/in_shop.py`](https://github.com/KIYI671/AhabAssistantLimbusCompany/blob/b0f439321987f5f7b126ebbc424f6ef144c1bff0/tasks/mirror/in_shop.py) 第 224、302、364 行
  - **目錄遍歷**: `os.walk('./assets/images/share/mirror/shop/...')` —— 注意此路徑不存在，遍歷結果為空（見上方校正表）
  - **未實裝**: 部分資源預留以供未來功能擴展
