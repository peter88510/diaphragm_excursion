# api_reference.md — Config / Result / Function Reference

> 欄位 / 簽名級對照表。
> 設計層說明見 [`docs/modules/*`](modules/)；資料流見 [`docs/pipeline.md`](pipeline.md)。
> 完整 docstring 請看 source code。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | SNAPSHOT |
| 版本 | 0.9 |
| 最後更新 | 2026-05-29 |
| 校對對象 | `config/*.py`、`algorithm/**/*.py`、`input/**/*.py`、`visualization/**/*.py` |
| 狀態 | snapshot |
| 過期條件 | 任一對應 dataclass 欄位 / 函式簽名變動 → 更新本檔 |

---

## §1 Config Reference

### §1.1 `PaddleSegSegmenterConfig`

`config/paddleseg_config.py`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `config_path` | `str` | `DEFAULT_CONFIG_PATH` | paddle 模型 YAML 路徑 |
| `model_path` | `str` | `DEFAULT_MODEL_PATH` | 權重檔路徑 |
| `device` | `Optional[str]` | `None` | `'gpu'` / `'cpu'` / None=auto |
| `resize_ratio` | `float` | `1.0` | 推論前 resize 比例 |
| `aug_pred` | `bool` | `False` | test-time augmentation |
| `scales` | `float` | `1.0` | multi-scale 推論 |
| `flip_horizontal` | `bool` | `False` | 翻轉增強 |
| `flip_vertical` | `bool` | `False` | 翻轉增強 |
| `is_slide` | `bool` | `False` | sliding window |
| `crop_size` | `Optional[Tuple[int, int]]` | `None` | sliding window 設定 |
| `stride` | `Optional[Tuple[int, int]]` | `None` | sliding window 設定 |
| `custom_color` | `Optional[List[int]]` | `None` | 自訂 palette |
| `save_predictions` | `bool` | `False` | **預設關閉**；原 paddle 強制存檔被反轉 |
| `save_dir` | `str` | `DEFAULT_SAVE_DIR` | 存檔路徑 |

### §1.2 `DiaphragmDetectionConfig` + `Phase`

`config/diaphragm_detection_config.py`

```python
class Phase(Enum):
    SNIFF = 'sniff'
    EXCURSION = 'excursion'
    OTHER = 'other'
```

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `phase` | `Phase` | `EXCURSION` | 對應 sections / aspect_ratio_threshold |
| `sections` | `int` | `1` | curve_fit 分段擬合段數 |
| `aspect_ratio_threshold` | `float` | `4.0` | candidate w/h 比門檻 |
| `detect_area_ratio` | `float` | `20000/(955·1500)` | 古典切割累計面積 ratio |
| `use_otsu` | `bool` | `False` | True 走 OTSU；False 走階層累計 |
| `median_blur` | `bool` | `True` | preprocessing 是否 medianBlur |
| `filter_top_ratio` | `float` | `100/955` | 影像上方清零行數 ratio |
| `use_segment_background_px` | `int` | `38` | paddle mask 二值化 threshold |
| `min_use_segment_area_ratio` | `float` | `1000/(955·1500)` | use_segment fallback 面積 ratio |
| `area_ratio` | `float` | `10000/(955·1500)` | candidate 占圖面積 ratio 門檻 |
| `fallback_region_top_ratio` | `float` | `200/955` | fallback region 上緣 ratio |
| `prune_branch_max_length` | `int` | `100` | skeleton 短分支修剪 |
| `curve_fit_maxfev` | `int` | `5000` | scipy curve_fit 迭代上限（原寫死 10M；截斷不收斂浪費，Patch 20B）|

`for_phase(phase)` classmethod：依 phase 推導 sections / aspect_ratio_threshold。

### §1.3 `RoiBandConfig`

`config/roi_band_config.py`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `reserve_ratio` | `float` | `0.052` | y_band 上下擴張比例 (= 50/955) |
| `enhance_num_segments` | `int` | `1` | enhanced_search 水平分段數 |
| `enhance_blur_kernel` | `int` | `5` | 強化後 medianBlur kernel |
| `use_segment_label` | `bool` | `True` | `select_target` mask 來源：True=paddle pass1；False=古典 pass2（Patch 12A 從 `RunConfig` 合入） |

