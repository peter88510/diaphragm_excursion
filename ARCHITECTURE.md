# ARCHITECTURE.md — diaphragm_excursion 系統架構

> 跨層架構、模組責任、依賴方向、關鍵 dataclass 與設計決策紀錄。
> 演算法逐步流程見 [`docs/pipeline.md`](docs/pipeline.md)（待建）；各 module 內部設計見 `docs/modules/*`（待建）。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 接手工程師、AI agent、回顧設計決策 |

---

## §1 設計目標與原則

| 原則 | 落實 |
|---|---|
| **可讀性 > 聰明度 > 效能** | dataclass + named arg；不寫 5-tuple；不過度抽象 |
| **最小修改** | patch-first 開發；不順便重構；既有 fallback 預設保留 |
| **跨層單向依賴** | 嚴格 visualization → algorithm → config；algorithm 不可反向 |
| **演算法層零副作用** | 不寫 `cv2.imshow` / `plt.show` / module-level state mutation |
| **Config-driven** | 所有可調參數進 dataclass config；不在 algorithm 內 hardcode |
| **Size-aware** | size-sensitive 參數用 ratio（pixel ÷ canonical 尺寸），不寫死 |
| **醫療系統強約束** | 量測精度第一；不靜默改變物理量計算 |

---

## §2 架構總覽

```
main.py
  │  (orchestration: per-frame loop / multi-frame dispatch)
  │
  ├── input/             DCM/PNG → FrameSequence
  │
  ├── algorithm/         per-frame & multi-frame pipeline
  │     ├── segmentation/         paddle 預測 → seg mask
  │     ├── diaphragm_detection/  mask + 古典法 → DetectionResult
  │     ├── roi_band/             y_band 擴張 + enhanced search → RoiSearchResult + TargetSelection
  │     ├── motion_curve/         軌跡擷取 + wavelet → MotionCurveResult
  │     ├── excursion/            peak/trough + 物理量 → ExcursionResult + PeakInfo
  │     ├── multiframe/           Multi-frame mode dispatch (Step 10)
  │     ├── signal_processing/    wavelet 等通用工具
  │     └── frame_result.py       FrameResult (per-frame 結果聚合)
  │
  ├── config/            per-layer dataclass configs
  │
  └── visualization/     debug per-stage + final overlay (兩條獨立 track)
```

主流程在 `main.py` 內 per-frame 迴圈：
`load → apply_dicom_crop → segment → detect → compute_y_band → enhanced_search → select → motion_curve → brightness_way → compute_peak_info → render_frame`

---

## §3 模組責任

| Top-level | 責任 | 對外型別 / 入口 |
|---|---|---|
| `input/` | DCM single / multi、PNG file / dir 讀取 + 統一格式 | `load(path) → FrameSequence`、`apply_dicom_crop()` |
| `algorithm/segmentation/` | PaddleSeg 模型 lazy load + predict | `PaddleSegSegmenter.predict(image_path, dcm_array) → PIL Image` |
| `algorithm/diaphragm_detection/` | 古典切割 / paddle mask → 找橫膈膜 ROI | `detect(image, cfg, use_segment) → DetectionResult` |
| `algorithm/roi_band/` | y_band 擴張 / 強化 / 第二次 detect / target 選定 | `compute_target_y_range()`、`enhanced_search()`、`select_target()` |
| `algorithm/motion_curve/` | 逐 x 抓最亮 peak + 補斷點 + wavelet 平滑 | `extract_motion_curve(image, y_range, cfg) → MotionCurveResult` |
| `algorithm/excursion/` | midline / find_peaks / boundary refine / 物理量 | `brightness_way()`、`compute_peak_info()` |
| `algorithm/multiframe/` | Multi-frame 模式（LEGACY / GLOBAL_WINDOW / REALTIME）dispatch | `get_legacy_frame_indices()`、`get_keyframe_indices()`、`run_global_window()`（待） |
| `algorithm/signal_processing/` | wavelet / skeleton helpers | `wavelet_denoising()` |
| `config/` | 全部 dataclass config + enum | `<Name>Config`、`Phase` / `MultiframeMode` / `KeyframeStrategy` |
| `visualization/` | debug per-stage + final overlay | `PipelineVisualizer.render_frame()` |
| `paddleseglibs/` | vendored PaddleSeg（含 Patch 2A-2C 改動） | 透過 `algorithm/segmentation/` 用 |

