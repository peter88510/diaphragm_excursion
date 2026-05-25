# pipeline.md — Per-frame Processing Flow

> Per-frame pipeline 每階段的 input / output / config 對照與主要動作。
> 跨層架構與設計決策見 [`ARCHITECTURE.md`](../ARCHITECTURE.md)。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 接手工程師、AI agent、查詢資料流 |

---

## §1 Pipeline 總覽

```
image_path
   │
   ▼ §2 input
FrameSequence (N, H, W)
   │
   ▼ §2 dicom_crop
FrameSequence (cropped)
   │
   ▼ per-frame loop
   │
   │   ┌─────────────────────────────────────────────────────┐
   │   │                                                     │
   │   ▼ §3 segmentation                                     │
   │   seg_mask (uint8 H×W)                                  │
   │   │                                                     │
   │   ▼ §4 detection pass1 (with seg)                       │
   │   DetectionResult                                       │
   │   │                                                     │
   │   ▼ §5.1 y_band 擴張                                    │
   │   y_band (y_min, y_max)                                 │
   │   │                                                     │
   │   ▼ §5.2 enhanced_search (pass2)                        │
   │   RoiSearchResult                                       │
   │   │                                                     │
   │   ▼ §5.3 select_target                                  │
   │   TargetSelection (含 diaphragm_mask)                   │
   │   │                                                     │
   │   ▼ §6 motion_curve                                     │
   │   MotionCurveResult                                     │
   │   │                                                     │
   │   ▼ §7.1 brightness_way                                 │
   │   ExcursionResult                                       │
   │   │                                                     │
   │   ▼ §7.2 compute_peak_info × batch                      │
   │   List[PeakInfo]                                        │
   │   │                                                     │
   │   ▼ aggregate                                           │
   │   FrameResult                                           │
   │   │                                                     │
   │   ▼ §9 PipelineVisualizer.render_frame                  │
   │   (cfg disabled 時零 I/O)                               │
   │                                                         │
   └─────────────────────────────────────────────────────────┘
```

Multi-frame dispatch（§8）決定走 per-frame loop（LEGACY，default）或 keyframe-only（GLOBAL_WINDOW，Step 10 進行中）。

---

## §2 Input 階段

| 維度 | 內容 |
|---|---|
| **入口** | `input.load(image_path)` |
| **輸入** | `str` 檔案 / 資料夾路徑 |
| **輸出** | `FrameSequence`（`frames` shape 永遠 `(N, H, W)` 或 `(N, H, W, 3)`） |
| **後處理** | `input.apply_dicom_crop(seq) → FrameSequence (cropped)` |
| **依賴 config** | 無（reader 自動偵測 source_type）|

### Reader dispatch

| Source | Reader | source_type |
|---|---|---|
| `.dcm` (NumberOfFrames=1) | `dicom_reader` | `dcm_single` |
| `.dcm` (NumberOfFrames>1) | `dicom_reader`（同檔內部判斷）| `dcm_multi` |
| `.png` 單檔 | `png_reader` | `png_file` |
| PNG 資料夾 | `png_reader` | `png_dir` |

### 通道處理

下游算法呼叫 `seq.as_gray() → (N, H, W)`；viz final overlay 呼叫 `seq.as_color() → (N, H, W, 3)`。

---

## §3 Segmentation 階段

| 維度 | 內容 |
|---|---|
| **入口** | `PaddleSegSegmenter.predict(image_path, dcm_array)` |
| **輸入** | `image_path: str`（給 paddle reader） + `dcm_array: np.ndarray`（單 frame，給 segmenter 內部）|
| **輸出** | `PIL.Image`（mode=P，palette；下游 convert("L") 取 uint8 mask） |
| **依賴 config** | `PaddleSegSegmenterConfig` |
| **效能特性** | model lazy load（建構時 `.load()` 一次）；每 frame predict |

---

## §4 Detection 階段（pass1）

| 維度 | 內容 |
|---|---|
| **入口** | `detect(image, config, use_segment=None)` |
| **輸入** | `image: gray uint8`、`config: DiaphragmDetectionConfig`、`use_segment: seg_mask`（pass1 提供，pass2 不提供） |
| **輸出** | `DetectionResult`（`best_region` / `filtered_binary` / `target_binary` / `potential_binary` / `debug_overlay`） |
| **依賴 config** | `DiaphragmDetectionConfig`（含 phase / sections / aspect_ratio / filter_top_ratio / fallback_region_top_ratio / detect_area_ratio / min_use_segment_area_ratio / area_ratio / use_otsu / median_blur / use_segment_background_px / prune_branch_max_length） |

### 主要動作