### §1.4 `MotionCurveConfig`

`config/motion_curve_config.py`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `jump_threshold_ratio` | `float` | `120/955` | y 跳躍斷點閾值 ratio |
| `fix_search_window_ratio` | `float` | `50/955` | 補斷點搜尋窗 ratio |
| `wavelet_level_trough` | `int` | `3` | 波谷平滑 wavelet level |
| `wavelet_level_crest` | `int` | `3` | 波峰平滑 wavelet level |

### §1.5 `ExcursionConfig`

`config/excursion_config.py`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `peak_min_distance_ratio` | `float` | `0.0333` | find_peaks 距離 ratio (= 50/1500) |
| `peak_prominence` | `int` | `10` | find_peaks 突起閾值 |
| `midline_min_distance_ratio` | `float` | `100/1500` | 中線交點過濾距離 ratio |
| `excursion_rule_start_range` | `int` | `1` | rule 起點跳過範圍 |
| `excursion_rule_end_range` | `int` | `0` | rule 終點跳過範圍 |

### §1.6 `RunBundle`

`config/run_bundle.py`

聚合 root cfg；main.py 用 `RunBundle.for_phase(Phase.EXCURSION)` 一行 instantiate 全部。

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `segmenter` | `PaddleSegSegmenterConfig` | default | paddle 模型 cfg |
| `dicom_crop` | `DicomCropConfig` | default | DICOM region crop cfg |
| `detection` | `DiaphragmDetectionConfig` | default | 偵測 cfg |
| `roi_band` | `RoiBandConfig` | default | ROI band cfg（含 `use_segment_label`） |
| `motion_curve` | `MotionCurveConfig` | default |  |
| `excursion` | `ExcursionConfig` | default |  |
| `viz` | `VisualizationConfig` | default |  |
| `multiframe` | `MultiframeConfig` | default |  |

**Classmethod**：`RunBundle.for_phase(phase)` — 目前只代 `detection`；其他 sub-cfg 用 default。

> 原 `RunConfig` 已於 Patch 12A 刪除；`use_segment_label` 移至 `RoiBandConfig`（§1.3）。

### §1.7 `VisualizationConfig`

`config/visualization_config.py`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `enabled` | `bool` | （見 source）| viz 總開關；False 時全 track 零 I/O |
| `output_dir` | `Path` | `Path("output")` | 根輸出目錄 |
| `save_final` | `bool` | `True` | final track 開關（全 mode 經 render_frame）|
| `save_debug` | `bool` | （見 source）| debug per-stage track 開關（全 mode）|
| `save_realtime` | `bool` | `False` | realtime track 開關（僅 REALTIME mode 生效）|
| `debug_stages` | `Optional[FrozenSet[str]]` | `None` | None=全部；set=過濾 |
| `final_font_path` | `str` | `"./font/Altinn-DIN Bold.otf"` | 自訂字型（final / realtime 共用）|
| `final_show_motion_curve` | `bool` | （見 source）| final: motion curve 軌跡 |
| `final_show_peak_markers` | `bool` | `True` | final: crest/trough markers + labels |
| `final_show_excursion_text` | `bool` | `True` | final: excursion_cm / sec / velocity 文字 |
| `rt_show_motion_curve` | `bool` | `True` | realtime: 軌跡（即時主視覺，預設開）|
| `rt_show_peak_markers` | `bool` | `True` | realtime: crest/trough markers |
| `rt_show_excursion_text` | `bool` | `True` | realtime: excursion_cm 文字 |

> 三 track（final / debug / realtime）獨立可組合；final/debug 全 mode 生效，realtime 僅 REALTIME mode 呼叫 renderer。REALTIME 通常只開 save_realtime。

### §1.8 `MultiframeConfig` + `MultiframeMode` + `KeyframeStrategy` + `ShiftStrategy`

`config/multiframe_config.py`

