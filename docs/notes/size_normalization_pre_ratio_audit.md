# Size Normalization Pre-Ratio Audit

> **目的**：紀錄 Step 9 size normalization 重構**動工前**所有 size-sensitive 參數的當前 pixel 值、來源假設、換算 ratio、設計依據。
> 之後 ratio 化 patch 落地後，本文件成為設計史，可追溯每個 ratio 從哪個 pixel 值與假設尺寸推導。

---

## 文件元資料

| 項目 | 內容 |
|---|---|
| 版本 | 0.4 |
| 最後校對 | 2026-05-23 |
| 校對對象 | `algorithm/` `config/` 內所有 size-sensitive 預設值 |
| 狀態 | snapshot（含 ratio 化進度欄；隨 Patch 10A-10C 推進） |
| 過期條件 | 任一參數預設值 / 名稱 / 位置變動 → 更新本文件 + 章末變更紀錄 |

---

## §1 假設基準尺寸

所有 ratio 換算以下列 single-frame DICOM 標準尺寸為基準：

```
image_width  = 1500   (M-mode time axis)
image_height = 955    (M-mode vertical)
image_area   = 1,432,500
```

> 此基準來源：用戶實務經驗（醫療設備 DICOM M-mode 主流輸出）。

> **Multi-frame 不在本表適用範圍**（multi-frame stitching window 寬度概念不同於 image_width；見 §6）。

---

## §2 未 ratio 化參數清單

### §2.1 y 軸相關

| 參數 | 當前值 | 假設 | 換算 ratio | Config / 設計來源 | 狀態 |
|---|---|---|---|---|---|
| `filter_top_rows` | 100 | h=955 | 100/955 ≈ **0.1047** | `DiaphragmDetectionConfig` / patch_code 原 main 的 `filter_100`；最上面標尺雜訊 | ✅ Patch 10A → `filter_top_ratio` |
| `fallback_region_top` | 200 | h=955 | 200/955 ≈ **0.2094** | `DiaphragmDetectionConfig` / curve_fit 找不到 best 時的 default top；經驗值 | ✅ Patch 10A → `fallback_region_top_ratio` |
| `jump_threshold` | 120 | h=955 | 120/955 ≈ **0.1257** | `MotionCurveConfig` / 相鄰 x 的 y 跳躍判斷斷點；原 `stable_peak` 寫死 | ✅ Patch 10A → `jump_threshold_ratio` |
| `fix_search_window` | 50 | h=955 | 50/955 ≈ **0.0524** | `MotionCurveConfig` / 補點搜尋窗（前一點 y - 50 開始 argmax） | ✅ Patch 10A → `fix_search_window_ratio` |

### §2.2 x 軸相關

| 參數 | 當前值 | 假設 | 換算 ratio | Config / 設計來源 | 狀態 |
|---|---|---|---|---|---|
| `midline_min_distance` | 100 | w=1500 | 100/1500 ≈ **0.0667** | `ExcursionConfig` / `find_midline` 相鄰交點過濾 | ✅ Patch 10B → `midline_min_distance_ratio` |

### §2.3 Area 相關

| 參數 | 當前值 | 假設 | 換算 ratio | Config / 設計來源 | 狀態 |
|---|---|---|---|---|---|
| `detect_area` | 20000 | area=1432500 | 20000/1432500 ≈ **0.01396** | `DiaphragmDetectionConfig` / `algo_segmentation` 連通元件面積閾值 | ✅ Patch 10C → `detect_area_ratio` |
| `min_use_segment_area` | 1000 | area=1432500 | 1000/1432500 ≈ **0.000698** | `DiaphragmDetectionConfig` / use_segment fallback 過濾微小切割 | ✅ Patch 10C → `min_use_segment_area_ratio` |
| `area_ratio` numerator | 10000 | area=1432500 | 10000/1432500 ≈ **0.00698** | `DiaphragmDetectionConfig` / candidate 面積占整圖比例門檻（分母已 ratio 化，分子仍 hardcode） | ✅ Patch 10C（註解清理，表達式與行為不變） |

### §2.4 Curve length 相關