---

## §4 跨層方向與依賴規約

### 單向依賴

```
main.py     → input
main.py     → algorithm
main.py     → config
main.py     → visualization

visualization → algorithm   (讀 result type)
visualization → input       (讀 FrameSequence)
visualization → config      (讀 VisualizationConfig 等)

algorithm/*   → config       (讀 對應 cfg)
algorithm/*   → algorithm/signal_processing  (wavelet)
algorithm/multiframe → algorithm/excursion + motion_curve + roi_band

config/* → (none)            config 是 leaf
```

### 禁止

| 禁忌 | 原因 |
|---|---|
| `algorithm → visualization` | algorithm 應無 viz 副作用；viz 是消費者不是生產者 |
| `config → algorithm / input / visualization` | config 是 leaf；不可向業務層循環依賴 |
| Sibling algorithm sub-packages 互相 import（除 multiframe / signal_processing 例外） | 避免 spaghetti；走 main.py 串接 |

### 例外與理由

- `algorithm/multiframe/` **可**依賴其他 algorithm sub-packages：因 multi-frame 是「組合既有 single-frame 結果」的 orchestrator
- `algorithm/signal_processing/` **可**被任意 algorithm 子模組依賴：wavelet 是通用工具

---

## §5 關鍵 dataclass

### Input 層

| 型別 | 位置 | 欄位 |
|---|---|---|
| `FrameSequence` | `input/frame_sequence.py` | `frames` `(N,H,W)` or `(N,H,W,3)`、`source_type`、`source_path`、`fps`、`metadata` |

### Algorithm 層（per-stage results）

| 型別 | 位置 | 主要欄位 |
|---|---|---|
| `DetectionResult` | `algorithm/diaphragm_detection/detector.py` | `best_region`、`filtered_binary`、`target_binary`、`potential_binary`、`debug_overlay` |
| `RoiSearchResult` | `algorithm/roi_band/enhanced_search.py` | `detection`、`enhanced_band`、`enhanced_padded`、`padded_mask`、`padded_overlay` |
| `TargetSelection` | `algorithm/roi_band/target_selection.py` | `target_binary`、`diaphragm_mask`、`overlay`、`padding_output`、`source` |
| `MotionCurveResult` | `algorithm/motion_curve/extract.py` | `init_diaphragm`、`broken_indices`、`smoothed_trough/crest`、`diaphragm_p_trough/crest` |
| `ExcursionResult` | `algorithm/excursion/brightness.py` | `batches: List[ExcursionBatch]`、`crossings`、`rise_or_decline` |
| `ExcursionBatch` | 同上 | `crest_position`、`trough_position`、`selected_crest_x`、`selected_trough_x` |
| `PeakInfo` | `algorithm/excursion/measurement.py` | `crest`、`trough`、`excursion_pixel`、`excursion_cm`、`time_pixel`、`time_sec`、`velocity` |
| `FrameResult` | `algorithm/frame_result.py` | 整合上述（detection / y_band / refined / selection / motion_curve / excursion / measurements）|

### Multi-frame（Step 10）

| 型別 | 狀態 |
|---|---|
| `GlobalExcursionResult` | 設計 backup 在 `docs/notes/patch_11b_design_backup.md` |

### Config 層

| 型別 | 位置 | 用途 |
|---|---|---|
| `PaddleSegSegmenterConfig` | `config/paddleseg_config.py` | paddle 模型路徑 / 設定 |
| `DiaphragmDetectionConfig` + `Phase` | `config/diaphragm_detection_config.py` | detection 參數 + phase 切換 |
| `RoiBandConfig` | `config/roi_band_config.py` | y_band reserve_ratio + enhanced search 參數 |
| `MotionCurveConfig` | `config/motion_curve_config.py` | jump / fix_search ratio + wavelet level |
| `ExcursionConfig` | `config/excursion_config.py` | peak find / midline / excursion_rule 參數 |
| `VisualizationConfig` | `config/visualization_config.py` | viz 開關 + final overlay 元素 toggle |
| `MultiframeConfig` + `MultiframeMode` + `KeyframeStrategy` | `config/multiframe_config.py` | Multi-frame 模式 + keyframe 抽取策略 |
| `RunBundle` | `config/run_bundle.py` | 聚合 root cfg；含 `for_phase(phase)` classmethod |