```python
class MultiframeMode(Enum):
    LEGACY = 'legacy'              # per-frame loop
    GLOBAL_WINDOW = 'global_window'  # Mode 1（default）
    REALTIME = 'realtime'           # Mode 2

class KeyframeStrategy(Enum):       # GLOBAL_WINDOW keyframe 取得
    FIXED_INDICES = 'fixed_indices'
    PHASE_CORRELATE = 'phase_correlate'

class ShiftStrategy(Enum):          # REALTIME 相鄰幀位移估計
    FIXED = 'fixed'                  # 固定 stride_pixel（legacy/fallback）
    TEMPLATE_MATCH = 'template_match'    # 右 column matchTemplate → 整數 px
    PHASE_CORRELATE = 'phase_correlate'  # cv2.phaseCorrelate → float sub-pixel
```

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `mode` | `MultiframeMode` | `GLOBAL_WINDOW` | dispatch 三模式之一 |
| `legacy_frame_indices` | `Optional[List[int]]` | `None` | LEGACY 模式跑哪些 frame；None=全跑 |
| `keyframe_strategy` | `KeyframeStrategy` | `FIXED_INDICES` | GLOBAL_WINDOW keyframe 取得策略 |
| `keyframe_indices` | `List[int]` | （experiment）| FIXED_INDICES 用；嚴格 2 個（multi-frame 上限）|
| `stride_pixel` | `int` | `8` | 每 frame 位移（GLOBAL_WINDOW 拼接 / REALTIME FIXED 策略 / 低信心 fallback）|
| `stitch_length_px_first` | `Optional[int]` | `None` | GLOBAL_WINDOW；None=自動算 `min(idx[0]×stride, frame_width)`|
| `stitch_length_px_second` | `Optional[int]` | `None` | GLOBAL_WINDOW；None=自動算 `(idx[1]-idx[0])×stride`|
| `realtime_warmup_frames` | `int` | `0` | REALTIME UX gating：< 此值標 "warming up" 不疊 overlay |
| `realtime_algorithm_min_width` | `int` | `200` | REALTIME 安全網：累積 width < 此值跳過全局 brightness_way |
| `realtime_wavelet_refresh_every_n` | `Optional[int]` | `50` | REALTIME 每 N 幀整段 buffer 重做 wavelet 消邊界 artifact；None=不重做 |
| `realtime_seg_refresh_max_n` | `int` | `60` | REALTIME 分層 cadence：距上次 heavy(paddle) 幀達此數強制再跑（峰觸發為主，此為保底上限，Patch 19A）|
| `realtime_max_frames` | `Optional[int]` | `None` | REALTIME 跑到第幾幀停（測試用）；None=全 sequence |
| `realtime_shift_strategy` | `ShiftStrategy` | `TEMPLATE_MATCH` | REALTIME 相鄰幀位移估計策略 |
| `realtime_shift_min_confidence` | `float` | `0.3` | 位移信心門檻；< 此值視為無效幀跳過。量綱依 strategy |

> GLOBAL_WINDOW 視窗 pixel 公式為 multi-frame 實驗結果；理論上不超過 2 keyframe。
> REALTIME 拼接用變動位移（estimate_shift），非固定 stride；見 §3.7 / `frame_shift.py`。
> REALTIME 分層 cadence（Patch 19A）：heavy 幀（paddle 全 pipeline，更新 y_band + 提供整張 frame mask）僅在 bootstrap / 峰觸發 / 距上次 ≥ `realtime_seg_refresh_max_n`；其餘為 light（沿用 cached y_band 只跑 motion_curve）。mask 採 refresh-recent。

### §1.9 `DicomCropConfig`

`config/dicom_crop_config.py`

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `ruler` | `int` | `20` | 上方 / 左側留白寬度（pixel）|
| `black_padding` | `int` | `0` | 左側額外 padding（pixel）|

掛在 `RunBundle.dicom_crop`；對應 `apply_dicom_crop(seq, cfg)`。

---

## §2 Result Types

### §2.1 `FrameSequence`

`input/frame_sequence.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `frames` | `np.ndarray` | `(N, H, W)` 或 `(N, H, W, 3)` |
| `source_type` | `str` | `dcm_single` / `dcm_multi` / `png_file` / `png_dir` |
| `source_path` | `str` | 原始路徑 |
| `fps` | `Optional[float]` | multi-frame DCM 才有意義 |
| `metadata` | `dict` | `physical_delta_y/x` / `region_location` / `image_paths` |

**Methods**: `is_color` (property)、`as_gray() → (N,H,W)`、`as_color() → (N,H,W,3)`

### §2.2 `DetectionResult`

`algorithm/diaphragm_detection/detector.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `best_region` | `Tuple[int, int]` | `(y_top, y_bottom)` |
| `filtered_binary` | `np.ndarray` | 所有 CC union |
| `target_binary` | `Optional[np.ndarray]` | 給 brightness_way 用；fallback 時為 None |
| `potential_binary` | `Optional[np.ndarray]` | potential candidates union；fallback 時為 None |
| `debug_overlay` | `Optional[np.ndarray]` | BGR color-coded viz |