| 參數 | 當前值 | 假設 | 換算 ratio | Config / 設計來源 | 狀態 |
|---|---|---|---|---|---|
| `prune_branch_max_length` | 100 | length-based（非 image dim） | n/a | `DiaphragmDetectionConfig` / `curve_fit` 內 skeleton 短分支修剪上限；長度單位與 image 尺寸非直接耦合 | 暫不動 |

---

## §3 已 ratio 化（對照組）

新加 size-sensitive 參數時請對齊以下風格：

| 參數 | 公式 | 當前 ratio | Config |
|---|---|---|---|
| `reserve_ratio` | `image_height × ratio` | 0.052 (= 50/955) | `RoiBandConfig` |
| `peak_min_distance_ratio` | `image_width × ratio` | 0.0333 (= 50/1500) | `ExcursionConfig` |
| `area_ratio` (denominator) | `area / image_area > ratio` | 0.00698 (= 10000/955·1500) | `DiaphragmDetectionConfig`（分母已 ratio，分子 numerator 仍 hardcode；見 §2.3） |

---

## §4 不需 ratio 化（與 size 無關）

不可誤改成 ratio：

| 參數 | 當前值 | 性質 |
|---|---|---|
| `use_segment_background_px` | 38 | intensity threshold |
| `peak_prominence` | 10 | intensity prominence |
| `enhance_blur_kernel` | 5 | morphological kernel（與 size 關聯弱） |
| `aspect_ratio_threshold` | 4.0 / 6.0 | ratio 本身 |
| `wavelet_level_trough` / `wavelet_level_crest` | 3 | wavelet decomposition level |
| `excursion_rule_start_range` | 1 | sequence index |
| `excursion_rule_end_range` | 0 | sequence index |
| `enhance_num_segments` | 1 | segment count |

---

## §5 後續 ratio 化建議

### 轉換策略

| 參數類 | 公式 | ratio 預設取自 §2 換算 |
|---|---|---|
| y 軸相關 | `int(image_height × ratio)` | 見 §2.1 |
| x 軸相關 | `int(image_width × ratio)` | 見 §2.2 |
| Area 相關 | `int(image_area × ratio)` 或維持 `area / image_area > ratio` | 見 §2.3 |
| Curve length | 暫不動（長度與 image dim 關係模糊） | 視未來情境決定 |

### 命名慣例

- pixel 絕對值參數：保留原名 + 加 deprecation 註解（如過渡需要）
- 新增 ratio 參數：`<原名>_ratio`（例如 `filter_top_rows` → 過渡保留並新增 `filter_top_rows_ratio`，最終移除舊欄位）
- 或直接重新命名：`filter_top_ratio = 0.1047`（更精簡）— 動 patch 時用 AskUserQuestion 收斂

### 與 Multi-frame 的互動

進 Multi-frame Mode 1（Global Window 拼接）前，須確認本表 ratio 對 multi-frame stitching 結果同樣適用（高度方向通常 OK；寬度方向因 stitching window ≠ image_width 而需另行設計）。

---

## §6 Multi-frame 適配備註

本表 ratio 假設 **input 為 single-frame DICOM**。

Multi-frame 的尺寸概念差異：
- single-frame 寬度 = M-mode time axis 取樣（pixel 與時間關聯）
- multi-frame stitching 寬度 = frame-shift 累積（pixel 與物理位移關聯）

直接套用本表 `image_width ratio` 到 multi-frame 會混淆語意。
Multi-frame 的 size handling 屬 **Step 9 Phase 2** 範圍（見 PROGRESS.md），本文件不涵蓋。

---

## §7 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-23 | 0.1 | 初版建立 | Step 9 Phase 0 — 動工前快照 |
| 2026-05-23 | 0.2 | §2 各表加「狀態」欄；§2.1 四個 y 軸參數標記 `✅ Patch 10A` | Step 9 ratio 化第一輪（y 軸） |
| 2026-05-23 | 0.3 | §2.2 `midline_min_distance` 標 `✅ Patch 10B` | Step 9 ratio 化第二輪（x 軸） |
| 2026-05-23 | 0.4 | §2.3 三個 area 參數標 `✅ Patch 10C` | Step 9 ratio 化第三輪（area） |