```
1. preprocessing: median_blur + filter_top_ratio × image_height 行清零
2. binary: use_segment 路徑（threshold paddle mask）vs 古典切割（algo_segmentation）
3. find_candidates: connected components → 雙路徑（potential_regions + use_segment_potentials）
4. diaphragm_curve_fit: skeleton + wavelet + poly-sin 擬合 + 評分 → best_idx
5. 組裝 filtered_binary / potential_binary / debug_overlay；決定 best_region 與 target_binary
6. fallback: 若 curve_fit 無 best，回 use_segment_potentials 或 image_shape 底部
```

---

## §5 ROI Band 階段

### §5.1 y_band 擴張

| 維度 | 內容 |
|---|---|
| **入口** | `compute_target_y_range(target_y_range, image_height, reserve_ratio)` |
| **輸入** | `detection.best_region`、影像高度、`RoiBandConfig.reserve_ratio` |
| **輸出** | `(y_min, y_max)` tuple，已 clamp 到 `[0, image_height]` |

### §5.2 Enhanced Search（pass2 detect）

| 維度 | 內容 |
|---|---|
| **入口** | `enhanced_search(image_gray, y_band, detection_config, roi_band_config)` |
| **輸入** | 原圖 + y_band + cfg |
| **輸出** | `RoiSearchResult`（`detection`（pass2）/ `enhanced_band` / `enhanced_padded` / `padded_mask` / `padded_overlay`） |
| **依賴 config** | `DiaphragmDetectionConfig`（**內部 `replace()` 出 `filter_top_ratio=0, median_blur=False`**） + `RoiBandConfig.enhance_num_segments`、`enhance_blur_kernel` |

### §5.3 Target Selection

| 維度 | 內容 |
|---|---|
| **入口** | `select_target(detection_pass1, refined, y_band, image_shape, use_segment_label)` |
| **輸入** | pass1 + pass2 結果 + `RoiBandConfig.use_segment_label` |
| **輸出** | `TargetSelection`（`target_binary`（可 None）/ `diaphragm_mask` / `overlay` / `padding_output` / `source`） |
| **決定**：`use_segment_label=True`→ 用 paddle pass1 結果；`False`→ 用古典 pass2 結果 |

---

## §6 Motion Curve 階段

| 維度 | 內容 |
|---|---|
| **入口** | `extract_motion_curve(image, y_range, config)` |
| **輸入** | `image: gray`（main.py 內 `cv2.medianBlur(gray, 7)`） + `y_range`(`y_band`) + `MotionCurveConfig` |
| **輸出** | `MotionCurveResult`（`init_diaphragm` / `broken_indices` / `smoothed_trough` / `smoothed_crest` / `diaphragm_p_trough` / `diaphragm_p_crest`） |
| **依賴 config** | `MotionCurveConfig`（含 `jump_threshold_ratio` / `fix_search_window_ratio` / `wavelet_level_trough` / `wavelet_level_crest`） |

### 主要動作

```
1. _trace_brightest: 逐 x 在 y_range 內找最亮 peak；y 跳躍 > jump_threshold_px → 標斷點
2. _fix_broken: 從前一點 y - fix_search_window_px 開始 argmax 補回斷點
3. wavelet_denoising × 2: 平滑出 smoothed_trough / smoothed_crest
4. peak-perspective 翻轉: diaphragm_p_* = round(h - smoothed_*) → 給 brightness_way 找波峰用
```

---

## §7 Excursion 階段

### §7.1 brightness_way

| 維度 | 內容 |
|---|---|
| **入口** | `brightness_way(diaphragm_mask, diaphragm_p_4crest, diaphragm_p_4trough, diaphragm_ori_y_value, config)` |
| **輸入** | `TargetSelection.diaphragm_mask` + `MotionCurveResult.diaphragm_p_crest` / `diaphragm_p_trough` / `init_diaphragm` + cfg |
| **輸出** | `ExcursionResult`（`batches: List[ExcursionBatch]`、`crossings`、`rise_or_decline`） |
| **依賴 config** | `ExcursionConfig`（`peak_min_distance_ratio` / `peak_prominence` / `midline_min_distance_ratio` / `excursion_rule_start_range` / `excursion_rule_end_range`）|

### 主要動作

```
1. find_midline → crossings + rise_or_decline
2. 依 crossings 數量分批
3. 每批跑 excursion_rule → selected_crest_x / selected_trough_x
4. find_boundary refine peak 位置（用 diaphragm_mask 修邊界）
5. 組裝 ExcursionBatch list
```

### §7.2 compute_peak_info

| 維度 | 內容 |
|---|---|
| **入口** | `compute_peak_info(crest, trough, scale_y, scale_x=None)` |
| **輸入** | 每 batch 的 `crest_position` / `trough_position` + `scale_y` / `scale_x`（從 `FrameSequence.metadata` 取） |
| **輸出** | `PeakInfo`（`excursion_pixel` / `excursion_cm` / `time_pixel` / `time_sec` / `velocity`） |
| **None guard**：`scale_y=None → excursion_cm=None`；`scale_x=None → time_sec=None`；`time_sec=0 → velocity=None` |