### §2.3 `RoiSearchResult`

`algorithm/roi_band/enhanced_search.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `detection` | `DetectionResult` | pass2 detect 結果 |
| `enhanced_band` | `np.ndarray` | 強化後小尺寸 `(band_h, w)` |
| `enhanced_padded` | `np.ndarray` | 強化後 zero-pad 回原圖大小 `(h, w)` |
| `padded_mask` | `np.ndarray` | pass2 `filtered_binary` 還原 `(h, w)` |
| `padded_overlay` | `np.ndarray` | pass2 `debug_overlay` 還原 `(h, w, 3)` |

### §2.4 `TargetSelection`

`algorithm/roi_band/target_selection.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `target_binary` | `Optional[np.ndarray]` | 邊界計算用 |
| `diaphragm_mask` | `np.ndarray` | 橫膈膜 ROI mask |
| `overlay` | `np.ndarray` | debug viz（= `refined.padded_overlay`）|
| `enhanced_padded` | `np.ndarray` | 強化後 padded（= `refined.enhanced_padded`）|
| `source` | `str` | `'segment'` / `'classical'` |

### §2.5 `MotionCurveResult`

`algorithm/motion_curve/extract.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `init_diaphragm` | `np.ndarray` | 原始軌跡 `(W,)`（已修補斷點）|
| `broken_indices` | `np.ndarray` | 修補前哪些 x 是斷點 |
| `smoothed_trough` | `np.ndarray` | wavelet 平滑（波谷分析用） |
| `diaphragm_p_trough` | `np.ndarray` | peak-perspective: `h - smoothed_trough` |
| `smoothed_crest` | `np.ndarray` | wavelet 平滑（波峰分析用） |
| `diaphragm_p_crest` | `np.ndarray` | peak-perspective: `h - smoothed_crest` |

### §2.6 `ExcursionResult` + `ExcursionBatch`

`algorithm/excursion/brightness.py`

**`ExcursionResult`**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `batches` | `List[ExcursionBatch]` | 依 crossings 分組 |
| `crossings` | `np.ndarray` | 全部中線交點 |
| `rise_or_decline` | `np.ndarray` | 全部方向標籤 |

**`ExcursionBatch`**

| 欄位 | 型別 | 說明 |
|---|---|---|
| `crest_position` | `Tuple[int, int]` | `(x, y)` 已 find_boundary 修正 |
| `trough_position` | `Tuple[int, int]` | `(x, y)` |
| `selected_crest_x` | `List[int]` | rule 選出的 x |
| `selected_trough_x` | `List[int]` |  |
| `crest_bar_max_peak` | `List[int]` | 對應 `init_diaphragm[x]` |
| `trough_bar_max_peak` | `List[int]` |  |

### §2.7 `PeakInfo`

`algorithm/excursion/measurement.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `crest` | `Tuple[int, int]` | `(x, y)` |
| `trough` | `Tuple[int, int]` | `(x, y)` |
| `excursion_pixel` | `int` | `\|crest_y - trough_y\| + 1` |
| `excursion_cm` | `Optional[float]` | `scale_y is None → None` |
| `time_pixel` | `int` | `\|crest_x - trough_x\| + 1` |
| `time_sec` | `Optional[float]` | `scale_x is None → None` |
| `velocity` | `Optional[float]` | `time_sec is None/0 → None` |

### §2.8 `FrameResult`

`algorithm/frame_result.py`

| 欄位 | 型別 | 來源 |
|---|---|---|
| `detection` | `DetectionResult` | pass1 detect |
| `y_band` | `Tuple[int, int]` | `compute_target_y_range` |
| `refined` | `RoiSearchResult` | `enhanced_search` (pass2) |
| `selection` | `TargetSelection` | `select_target` |
| `motion_curve` | `MotionCurveResult` | `extract_motion_curve` |
| `excursion` | `Optional[ExcursionResult]` | `brightness_way`（excursion phase 才填）|
| `measurements` | `List[PeakInfo]` | `compute_peak_info` per batch |

