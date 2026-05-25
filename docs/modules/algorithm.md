# algorithm/ — 演算法層

> Per-frame 演算法管線的核心實作。
> Pipeline 階段對照見 [`docs/pipeline.md`](../pipeline.md)；跨層架構見 [`ARCHITECTURE.md`](../../ARCHITECTURE.md)。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 修改 algorithm 內邏輯時參考；新人理解資料流 |

---

## §1 模組目標

`algorithm/` 收集所有「**輸入 image / mask，輸出 dataclass result**」的純函式邏輯。

設計約束：

- **零副作用**：不寫 `cv2.imshow` / `plt.show` / module-level state mutation
- **dataclass 回傳**：不回 tuple / dict；型別在 result 各自定義
- **config-driven**：可調參數從 cfg 注入，不在演算法內 hardcode
- **跨層方向**：見 [ARCHITECTURE.md §4](../../ARCHITECTURE.md#4-跨層方向與依賴規約)；algorithm 不可 import visualization

---

## §2 子結構概覽

按 pipeline 順序：

| Sub-package | 用途 | 主要對外型別 |
|---|---|---|
| `segmentation/` | PaddleSeg 模型 lazy load + predict | `PaddleSegSegmenter` |
| `diaphragm_detection/` | mask + 古典法 → 找橫膈膜 ROI | `detect()` → `DetectionResult` |
| `roi_band/` | y_band 擴張 + 強化 + pass2 detect + target 選定 | `RoiSearchResult` / `TargetSelection` |
| `motion_curve/` | 逐 x 軌跡擷取 + wavelet 平滑 | `extract_motion_curve()` → `MotionCurveResult` |
| `excursion/` | midline + peak/trough + boundary refine + 物理量 | `brightness_way()` → `ExcursionResult` / `PeakInfo` |
| `multiframe/` | Multi-frame 模式 dispatch（LEGACY / GLOBAL_WINDOW / REALTIME） | `get_*_indices()` / `run_global_window()`（待） |
| `signal_processing/` | wavelet 等通用 helper | `wavelet_denoising()` |

外加根層：
- `algorithm/__init__.py` — re-export `FrameResult`
- `algorithm/frame_result.py` — `FrameResult` dataclass，聚合 per-frame 全部 stage result

---

## §3 對外 API

**從 main.py 視角**，algorithm 提供以下入口：

```python
# segmentation
from algorithm.segmentation import PaddleSegSegmenter

# detection
from algorithm.diaphragm_detection import detect, DetectionResult

# roi_band
from algorithm.roi_band import (
    compute_target_y_range, enhanced_search, select_target,
    RoiSearchResult, TargetSelection,
)

# motion_curve
from algorithm.motion_curve import extract_motion_curve, MotionCurveResult

# excursion
from algorithm.excursion import (
    brightness_way, compute_peak_info,
    ExcursionResult, ExcursionBatch, PeakInfo,
)

# multiframe (Step 10)
from algorithm.multiframe import get_legacy_frame_indices, get_keyframe_indices

# 聚合
from algorithm import FrameResult
```

---

## §4 各 Sub-package

### §4.1 `segmentation/`

| 維度 | 內容 |
|---|---|
| **檔案** | `base.py`（`SegmenterBase` abstract）/ `paddleseg_segmenter.py`（`PaddleSegSegmenter`） |
| **入口** | `PaddleSegSegmenter(cfg).load()` 一次；`segmenter.predict(image_path, dcm_array)` per frame |
| **依賴 config** | `PaddleSegSegmenterConfig` |
| **依賴外部** | `paddleseglibs/`（vendored PaddleSeg，含 Patch 2A-2C 改動） |

#### 設計重點

- **lazy load**：`PaddleSegSegmenter` 建構時不載 model；`.load()` 顯式觸發；後續 predict 重用同一 model
- **`predict()` 介面**：`(image_path, dcm_array=None)` — Patch 2 決定保留兩個參數，讓 wrapper 既能用 paddle 內部 reader（給 path）又能直接接 multi-frame DCM array（已切片）
- **回傳 PIL Image**：mode=P + palette；caller 用 `np.array(.convert("L"))` 取 uint8 mask
- **副作用**：原 paddle 寫死的 `save_predictions` 已透過 cfg toggle 控制（default off）

#### 已知議題

- Multi-frame DCM 在 `save_predictions=True` 時 N 個 mask 寫到同一個 PNG 互相覆蓋（檔名不含 frame index）。目前測試流程不依賴存檔；將來修法見 PROGRESS.md「Multi-frame DCM 存檔覆蓋 bug」

---

### §4.2 `diaphragm_detection/`

| 維度 | 內容 |
|---|---|
| **檔案** | `detector.py`（`detect()` + `DetectionResult`）/ `classical.py`（`algo_segmentation`）/ `candidate.py`（`find_candidates`）/ `curve_fit.py`（`diaphragm_curve_fit`） |
| **入口** | `detect(image, config, use_segment=None) → DetectionResult` |
| **依賴 config** | `DiaphragmDetectionConfig`（phase / sections / aspect_ratio / `filter_top_ratio` / `fallback_region_top_ratio` / `detect_area_ratio` / `min_use_segment_area_ratio` / `area_ratio` / `use_otsu` / `median_blur` / `use_segment_background_px` / `prune_branch_max_length`） |

#### 設計重點

- **雙路徑 binary**：`use_segment=None` 走 `algo_segmentation`（古典 gamma + 階層）；提供 mask 走 paddle 二值化
- **雙路徑 candidates**：`potential_regions`（aspect_ratio + area_ratio 嚴格篩）給 curve_fit；`use_segment_potentials`（只 area 篩）給 fallback
- **curve_fit 評分**：每 candidate 抽 skeleton → wavelet 平滑後做 poly+sin 擬合 → morphological_comparison 評分（peak count diff + valley count diff + energy + position）；越小越像
- **fallback**：curve_fit 沒選出 best 時，若有 use_segment_potentials 則取其 y 範圍 union，否則回 `(fallback_region_top, image_height)`
- **size-sensitive 參數**已 Step 9 ratio 化；對任意尺寸影像可運行

#### 對 `DetectionResult` 欄位

| 欄 | 用途 |
|---|---|
| `best_region` | `(y_top, y_bottom)` 給 roi_band y_range 用 |
| `filtered_binary` | 所有 connected components union；給 enhanced_search 與 viz 用 |
| `target_binary` | 給 brightness_way 找 peak 邊界用（excursion phase + use_segment 時為 filtered_binary 全部）|
| `potential_binary` | potential candidates union；給 viz 用 |
| `debug_overlay` | color-coded BGR；給 viz 用 |

---

### §4.3 `roi_band/`

| 維度 | 內容 |
|---|---|
| **檔案** | `y_range.py` / `enhancement.py` / `enhanced_search.py` / `target_selection.py` |
| **入口** | 三個函式串接：`compute_target_y_range()` → `enhanced_search()` → `select_target()` |
| **依賴 config** | `RoiBandConfig`（`reserve_ratio` / `enhance_num_segments` / `enhance_blur_kernel` / `use_segment_label`）+ `DiaphragmDetectionConfig`（給 pass2 detect 用） |

#### `compute_target_y_range()`

`detection.best_region` 上下各擴張 `image_height × reserve_ratio` pixel，clamp 到 `[0, image_height]`。

#### `enhanced_search()`

1. `enhance_band(image, y_band, num_segments=1)` → 變分增強 band 區域
2. `cv2.medianBlur(enhanced, enhance_blur_kernel)` → 抑制雜訊
3. 第二次 `detect()`，**內部 `replace(detection_config, filter_top_ratio=0, median_blur=False)`**（避免重複 preprocessing）
4. Zero-pad pass2 結果回原圖大小 → `RoiSearchResult`

#### `select_target()`

依 `RoiBandConfig.use_segment_label` 決定下游 `diaphragm_mask` 來源：
- `True`（default）→ 用 pass1 (paddle) 結果（更穩定）
- `False` → 用 pass2 (古典) 結果（更靈敏）

回傳 `TargetSelection`：`target_binary`（可 None）+ `diaphragm_mask`（給 brightness_way）+ `overlay`（給 viz）+ `padding_output`（給 viz）+ `source`（debug）

---

### §4.4 `motion_curve/`

| 維度 | 內容 |
|---|---|
| **檔案** | `extract.py`（`extract_motion_curve` + `MotionCurveResult` + helpers）|
| **入口** | `extract_motion_curve(image, y_range, config) → MotionCurveResult` |
| **依賴 config** | `MotionCurveConfig`（`jump_threshold_ratio` / `fix_search_window_ratio` / `wavelet_level_trough` / `wavelet_level_crest`）|
| **依賴內部** | `algorithm.signal_processing.wavelet_denoising` |

#### 主要動作

```
1. _trace_brightest:
     for x in range(W):
         peaks = find_peaks(image[y_min:y_max, x])
         y = peaks[argmax(bar[peaks])] + y_min
         if abs(y - pre_y) > jump_threshold_px: 標斷點 (init_diaphragm[x]=0)
2. _fix_broken:
     for x in broken_indices:
         bar = image[pre_y - fix_search_window_px : , x]
         y = argmax(bar) + offset → 補回
3. wavelet_denoising × 2 (level=trough / level=crest):
     smoothed_trough / smoothed_crest
4. peak-perspective:
     diaphragm_p_trough = round(h - smoothed_trough)
     diaphragm_p_crest  = round(h - smoothed_crest)
```

#### 設計重點

- **smoothed_trough / smoothed_crest 同 wavelet level**：原作者試過分化後恢復同 level，欄位仍分開為未來分化預留接口
- **peak-perspective 翻轉**：`y' = h - y` 讓 find_peaks 直接找原本的「波谷」
- **size 處理**：jump_threshold 與 fix_search_window 用 ratio（Patch 10A）；對任意 image_height 縮放

---

### §4.5 `excursion/`

| 維度 | 內容 |
|---|---|
| **檔案** | `brightness.py`（`brightness_way` + `ExcursionResult` + `ExcursionBatch`）/ `midline.py`（`find_midline`）/ `rules.py`（`excursion_rule`）/ `boundary.py`（`find_boundary`）/ `measurement.py`（`compute_peak_info` + `PeakInfo`） |
| **入口** | `brightness_way()` + `compute_peak_info()` |
| **依賴 config** | `ExcursionConfig`（`peak_min_distance_ratio` / `peak_prominence` / `midline_min_distance_ratio` / `excursion_rule_start_range` / `excursion_rule_end_range`）|

#### `brightness_way()` 流程

```
1. find_midline(diaphragm_p_4trough, min_distance=ratio × x_dim)
   → crossings, rise_or_decline
2. 依 crossings 數量分批（>2 → 拆 2 個一組）
3. 每批 excursion_rule(crossings, rise_or_decline, p_4trough, start_range, end_range)
   → selected_troughs / selected_crest (x indices)
4. find_boundary(diaphragm_mask, selected_x/y crest/trough)
   → crest_position / trough_position (peak 位置修正後 (x, y))
5. 組裝 List[ExcursionBatch]
```

#### `compute_peak_info()`

| 輸入 | 輸出 |
|---|---|
| `crest`, `trough`, `scale_y`, `scale_x` | `PeakInfo`（含 `excursion_pixel` / `excursion_cm` / `time_pixel` / `time_sec` / `velocity`） |

- `scale_y=None` → `excursion_cm=None`
- `scale_x=None` 或 `time_pixel=0` → `time_sec=None`
- `time_sec=0` 或 `excursion_cm=None` → `velocity=None`

main.py excursion phase **不傳 scale_x** → `time_sec / velocity` 為 None；只計算 `excursion_cm`。

#### 設計重點

- **midline + rules**：用「平均線交叉」找 peak/trough；比直接 find_peaks 更穩
- **boundary refine**：用 segment mask 修正 peak 位置（避免 wavelet 平滑後 peak 偏離真實邊界）
- **None guard**：所有物理量 None-safe；不 div-by-zero crash

---

### §4.6 `multiframe/`（Step 10）

| 維度 | 內容 |
|---|---|
| **檔案** | `frame_selection.py`（`get_legacy_frame_indices` / `get_keyframe_indices` / `_phase_correlate_keyframes` stub）；`global_window.py`（待 Patch 11B） |
| **入口** | dispatch helpers，main.py 依 `MultiframeConfig.mode` 走分支 |
| **依賴 config** | `MultiframeConfig`（mode / strategy / keyframe_indices / stride / `stitch_length_px`） |

#### Modes（三選一）

| Mode | 行為 | 落地 |
|---|---|---|
| `LEGACY` | per-frame loop（**default**，等同舊 main.py 行為） | ✅ 11A + 11C-LEGACY；`legacy_frame_indices` 過濾生效 |
| `GLOBAL_WINDOW` | 抽 2 keyframe → 拼接 → 全局 excursion | ✅ 11B 邏輯（`run_global_window`）；⬜ 11C-GW main.py 整合 |
| `REALTIME` | shift_x 累加 + partial window 即時更新 | ⬜ 探索階段 |

#### Keyframe Strategies（GLOBAL_WINDOW 用）

| Strategy | 來源 | 落地 |
|---|---|---|
| `FIXED_INDICES` | `cfg.keyframe_indices`（**default** `[87, 149]`） | ✅ |
| `PHASE_CORRELATE` | `_phase_correlate_keyframes(seq, cfg)` 累加位移算 | ⬜ stub（user 自補） |

#### 設計取向

- multi-frame 是「組合既有 single-frame 結果」的 orchestrator，**可依賴**其他 algorithm sub-packages（excursion / motion_curve / roi_band）；這是 algorithm 內部跨 sub-package import 的唯一例外（per ARCHITECTURE.md §4）
- Mode dispatch 走 `MultiframeConfig.mode` enum 而非條件字串，避免 typo

---

### §4.7 `signal_processing/`

| 維度 | 內容 |
|---|---|
| **檔案** | `stable_peak.py`（`wavelet_denoising` + 多個 stable section helpers） |
| **入口** | `from algorithm.signal_processing import wavelet_denoising` |

#### `wavelet_denoising(signal, wavelet='db4', level=5)`

低頻趨勢提取：
```
coeffs = pywt.wavedec(signal, wavelet, level=level)
coeffs[1:] = 0   # 只保留近似係數
trend = pywt.waverec(coeffs, wavelet)
return trend[:len(signal)]
```

#### 其他 helpers（保留，當前未使用）

- `select_stable_section` / `align_peak` / `Connect_breakpoints` 等
- 設計為未來「stable section 分析」預留；目前 dead but reserved（per CLAUDE.md §3 不刪「看起來沒用」code）

---

## §5 依賴方向

### Imports（algorithm 內）

```
diaphragm_detection → signal_processing (curve_fit 用 wavelet_denoising)
motion_curve        → signal_processing (extract 用 wavelet_denoising)
excursion           → (無內部 algorithm 依賴；只用自己的 helper)
roi_band            → diaphragm_detection (enhanced_search 內 detect)
multiframe          → motion_curve + roi_band + excursion + signal_processing (orchestrator)
segmentation        → paddleseglibs (vendored)
```

### Config 依賴

每 sub-package 依賴**對應**的 cfg；不依賴其他 layer 的 cfg：

| sub-package | 依賴 config |
|---|---|
| segmentation | `PaddleSegSegmenterConfig` |
| diaphragm_detection | `DiaphragmDetectionConfig` |
| roi_band | `RoiBandConfig`（含 `use_segment_label`） + `DiaphragmDetectionConfig` |
| motion_curve | `MotionCurveConfig` |
| excursion | `ExcursionConfig` |
| multiframe | `MultiframeConfig` + `ExcursionConfig`（global_window 用） |
| signal_processing | （無）|

### 被誰依賴

```
visualization → algorithm   (讀 result types)
main.py       → algorithm   (orchestration)
```

---

## §6 待辦與已知限制

| 項目 | 範圍 | 狀態 |
|---|---|---|
| Multi-frame Mode 1 拼接 | `multiframe/global_window.py` 11B 待落地 | 設計 backup 已寫 |
| Multi-frame Mode 2 (REALTIME) | partial window handling 設計 | 探索階段 |
| `_phase_correlate_keyframes` stub | user 自補 | open |
| Multi-frame DCM 存檔覆蓋 bug | `paddleseglibs/paddleseg/core/predict.py` 內檔名不含 frame index | 暫不修（測試流程不依賴存檔） |
| `prune_branch_max_length` 是否該 ratio 化 | `diaphragm_detection.curve_fit` | 暫不動（length 與 image dim 關係模糊）|
| Sniff phase 用 `segment_way` | excursion 內未實作 sniff 路徑 | （不在此 doc 範圍） |

---

## §7 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§6 全部章節定義；7 sub-package 依 pipeline 順序拆 §4.1-§4.7 | 文件化專案，深入 algorithm 內部 |
| 2026-05-25 | — | §4.3 / §5 cfg 引用：`RunConfig.use_segment_label` → `RoiBandConfig.use_segment_label` | Patch 12A：RunConfig 已刪 |
| 2026-05-25 | — | §4.6 LEGACY 標 ✅ 11A + 11C-LEGACY；GLOBAL_WINDOW 改 11C-GW | Patch 11C-LEGACY 落地 |
| 2026-05-25 | — | §4.6 GLOBAL_WINDOW 邏輯標 ✅ 11B；keyframe default `[87, 149]` | Patch 11B 邏輯落地 |