---

## §6 設計決策紀錄

### §6.1 dataclass over dict / tuple

**選擇**：所有跨函式結構化資料用 `@dataclass`。

**理由**：
- type safety（IDE 補全 + 型別檢查可用）
- refactor friendly（rename 欄位有 IDE 支援；dict key rename 是字串搜尋）
- 避免 5-tuple 回傳的可讀性災難（原 codebase 有過 `return a, b, c, d, e`）

**取捨**：dataclass 比 dict 多一些 boilerplate；本 repo 認為值得。

### §6.2 Config-driven over hardcoded

**選擇**：所有可調參數都放 `config/` 內 dataclass，函式接 cfg 參數。

**理由**：
- 測試時 override 不需動 algorithm 程式碼
- 不同 phase / mode 用不同 cfg 實例
- algorithm 層保持「演算法邏輯」純淨，不夾雜「特定參數值」

**例外**：純常數（如 morphological kernel size 5、intensity threshold 38）若不會跨環境變動，可保留 hardcode 在演算法層內。

### §6.3 Ratio over fixed pixel (Step 9)

**選擇**：size-sensitive 參數一律用 `image_dim × ratio` 計算 pixel 值，不寫死 pixel。

**理由**：
- 原 codebase 假設 single-frame DCM 永遠 1500×955；違反任何尺寸就行為偏差
- ratio 讓相同演算法套用任意尺寸影像

**精度**：default 用 fraction form `100 / 955`，caller 用 `round()` 換算回 pixel（不是 `int()`，避免 truncation off-by-one）。

**例外**：intensity threshold / morphological kernel / wavelet level 等與 image 尺寸無關的不 ratio 化。

詳細參數轉換對照見 [`docs/notes/size_normalization_pre_ratio_audit.md`](docs/notes/size_normalization_pre_ratio_audit.md)。

### §6.4 Algorithm 全 gray、Viz 用 as_color

**選擇**：
- algorithm 層 input 全部走 `seq.as_gray()` 灰階
- viz 層 final overlay base canvas 用 `seq.as_color()` 保留 DCM 原色標記

**理由**：
- algorithm 用灰階：強度單通道、threshold 邏輯乾淨、performance 較好
- viz 用彩色：DCM 可能含設備色彩標記（caliper、ROI 線）；viz 應保留原始呈現

### §6.5 Algorithm 層零副作用

**選擇**：algorithm 內**禁** `cv2.imshow` / `plt.show` / module-level `matplotlib.use()` / global state mutation。

**理由**：
- 原 codebase 內 `if DEBUG: cv2.imshow(...)` 散落各處，導致跑 150 frame 會 block 150 次
- algorithm 邏輯應無 IO；viz / log 是消費者

**落實**：所有 viz 集中在 `visualization/`；algorithm 只回傳 result type，由 viz 層自己畫。

### §6.6 三層文件 tier (CLAUDE.md §10)

**選擇**：STABLE / LIVING / SNAPSHOT 三層；版號策略依 tier 調整。

**理由**：
- 統一版號太緊（PROGRESS.md 每 patch 改一次，bump 麻煩）
- 完全棄用太鬆（SNAPSHOT 失去設計史追溯能力）
- 三層 + SNAPSHOT 版號雙軌（Last Updated 必 + semver 選）= 平衡

詳細格式規範見 [`docs/STYLE.md`](docs/STYLE.md)。

---

## §7 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§6 全部章節定義 | 文件化專案，提供 architecture 級設計參考 |
| 2026-05-25 | — | §5 Config 表移除 `RunConfig` 行、加 `RunBundle` 行 | Patch 12A：刪 RunConfig + 建 RunBundle |