### §2.9 `GlobalExcursionResult`

`algorithm/multiframe/global_window.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `stitched_init_diaphragm` | `np.ndarray` | `(W_full,)` 拼接 init 軌跡 |
| `stitched_smoothed_trough` | `np.ndarray` | wavelet 平滑（不重做，直接 concat keyframe 結果）|
| `stitched_smoothed_crest` | `np.ndarray` |  |
| `stitched_p_trough` | `np.ndarray` | peak-perspective；給 brightness_way 用 |
| `stitched_p_crest` | `np.ndarray` |  |
| `stitched_diaphragm_mask` | `np.ndarray` | `(H, W_full)` 拼接 mask |
| `excursion` | `ExcursionResult` | 全局 brightness_way 結果 |
| `measurements` | `List[PeakInfo]` | 全局物理量 per batch |
| `keyframe_indices` | `List[int]` | 拼接用 keyframe |
| `first_segment_len_px` | `int` | first 段實際長度（含 frame_width cap）|
| `second_segment_len_px` | `int` | second 段實際長度 |
| `stitch_boundary_x` | `int` | 拼接點 x 座標（= `first_segment_len_px`）|
| `full_width` | `int` | 全局 signal 總寬 = `first_segment_len_px + second_segment_len_px` |

### §2.10 `RealtimeState`

`algorithm/multiframe/realtime.py`（REALTIME mode 累積 state；含 streaming-ready `ingest_frame`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `algorithm_min_width` / `wavelet_refresh_every_n` / `wavelet_level_trough` / `wavelet_level_crest` | — | config snapshot（建構帶入）|
| `stitched_init_diaphragm` / `stitched_smoothed_{trough,crest}` / `stitched_p_{trough,crest}` | `Optional[np.ndarray]` | `(W_now,)` 累積右尾拼接 signal |
| `stitched_diaphragm_mask` | `Optional[np.ndarray]` | `(H, W_now)` 累積 mask |
| `excursion` | `Optional[ExcursionResult]` | rolling 全局結果；width < min 時 None |
| `measurements` | `List[PeakInfo]` | rolling 物理量 |
| `ingested_indices` / `shifts` | `List[int]` | 每次 ingest 的 frame idx / 取的右尾 px（供 viz 對齊 color canvas）|
| `last_frame_idx` / `n_ingested` / `last_wavelet_refresh_n` / `full_width` | `int` | metadata |

`ingest_frame(motion_curve, idx, shift_px, excursion_cfg, scale_y=None, full_mask=None)`：append 右尾 shift_px（curve append-only；mask light=carry-forward / heavy=refresh-recent）→ 視情況 refresh wavelet → rolling brightness_way。Patch 19A decouple 成吃 `motion_curve` + 可選 `full_mask`（heavy 幀 paddle mask）。

### §2.11 `ShiftResult`

`algorithm/multiframe/frame_shift.py`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `shift_px` | `int` | forward 位移（拼接用整數；正=前進、≤0=delay/倒退）= `-raw` |
| `raw_shift` | `float` | native 估計值（與實驗 code 同號，便於對照）|
| `confidence` | `float` | template score / phaseCorrelate confidence；FIXED=1.0 |
| `found` | `bool` | confidence ≥ min_confidence |

---

## §3 Public Functions

### §3.1 Input

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `load` | `(path: str)` | `FrameSequence` | 依路徑類型分派 reader |
| `apply_dicom_crop` | `(seq, cfg: DicomCropConfig)` | `FrameSequence` | DCM region_location 裁切；非 DCM no-op |

### §3.2 Segmentation

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `PaddleSegSegmenter.__init__` | `(cfg)` | — | 不做重活；不 load |
| `PaddleSegSegmenter.load` | `()` | `None` | 一次性 setup（含 load weights） |
| `PaddleSegSegmenter.predict` | `(image_path, dcm_array=None)` | `PIL.Image` | 共用已 load 的 predictor；mode=P 含 palette |

### §3.3 Detection

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `detect` | `(image, config, use_segment=None, timing=None)` | `DetectionResult` | 主入口；`use_segment` 提供時走 paddle 路徑；`timing` 為 REALTIME Layer D 計時（duck-typed，optional）|

### §3.4 ROI band

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `compute_target_y_range` | `(target_y_range, image_height, reserve_ratio)` | `Tuple[int, int]` | best_region 上下擴張 ratio |
| `enhanced_search` | `(image_gray, y_band, detection_config, roi_band_config, timing=None)` | `RoiSearchResult` | enhance + medianBlur + pass2 detect；`timing` 同上（轉發給 pass2 detect）|
| `select_target` | `(detection_pass1, refined, y_band, image_shape, use_segment_label)` | `TargetSelection` | 依 cfg 選 mask 來源 |

### §3.5 Motion curve

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `extract_motion_curve` | `(image, y_range, config)` | `MotionCurveResult` | 逐 x 追亮 peak + 補斷點 + wavelet × 2 |

### §3.6 Excursion

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `brightness_way` | `(diaphragm_mask, diaphragm_p_4crest, diaphragm_p_4trough, diaphragm_ori_y_value, config)` | `ExcursionResult` | midline + rule + boundary refine |
| `compute_peak_info` | `(crest, trough, scale_y=None, scale_x=None)` | `PeakInfo` | None-safe 物理量計算 |
| `aggregate_measurements` | `(measurements: List[PeakInfo])` | `Optional[PeakInfo]` | 多組 → 單值聚合 stub（暫 fallback 第 0 組）|

### §3.7 Multi-frame

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `get_legacy_frame_indices` | `(cfg, seq)` | `List[int]` | LEGACY 模式要跑的 frame indices |
| `get_keyframe_indices` | `(cfg, seq)` | `List[int]` | GLOBAL_WINDOW 抽 keyframe；dispatch FIXED_INDICES / PHASE_CORRELATE |
| `_phase_correlate_keyframes` | `(seq, cfg)` | `List[int]` | **stub**，raise NotImplementedError |
| `run_global_window` | `(keyframe_motion_curves, keyframe_selections, multiframe_cfg, excursion_cfg, scale_y=None)` | `GlobalExcursionResult` | Mode 1 主入口；嚴格 2 keyframe |
| `estimate_shift` | `(prev_gray, curr_gray, strategy, stride_pixel, min_confidence)` | `ShiftResult` | REALTIME 相鄰幀位移；dispatch FIXED / TEMPLATE_MATCH / PHASE_CORRELATE |
| `RealtimeState.ingest_frame` | `(motion_curve, idx, shift_px, excursion_cfg, scale_y=None, full_mask=None)` | `None` | 累積右尾 + rolling 全局 excursion；`full_mask`=heavy 幀 paddle mask（refresh-recent）/ None=light（streaming-ready）|

### §3.8 Signal processing

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `wavelet_denoising` | `(signal, wavelet='db4', level=5)` | `np.ndarray` | 低頻趨勢提取 |

### §3.9 Visualization

| Function | Signature | Returns | 用途 |
|---|---|---|---|
| `PipelineVisualizer.__init__` | `(cfg, excursion_config)` | — |  |
| `PipelineVisualizer.render_frame` | `(frame_idx, image_gray, image_color, seg_mask, frame_result)` | `None` | disabled 時零 I/O |
| `excursion_info_display` | `(figure, measurements: List[PeakInfo], font_path=..., peak='ct', show_text=True)` | `np.ndarray` | 多 peak markers + 自訂字；px / 字型按 image height ratio 化（ref 1500×955）|
| `render_global_final` | `(global_result, image_color_first, image_color_second, cfg, excursion_cfg)` | `None` | GLOBAL_WINDOW final overlay；風格沿用 single-frame |
| `render_realtime_global` | `(frame_idx, state, color_frames, is_warmup, warmup_total, cfg, excursion_cfg)` | `None` | REALTIME 完整累積 track（gate by save_realtime）|
| `render_realtime_canvas` | `(frame_idx, image_color, state, is_warmup, warmup_total, cfg, excursion_cfg)` | `None` | REALTIME 即時視窗 track：frame[i] 底 + global 軌跡右錨定 + 累積邊界虛線 |

---

## §4 Cross-reference（Config → Function → Result）

| Config | Caller | Returns |
|---|---|---|
| `PaddleSegSegmenterConfig` | `PaddleSegSegmenter.predict` | `PIL.Image` |
| `DiaphragmDetectionConfig` | `detect` | `DetectionResult` |
| `RoiBandConfig` + `DiaphragmDetectionConfig` | `enhanced_search` | `RoiSearchResult` |
| `RoiBandConfig.use_segment_label` | `select_target` | `TargetSelection` |
| `MotionCurveConfig` | `extract_motion_curve` | `MotionCurveResult` |
| `ExcursionConfig` | `brightness_way` | `ExcursionResult` |
| （無 cfg） | `compute_peak_info` | `PeakInfo` |
| `MultiframeConfig` | `get_legacy_frame_indices` / `get_keyframe_indices` | `List[int]` |
| `MultiframeConfig` + `ExcursionConfig` | `run_global_window` | `GlobalExcursionResult` |
| `MultiframeConfig`（shift_strategy）| `estimate_shift` | `ShiftResult` |
| `ExcursionConfig` | `RealtimeState.ingest_frame` | `RealtimeState`（rolling 全局）|
| `VisualizationConfig` + `ExcursionConfig` | `PipelineVisualizer.render_frame` / `render_realtime_*` | `None`（side-effect 寫 PNG） |

---

## §5 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | 0.1 | 初版建立；§1 9 個 cfg + §2 9 個 result + §3 ~18 個 function + §4 cross-ref | 進階文件化階段，提供欄位 / 簽名速查 |
| 2026-05-25 | 0.2 | §1.3 加 `use_segment_label`；§1.6 RunConfig → RunBundle；§4 cross-ref 更新 | Patch 12A：刪 RunConfig + 建 RunBundle |
| 2026-05-25 | 0.3 | §1.8 keyframe default `[88,149]` → `[87,149]`；§2.9 GlobalExcursionResult 完整欄位；§3.7 `run_global_window` 簽名實落地 | Patch 11B：GLOBAL_WINDOW 邏輯落地 |
| 2026-05-25 | 0.4 | §1.8 `stitch_length_px` 拆 `stitch_length_px_first` + `stitch_length_px_second`；§2.9 `first_segment_len_px` / `second_segment_len_px` 取代舊欄位；移除具體 keyframe / pixel 數字（experiment 值） | Patch 11B'：stitching 邏輯改為兩段獨立 |
| 2026-05-25 | 0.5 | §3.9 加 `render_global_final` | Patch 11D：GLOBAL_WINDOW final overlay |
| 2026-05-25 | 0.6 | §1.9 新增 `DicomCropConfig`；§1.6 RunBundle 加 `dicom_crop`；§3.1 `apply_dicom_crop` 簽名改吃 cfg；header 版號補 bump 對齊變更紀錄 | Patch 13A：dicom_crop 參數抽至 config |
| 2026-05-25 | 0.7 | §3.6 加 `aggregate_measurements`；§3.9 `excursion_info_display` 簽名改吃 `List[PeakInfo]` + 註記 ratio 化 | Patch 13C：info_display 多 peak + ratio 化 + aggregator stub |
| 2026-05-29 | 0.8 | §1.7 加 `save_realtime` / `rt_show_*`；§1.8 加 `ShiftStrategy` + 6 個 `realtime_*` 欄位、mode default 改 GLOBAL_WINDOW；§2.10 `RealtimeState` / §2.11 `ShiftResult`；§3.7 加 `estimate_shift` / `ingest_frame`；§3.9 加 `render_realtime_*`；§4 cross-ref 更新 | Patch 14A-18：REALTIME mode 端到端（state / 變動位移 / 滑動視窗 / 雙 track viz）|
| 2026-05-29 | 0.9 | §1.2 加 `curve_fit_maxfev`；§1.8 加 `realtime_seg_refresh_max_n` + 分層 cadence 註；§2.10 / §3.7 `ingest_frame` 簽名改 `(motion_curve, ..., full_mask)`；§3.3 `detect` / §3.4 `enhanced_search` 加 optional `timing` | Patch 19A（分層 cadence + refresh-recent）+ Patch 19 Layer C/D timing + Patch 20B（`curve_fit_maxfev`）|