main.py 對 excursion phase 不傳 `scale_x` → `time_sec` / `velocity` 為 None；只算 `excursion_cm`。

---

## §8 Multi-frame Dispatch

Per `MultiframeConfig.mode` 分三路：

| Mode | 行為 | 落地進度 |
|---|---|---|
| `LEGACY` | per-frame loop（同舊 main.py） | ✅ Patch 11A 配置 + 11C-LEGACY main.py 整合；`bundle.multiframe.legacy_frame_indices` 控制要跑的 frame（None=全跑、list=指定）|
| `GLOBAL_WINDOW` | 抽 keyframe（FIXED_INDICES 或 PHASE_CORRELATE）→ 拼接 → 全局 excursion + final viz | ✅ Patch 11B / 11B' 邏輯 + 11C-GW main.py 整合 + 11D final overlay |
| `REALTIME` | 增量 shift_x 累加，partial window 即時更新 | ⬜ 探索階段 |

### Keyframe selection（GLOBAL_WINDOW）

```
KeyframeStrategy.FIXED_INDICES    → 用 cfg.keyframe_indices 直接照搬（experiment 值）
KeyframeStrategy.PHASE_CORRELATE  → _phase_correlate_keyframes() stub（待 user 補實作）
```

嚴格 2 個 keyframe（multi-frame 上限）。

### Stitch length（GLOBAL_WINDOW）— 兩段獨立

```
first  段長度 = min(keyframe_indices[0] × stride_pixel, frame_width)    (default)
              = cfg.stitch_length_px_first（capped by frame_width）       (override)

second 段長度 = (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel  (default)
              = cfg.stitch_length_px_second                                  (override)
```

拼接：`frame[0] 取前 first 段` + `frame[1] 取右尾 second 段` → concat。

物理意義：first ≈ 「掃描起點 → keyframe[0] 時刻」軌跡；second ≈ 「keyframe[0] → keyframe[1] 時刻」軌跡。

**不重做 wavelet**（keyframe 已平滑過）；位移只在 x 方向，y 噪音忽略。

> 視窗 pixel 公式為 multi-frame 實驗結果；理論上不會有超過 2 keyframe 的維度擴展。

---

## §9 Visualization 階段

| 維度 | 內容 |
|---|---|
| **入口** | `PipelineVisualizer.render_frame(frame_idx, image_gray, image_color, seg_mask, frame_result)` |
| **gated by** | `VisualizationConfig.enabled`（default False → 零 I/O） |

### 兩條獨立 track

| Track | 控制 | 輸出位置 |
|---|---|---|
| **debug** | `cfg.save_debug` + `cfg.debug_stages` filter | `output/debug/{stage}/{i:04d}.png` |
| **final** | `cfg.save_final` + `cfg.final_show_*` 三 toggles | `output/final/{i:04d}.png` |

### Debug stages（9 個）

```
paddle_segmentation
detection_pass1_overlay / detection_pass1_filtered / detection_pass1_potential
roi_band_yband / roi_band_enhanced
detection_pass2_overlay
motion_curve
excursion_brightness
```

### Final overlay 元素（依 toggle）

| Toggle | 元素 |
|---|---|
| `final_show_motion_curve` | motion curve 啞黃軌跡（debug 用襯底） |
| `final_show_peak_markers` | crest（黃星 + label）、trough（橘星 + label） |
| `final_show_excursion_text` | excursion_cm / sec / velocity 自訂字型文字 |

詳細 viz 細節見 [`visualization/`](../visualization/) 內各 layer 模組。

---

## §10 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§9 全部章節定義 | 文件化專案，提供 per-frame data flow 對照 |
| 2026-05-25 | — | §5.3 cfg 引用：`RunConfig.use_segment_label` → `RoiBandConfig.use_segment_label` | Patch 12A：RunConfig 已刪 |
| 2026-05-25 | — | §8 LEGACY 標 ✅ 11C-LEGACY；GLOBAL_WINDOW 改 11C-GW | Patch 11C-LEGACY 落地 |
| 2026-05-25 | — | §8 GLOBAL_WINDOW 邏輯標 ✅ 11B；keyframe default `[87, 149]`；stitch_length 496 對齊 spec | Patch 11B 邏輯落地 |
| 2026-05-25 | — | §8 Stitch length 拆兩段獨立（first + second）；移除具體 keyframe / pixel 數字（experiment 值，避免 doc rot） | Patch 11B'：兩段 stitching 邏輯 |
| 2026-05-25 | — | §8 GLOBAL_WINDOW 標 ✅ 11C-GW + 11D；main.py mode dispatch + global final viz 落地 | Patch 11C-GW + 11D |
