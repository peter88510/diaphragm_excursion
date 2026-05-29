# Refactor Progress Log

> 本文件記錄 diaphragm_excursion repo 的 patch-based 重構進度。
> 規則：每個 step 必須先說做法 → 工程師同意 → 才執行。

---

## 📌 整體目標

將既有混亂 codebase 模組化為兩層架構：
- **Input 層**：資料正規化（DICOM / PNG → FrameSequence）
- **Algorithm 層**：核心演算法（segmentation / tracking / excursion ...）

保留所有現有行為，不重寫邏輯。

---

## 🗺 Refactor Patch 計畫

### Step 1 — Review `paddleseglibs/predict.py`
- **狀態**：✅ 已完成
- **產出**：Review report（介面契約、耦合點、可抽出範圍、SegmenterBase 草案）
- **關鍵發現**：
  - `parse_args()` 在 library 內被呼叫，污染 sys.argv
  - 每次 `infer()` 都重新 load model weights（效能問題）
  - 內部 `predict()` 有強制存檔副作用
  - 回傳 PIL Image (mode=P, palette)，原樣保留不動

### Step 2 — 抽出 `SegmenterBase` + `PaddleSegSegmenter`
- **狀態**：🚧 進行中
- **拆解為 4 個 sub-patches**：
  - **Patch 2A**：`paddleseg/core/predict.py` 加 `skip_model_load` 參數（向後相容）— ✅ 完成
  - **Patch 2B**：`paddleseglibs/predict.py` 拆 `build_predictor()` + `predict_one()`，保留 `infer()` compat — ✅ 完成
  - **Patch 2C**：副作用控制 + config 入口（合併執行）— ✅ 完成
    - 2C-1：`paddleseg/core/predict.py` 加 `save_predictions` 參數
    - 2C-2：`paddleseglibs/predict.py` 串接 `save_predictions`
    - 2C-3：新增 `config/paddleseg_config.py`（`PaddleSegSegmenterConfig` dataclass）
  - **Patch 2D**：新增 `algorithm/segmentation/{base.py, paddleseg_segmenter.py}` — ✅ 完成
- **決定事項（已確認）**：
  - `parse_args()` 在 wrapper 完全跳過
  - 採選項 B：小改 paddleseglibs，輸出需與原先 byte-identical
  - Mask 型別不動，維持回傳 PIL Image (mode=P)
  - `predict()` 介面採選項 1：`(image_path, dcm_array=None)`
  - 驗證 script 放 `experiments/`
  - 教學筆記放 `docs/notes/`
  - 每個 sub-patch 做完都停下來給工程師看

### Step 3 — Input 層獨立（含 multi-frame 支援）
- **狀態**：🚧 進行中
- **觸發**：multi-frame DCM 用例破壞「以檔案為單位」的舊設計
- **目的**：把 input 邏輯全部移出 main.py、支援 single/multi DCM + PNG 單檔/資料夾
- **拆解為 6 個 sub-patches**：
  - **Patch 3A**：`input/frame_sequence.py`（FrameSequence dataclass + as_gray/as_color）— ✅ 完成
  - **Patch 3B**：`input/readers/dicom_reader.py`（內部偵測 single/multi frame）— ✅ 完成
  - **Patch 3C**：`input/readers/png_reader.py`（單檔 + 資料夾）— ✅ 完成
  - **Patch 3D**：`input/loader.py`（對外入口 `load(path)`）— ✅ 完成
  - **Patch 3E**：`input/preprocessing/dicom_crop.py`（修 multi-frame bug）— ✅ 完成
  - **Patch 3F**：改 `main.py` 變成乾淨 orchestration — ✅ 完成
- **決定事項（已確認）**：
  - frames 統一 (N, H, W) 或 (N, H, W, 3) — N 維永遠存在
  - 通道轉換用 `.as_gray()` / `.as_color()` method
  - DCM single/multi 合在一個 `dicom_reader.py` 內部判斷
  - Metadata 用 dict
  - 每個 sub-patch 做完都停下來

### Step 4 — Diaphragm detection layer
- **狀態**：🚧 進行中
- **角色**：segmenter 之後、excursion 主算法之前。從 raw image + seg mask 找出橫膈膜 ROI
- **拆解為 6 個 sub-patches**：
  - **Patch 4A**：`config/diaphragm_detection_config.py`（Phase enum + Config）+ algorithm 骨架 — ✅ 完成
  - **Patch 4B**：`algorithm/diaphragm_detection/classical.py`（gamma + level + algo_segmentation）— ✅ 完成
  - **Patch 4C**：`algorithm/diaphragm_detection/curve_fit.py`（skeleton + prune + fit + score）— ✅ 完成
  - **Patch 4D**：`algorithm/diaphragm_detection/candidate.py`（connected components 篩選）— ✅ 完成
  - **Patch 4E**：`algorithm/diaphragm_detection/detector.py`（主入口 detect() + DetectionResult）— ✅ 完成
  - **Patch 4F**：整合進 main.py，評估刪除 patch_code.py / diaphragm_curve_fit.py — ✅ main.py 已更新；patch_code.py / diaphragm_curve_fit.py 刪除待用戶確認
- **決定事項（已確認）**：
  - Layer 命名 `algorithm/diaphragm_detection/`
  - 結構：扁平 5 檔
  - Config 用 Phase enum + DiaphragmDetectionConfig，跟 paddleseg_config 同級放 `config/`
  - DetectionResult 是 algorithm 輸出型別，放 algorithm 內（4E）
  - `stable_peak.py` 暫不動位置（root），curve_fit.py 直接 import

### Step 5 — ROI band（detect 後、excursion 前的 ROI 擴張與精煉）
- **狀態**：🚧 Patch 5A + 5B 完成
- **角色**：detect() 找出 (top, bottom) 之後、excursion 主算法之前的小過程鏈
- **Patch 5A**（已完成）：
  - 新建 `algorithm/roi_band/y_range.py`（`compute_target_y_range`）
  - 新建 `config/roi_band_config.py`（`RoiBandConfig`）
  - 修原 y_dim=955 寫死的隱性 bug
  - 刪除 `diaphragm_curve_fit.py`
- **Patch 5B**（已完成）：
  - 新建 `algorithm/roi_band/enhancement.py`（`enhance_band`）
  - 新建 `algorithm/roi_band/enhanced_search.py`（`RoiSearchResult` + `enhanced_search`）
  - `RoiBandConfig` 擴充：`enhance_num_segments`、`enhance_blur_kernel`
  - main.py 加入第二次 detect（second pass via enhanced_search）
  - 第二次 detect 用 `dataclasses.replace` 內部覆寫 `filter_top_rows=0`、`median_blur=False`，不污染外部 config
  - 解決原版兩次 detect_diaphragm 散落變數命名問題 → 用 `RoiSearchResult` dataclass 統一
- **Patch 5C**（已完成）：
  - 新建 `algorithm/roi_band/target_selection.py`（`TargetSelection` + `select_target`）
  - 新建 `config/run_config.py`（`RunConfig`，pipeline 層 toggles）
  - `RoiSearchResult` 加 `enhanced_padded` 欄位
  - main.py 加入 select_target 呼叫（4e 步驟）
  - **不引入 ImageStore** —— 用 dataclass + 結構化 result 取代 mutable global container
- **預留**：未來「迭代搜索」loop 預計擴充此模組

### Step 6 — Excursion 主算法（motion curve + brightness_way + measurement）
- **狀態**：🚧 Patch 6 + 7 + 8 完成（Patch 8 待用戶實機驗證）
- **角色**：select_target 之後正式進入 excursion 主算法
- **Patch 6**（已完成）：motion curve 抽取（extract_motion_curve + MotionCurveResult + MotionCurveConfig）
- **Patch 7**（已完成）：brightness_way（peak/trough 偵測 + segment 修邊界）
- **Patch 8**（已完成）：peak info 物理量計算
  - 新建 `algorithm/excursion/measurement.py`（`PeakInfo` + `compute_peak_info`）
  - `FrameResult` 加 `measurements: List[PeakInfo]` 欄位
  - 取代原 `peaks_info_dict` 巢狀 dict（type-safe + 多 batch 支援）
  - 取代原 `excursion_time_calculator` 5-tuple；velocity div-by-zero 安全（返 None）
  - 移除 `print("[][][] SCALE Y...")` 150 frame 噪音
  - Excursion phase 在 main.py 不傳 scale_x → 限制不輸出 time / velocity（與用戶要求一致；sniff phase 才會傳 scale_x）
  - **不引入 test_info dict** —— 跨 frame 撈用 `results: List[FrameResult]` 直接 index
  - 新建 `algorithm/excursion/`：`midline.py` / `rules.py` / `boundary.py` / `brightness.py`
  - 新建 `config/excursion_config.py`（`ExcursionConfig`）
  - 新建 `algorithm/frame_result.py`（`FrameResult` dataclass，取代 main 內逐漸膨脹的 tuple）
  - `MotionCurveConfig` 拆 `wavelet_level_trough` / `wavelet_level_crest`（保留分化接口）
  - 移除 `matplotlib.use('TkAgg')` module-level 副作用
  - `args.mode == "debug"` → `debug: bool` 參數；`x_dim` → 內部 `len(...)` 推導
  - 7-tuple 回傳改 `ExcursionResult`（含 `ExcursionBatch` list）
  - `utils.FindBoundary` → `algorithm/excursion/boundary.py`（typo `ctest` → `crest`）
- **預期未來 patches**：sniff 路徑（segment_way，會傳 scale_x → time/velocity 啟用）、stable section、cross-frame 合併分析（從 150 frame 中挑 2 frame 接波形信號值再跑一次 excursion）

### Step 7 — Visualization 統整
- **狀態**：✅ 完成
- **動機**：原 codebase viz 散落在主流程 `if DEBUG: ...` 內，CLAUDE.md §七 要求 viz 獨立 module
- **拆解為 5 個 sub-patches**：
  - **Patch 9A**：`config/visualization_config.py`（`VisualizationConfig` + `debug_stages` toggle）+ `visualization/__init__.py` / `stages.py` / `io.py` 骨架 — ✅ 完成
  - **Patch 9B**：抽 detection viz；移除 `DiaphragmDetectionConfig.visual` 欄位、`detector.py` 的 cv2.imshow、`curve_fit.py` 的 plt.show 與 matplotlib import；新增 `visualization/layers/{segmentation, detection}.py` — ✅ 完成
  - **Patch 9C**：抽 ROI band viz；新增 `visualization/layers/roi_band.py`（y_band overlay + enhanced_padded） — ✅ 完成
  - **Patch 9D**：抽 motion_curve / excursion / detection_pass2 viz；移除 `brightness.py` 的 `debug` 參數、plt 段、matplotlib/find_peaks import；新增 `visualization/layers/{motion_curve, excursion}.py`（excursion 用 `Figure + FigureCanvasAgg` 不碰全域 backend） — ✅ 完成
  - **Patch 9E**：`PipelineVisualizer` 主入口 + main.py 整合 + legacy 刪除（`patch_code.py` / `excursion_rule.py` / `debug.py` / `stable_peak.py` 內 `edge_motion_curve` + `mask_edge_motion_curve` 兩支死函式）；`stable_peak.py` 搬到 `algorithm/signal_processing/`（保留 helpers 給未來 stable section 用） — ✅ 完成
  - **Patch 9F**：`info_display.py` 搬到 `visualization/` + 重構（修 label 位置 bug、font scale 一致化、PIL 轉換合併、常數抽出、加 type hints）；`PipelineVisualizer._render_final` 改用 `as_color` 為 base canvas + 呼叫 `excursion_info_display`；`VisualizationConfig` 加 `final_font_path` — ✅ 完成
- **決定事項（已確認）**：
  - 兩條獨立 track：final overlay（綜合成果圖）與 debug per-stage（不混用）
  - 預設 `enabled=False`，production 零副作用
  - debug 路徑：`output/debug/{stage}/{i:04d}.png`；final 路徑：`output/final/{i:04d}.png`
  - 檔名內嵌 stage（不在圖內加 putText 標題條）
  - Final 內容：crest/trough 標記 + excursion_cm 文字 + motion curve 軌跡（debug 用）
  - 文字疊加用 cv2.putText（英數）
  - matplotlib 用 `Figure + FigureCanvasAgg`，不動全域 backend
  - `stable_peak.py` 內 dead helpers 保留（未來 stable section 重用）

### Step 8 — Step 2 驗證收尾（**暫緩**）
- **狀態**：⬜ 暫緩
- **理由**：用戶選擇先重整 main 入口、自行 debug；必要時再回頭寫驗證 script

### Step 9 — Size Normalization Audit（**已完成**）
- **狀態**：✅ 完成（2026-05-23 ~ 05-24）
- **動機**：許多演算法參數歷史上 hardcode 在 single-frame DICOM `1500 × 950` 尺寸；部分已 ratio 化但未全面盤點
- **落地 patch**：
  - **Patch 10A**：盤點 + 撰寫 `docs/notes/size_normalization_pre_ratio_audit.md`（SNAPSHOT）
  - **Patch 10B**：`motion_curve` jump_threshold / fix_search_window ratio 化
  - **Patch 10C**：`excursion` peak_min_distance / midline_min_distance ratio 化
- **驗證結果**：1500×955 ref 尺寸下逐 pixel 等價舊 hardcode（round 還原）；2026-05-25 實機驗證通過
- **連動 Patch 13C**：`visualization/info_display.py` 全 px / scale 改 height-ratio（ref 1500×955）；統一 ratio 化原則
- **連動議題**：
  - **Multi-frame resize 決策**：是否將 multi-frame 統一 resize 至 1500×950？
    - Pros：single/multi 共用一套 pipeline、降低參數維護成本、tracking/ROI 一致
    - Cons：physical pixel spacing 失真、excursion physical distance 需推算回真實尺寸
  - **Visualization output resize**：是否讓 viz 輸出可獨立 resize（demo / realtime 用）？
    - 必須與 algorithm processing size **嚴格分離**，避免 viz resize 汙染核心計算

### Step 10 — Multi-frame Excursion 模式擴充（**已完成**）
- **狀態**：✅ 三 mode 全部落地並實機驗證
- **本質**：multi-frame = 多次 single-frame 結果組合
- **拆解為兩種模式**：

#### 模式狀態總覽

| Mode | 整合進度 | 對應 patch |
|---|---|---|
| `LEGACY` | ✅ 已整合進 main.py | 11A（cfg） + 11C-LEGACY（main 接 `legacy_frame_indices`） |
| `GLOBAL_WINDOW` | ✅ 主流程已落地 | 11B（拼接邏輯）+ 11B'（兩段獨立）+ 11C-GW（main 整合）+ 11D（global final viz） |
| `REALTIME` | ✅ 端到端落地 + 實機驗證 | 14A-18（見下 Step 11 表）|

#### 模式一：Global Window 拼接
- **目的**：固定視窗策略建立完整 global signal，套既有 excursion 演算法
- **已知條件**：
  - 視窗約 88 frames（理想無 delay 時，前後 frame 位移約 8 pixel）
  - 剩餘視窗：62 frames ≈ 496 pixel 位移
- **流程**：擷取 frame 88 與 frame 149 → 各跑 single-frame 演算法 → frame 149 後半 496 pixel 訊號拼接至前段 → 形成 global signal → 套 excursion 演算法
- **依賴**：Step 9 size normalization 完成度（拼接需 size 一致）

#### 模式二：Real-time Incremental（**已落地** 14A-18）
- **目的**：模擬 real-time 演示；frame 持續輸入時即時更新 excursion
- **落地設計**：
  - frame[0] 探頭起始跳過；frame[i] 取右尾 `shift_px`（estimate_shift 變動位移）累積
  - 累積 width = Σ shift_px（非固定 stride）；每 N 幀整段 buffer 重做 wavelet 消邊界 artifact
  - 雙層門檻：`realtime_warmup_frames`（UX）+ `realtime_algorithm_min_width`（安全網）
  - ShiftStrategy：TEMPLATE_MATCH（整數，default）/ PHASE_CORRELATE（float）/ FIXED；`shift≤0` 或低信心跳過 ingest
  - 雙 track viz：canvas（frame[i] 底 + global 軌跡右錨定 + 累積邊界虛線）/ global（完整累積）
  - `RealtimeState.ingest_frame` 為 streaming-ready 接口（未來接真實 stream 只換來源）
  - **分層 cadence（Patch 19A，省 paddle）**：estimate_shift 前移→無效幀跳過不跑 paddle；heavy（paddle 全 pipeline）僅 bootstrap / 峰觸發（piggyback brightness_way crest/trough x）/ 距上次 ≥ `realtime_seg_refresh_max_n`；其餘 light（沿用 cached y_band 只跑 motion_curve）。mask 採 refresh-recent（heavy 整張 frame mask 右對齊覆蓋 buffer 最右 ~frame_width 欄）；`ingest_frame` decouple 成吃 `(motion_curve, ..., full_mask)`
- **待續（未來）**：phase_correlate 實作精修；多 peak aggregator 聚合規則；真實 stream adapter

### Step 11 — Cfg 精煉與 ratio 化擴展（**進行中**）

整合零碎改進；每個 patch 獨立 commit。

| Patch | 主題 | 狀態 |
|---|---|---|
| 12A | 刪 `RunConfig` + 建 `RunBundle`；`use_segment_label` 搬至 `RoiBandConfig` | ✅ |
| 13A | 抽 `DicomCropConfig`；`apply_dicom_crop(seq, cfg)` 強制吃 cfg | ✅ |
| 13C | `algorithm/excursion/aggregator.py` stub；`info_display` 全 px 改 height-ratio + 多 peak markers + 簽名改吃 `List[PeakInfo]` | ✅ |
| 14A | `RealtimeState` 純右尾累積 + 雙層門檻 + wavelet refresh | ✅ |
| 14B | REALTIME viz 雙 track（canvas + global）+ warmup 文字 | ✅ |
| 14C | main.py REALTIME dispatch + `_run_realtime` | ✅ |
| 15 | 統一 config 入口 `run_config.py`（gitignored）+ `run()` 注入 bundle | ✅ |
| 16 | `frame_shift.py` 變動位移估計（取代固定 stride）；`ShiftStrategy` | ✅ |
| 17 | canvas 改右錨定滑動視窗（base=frame[i] + global 軌跡最右段）| ✅ |
| 18 | `rt_show_*` 開關 + 累積邊界洋紅虛線 + viz config 文件化 | ✅ |
| — | 刪 `utils.py`（4 函式已被分層模組取代）+ 兩支實驗檔移除 | ✅ |
| 19A | REALTIME 分層 cadence（estimate_shift 前移 + heavy/light + refresh-recent mask）| ✅ |
| 19 timing | REALTIME per-stage 計時 instrumentation（Layer A 每幀 / B heavy / C detect_roi / D detect 內部）| ✅ |
| 20A+20B | detect 優化：curve_fit ROI-crop（byte-identical）+ `curve_fit_maxfev` 10M→5000 | ✅ |
| docs | SNAPSHOT 同步：api_reference 0.8→0.9 / pipeline 分層 cadence / INDEX | ✅ |

**Patch 13B（取消）**：原計畫把 paddle model 路徑搬出 `paddleseglibs/predict.py`；發現 `PaddleSegSegmenterConfig` 已將 `config_path / model_path / save_dir` 暴露為欄位，user 可直接 override，預設值放哪不影響使用體驗。

---

## ✅ 已完成

- Step 1：Review `paddleseglibs/predict.py`
- Step 2 — Patch 2A：`paddleseg/core/predict.py` 加 `skip_model_load`
- Step 2 — Patch 2B：`paddleseglibs/predict.py` 拆 `build_predictor` + `predict_one`
- Step 2 — Patch 2C：`save_predictions` 副作用旗標 + `config/paddleseg_config.py`
- Step 2 — Patch 2D：`algorithm/segmentation/{base.py, paddleseg_segmenter.py}`
- Step 2 — 教學筆記：`docs/notes/model_load_caching.md`
- Step 2 — 驗證 script：`experiments/verify_segmenter_equivalence.py`（**尚未實測執行**）
- Step 3 — Input 層獨立：FrameSequence + readers + loader + dicom_crop + main 重寫
- Step 4 — Diaphragm detection layer：config + classical + curve_fit + candidate + detector + main 整合
- Step 5 — Patch 5A：ROI band y_range + main 整合 + 刪除 `diaphragm_curve_fit.py`
- Step 5 — Patch 5B：enhance_band + enhanced_search（第二次 detect via classical）+ RoiSearchResult
- Step 5 — Patch 5C：TargetSelection + select_target + RunConfig（取代 ImageStore）
- Step 6 — Patch 6：motion_curve（extract_motion_curve + MotionCurveResult + MotionCurveConfig）
- Step 6 — Patch 7：brightness_way + excursion module + ExcursionConfig + FrameResult + MotionCurve wavelet 拆分
- Step 6 — Patch 8：PeakInfo + compute_peak_info + FrameResult.measurements（取代 peaks_info_dict / test_info）
- Step 7 — Patch 9A：VisualizationConfig + visualization/{__init__, stages, io}.py 骨架
- Step 7 — Patch 9B：detection viz（移除 algorithm 層 cv2.imshow / plt.show / config.visual）
- Step 7 — Patch 9C：ROI band viz（y_band overlay + enhanced_padded）
- Step 7 — Patch 9D：motion_curve + excursion + pass2 viz（移除 brightness.py 的 debug/plt/matplotlib）
- Step 7 — Patch 9E：PipelineVisualizer + main 整合 + 刪 patch_code/excursion_rule/debug；stable_peak 搬到 algorithm/signal_processing/
- Step 7 — Patch 9F：info_display.py 搬入 visualization/ + 重構修 2 bug；final overlay 改用 as_color base + excursion_info_display
- Step 7 — Patch 9G：Final overlay 元素 toggles（motion_curve / peak_markers / excursion_text）；excursion_info_display 加 show_text 參數解耦
- Step 9 — Patch 10A：盤點 hardcode pixel constants → `docs/notes/size_normalization_pre_ratio_audit.md`
- Step 9 — Patch 10B：`motion_curve` jump_threshold / fix_search_window ratio 化
- Step 9 — Patch 10C：`excursion` peak_min_distance / midline_min_distance ratio 化
- Step 10 — Patch 11A：`MultiframeConfig` + `MultiframeMode` + `KeyframeStrategy` + frame_selection helpers
- Step 10 — Patch 11B / 11B'：`algorithm/multiframe/global_window.py`（拼接 + 全局 excursion；兩段獨立 stitching）
- Step 10 — Patch 11C-LEGACY：main.py mode dispatch；`legacy_frame_indices` 過濾生效
- Step 10 — Patch 11C-GW：main.py GLOBAL_WINDOW 整合（2 keyframe → 拼接 → 全局 excursion）
- Step 10 — Patch 11D：`visualization/global_window.py`（`render_global_final`）
- Step 11 — Patch 12A：刪 `RunConfig` + 建 `RunBundle`；`use_segment_label` 搬至 `RoiBandConfig`
- Step 11 — Patch 13A：抽 `DicomCropConfig`；`apply_dicom_crop(seq, cfg)` 強制吃 cfg
- Step 11 — Patch 13C：`aggregate_measurements` stub；`info_display` height-ratio 化 + 多 peak markers + 簽名改吃 `List[PeakInfo]`
- Step 10 — Patch 14A：`RealtimeState` 純右尾累積 + 雙層門檻 + wavelet refresh
- Step 10 — Patch 14B：REALTIME viz 雙 track（canvas + global）+ warmup 文字
- Step 10 — Patch 14C：main.py REALTIME dispatch + `_run_realtime`
- Step 11 — Patch 15：統一 config 入口 `run_config.py`（gitignored）+ `run()` 注入 bundle
- Step 10 — Patch 16：`frame_shift.py` 變動位移估計（`estimate_shift` / `ShiftStrategy` / `ShiftResult`）取代固定 stride
- Step 10 — Patch 17：canvas 改右錨定滑動視窗（base=frame[i] + global 軌跡最右段）
- Step 10 — Patch 18：`rt_show_*` 開關 + 累積邊界洋紅虛線 + viz config 文件化
- 清理 — 刪 `utils.py`（4 函式已被分層取代）+ `px_lv_shiftX.py` / `estimate_xshift.py` 實驗檔
- Step 10 — Patch 14D：SNAPSHOT docs 同步（api_reference 0.8 / pipeline / algorithm.md / INDEX）
- Step 10 — Patch 19A：REALTIME 分層 cadence（estimate_shift 前移 + heavy/light tier + refresh-recent mask；省 paddle，`ingest_frame` decouple 成 `(motion_curve, full_mask)`）
- Step 10 — Patch 19 timing：REALTIME per-stage 計時 instrumentation（Layer A 每幀 / B heavy 內部 / C detect_roi 分趟 / D detect 內部 op；duck-typed timing，None 零影響）
- 效能 — Patch 20A+20B：detect 優化（20A curve_fit per-candidate ops ROI-crop 到 y-band，byte-identical 已實證；20B `curve_fit_maxfev` 進 config，10M→5000）
- 文件 — SNAPSHOT 同步：api_reference 0.8→0.9 + pipeline 分層 cadence 段 + INDEX（Patch 19A + timing + 20B）
- 清理 — 移除 algorithm 層 per-frame/per-candidate debug print 噪音（classical / curve_fit / midline / rules / brightness）；保留 main.py 進度輸出與 REALTIME 每幀 log（純輸出清理，計算不變）

---

## 📝 待辦 / 後續 patch（先記下，不影響當前順序）

- [ ] **Patch 20B regression**：LEGACY mode 跑數張 frame，比對 `curve_fit_maxfev`=5000 vs 原 10M 的 `detection.best_region` / 選中 idx。20A 為 byte-identical（已實證）；20B 若某 frame 變動代表該擬合本需 >5000 evals，調高 `curve_fit_maxfev` 即可。順便重看 Layer D `curve_fit` ms 降幅
- [ ] **Patch 8 驗證**（下次 session 第一件事）：跑 `python main.py`，看 log 新增的 `excursion_cm=X.XX` 數值是否合理（橫膈膜 excursion 通常 1–7 cm）
- [ ] PNG path 的實際使用情境確認（目前可能是預留）
- [x] Multi-frame DICOM 支援 — Step 3 已處理（FrameSequence 首維永遠是 N）
- [ ] **Multi-frame DCM 存檔覆蓋 bug**（低優先）
  - 症狀：`save_predictions=True` 時，multi-frame DCM 的 N 個 mask 全部寫到同一個 PNG 檔（檔名由 DCM 檔案 basename 決定，不含 frame index）→ 結果互相覆蓋
  - 位置：`paddleseglibs/paddleseg/core/predict.py` 內 `os.path.splitext(im_file)[0] + ".png"` 那段
  - 根因：原 paddleseg 設計假設「一個 input path = 一張影像」，不知道 multi-frame
  - 暫不修：使用者測試流程不依賴存檔（mask 直接在記憶體傳給下游）
  - 將來修法：predict_one() 多接一個 `frame_index` 參數，存檔時嵌入到檔名（如 `_frame0042.png`）
- [x] `SequenceOfUltrasoundRegions[1]` 的 index `1` 確認 — 因 DCM 上半 B-mode、下半 M-mode；index 1 = M-mode（excursion 計算依據）
- [ ] PNG 預設的 `PhysicalDeltaY/X` 是哪台 ipad（需 config 化）
- [ ] PNG resize 目標尺寸 `(1500, 955)` 是否該對應到 input source（hardcode 風險）→ **併入 Step 9**
- [ ] `pil_image_to_cv2_gray` 應移至 segmenter 內部（呼叫端不該知道回傳是 PIL）
- [x] `stable_peak.py` 找適當位置 — 9E 已搬到 `algorithm/signal_processing/`，repo root 不再有此檔
- [ ] `area_ratio = 10000 / (955 * 1500)` 該重算為 image-relative（hotfix 餘毒）→ **併入 Step 9**
- [ ] `bresenham` pip 套件加進 requirements（之後盤點依賴時處理）
- [x] `docs/notes/model_load_caching.md` 補 SNAPSHOT header — 2026-05-24 完成（對齊 §10.2 雙軌 + STYLE.md §2）

---

## 🚧 開放問題（需工程師回答）

- [ ] PNG path 目前是否實際在用？影響 input 層是否要立刻處理多來源
- [x] `FrameSequence` 要先做還是等 multi-frame 進來再做 — Step 3 已落地，N 維永遠存在
- [ ] 之後可能換哪些 inference 平台？（ONNX / TensorRT / PyTorch / ...）會影響 `SegmenterBase` 介面要不要更通用
- [ ] Sniff phase 進場時，`scale_x`（sec/pixel, horizontal）從哪裡來？是否同樣存在 `seq.metadata['physical_delta_x']`，或需另設 PNG 來源的 default

---

## 🔖 Session 重啟後接續點

下次開新 session 時直接看這段：

### 1. 當前狀態（2026-05-29）

- **Step 1-7**：✅ 全部完成且驗證
- **Step 9（ratio 化 10A-10C）**：✅ 完成 + 實機驗證通過
- **Step 10（Multi-frame）**：✅ 三 mode 全落地
  - LEGACY / GLOBAL_WINDOW（11A-11D）✅
  - REALTIME（14A-18）✅ 端到端 + 實機驗證（變動位移 / 滑動視窗 / 雙 track / 累積邊界虛線）
  - REALTIME 分層 cadence（**Patch 19A**）✅：estimate_shift 前移 + heavy/light + refresh-recent mask（省 paddle）
- **REALTIME profiling（Patch 19 timing）**：✅ per-stage 計時 instrumentation（Layer A/B/C/D；duck-typed，None 零影響）
- **效能優化（Patch 20A+20B）**：✅ 落地，**20B 待 regression**——20A curve_fit ROI-crop（byte-identical 已實證）；20B `curve_fit_maxfev` 10M→5000（行為變更，需 LEGACY 比對 best_region）
- **Step 11（cfg 精煉）**：12A / 13A / 13C / 15 ✅；13B 取消
- **config 入口**：`run_config.py`（gitignored）統一個人實驗值，`run()` 注入 bundle（Patch 15）
- **清理**：`utils.py` + 兩支實驗檔已刪

### 2. 待 user 評估 / 後續

- **Aggregator 聚合規則**：stub 回第 0 組；待定義（mean / median / max / first）→ 加 `AggregatorConfig`
- **REALTIME phase_correlate**：`PHASE_CORRELATE` 已可用但精修待驗；`_phase_correlate_keyframes`（GLOBAL_WINDOW keyframe 用）仍 stub
- **REALTIME streaming adapter**：`ingest_frame` 已 streaming-ready；未來接真實 stream 來源

### 3. 候選下一步

| 候選 | 主題 | 備註 |
|---|---|---|
| A | Aggregator 聚合規則定義 + cfg 化 | 13C 收尾延伸 |
| B | REALTIME phase_correlate 精修 / 真實 stream adapter | 14 系列延伸 |
| C | Sniff phase `segment_way` 路徑 | 會啟用 scale_x → time/velocity |
| D | Step 8 byte-equivalence 驗證 script | 暫緩中 |

### 4. 規約 / 機制

- CLAUDE.md（本 repo）+ 母 CLAUDE.md 重點繼承
- 每個 patch confirm-then-execute（§3 工作節奏）
- **commit-per-patch**：每個小 patch 獨立 commit；不可 bundle 多個 patch；commit/push 由用戶 `/commit` 觸發
- AI 動檔完成後做 AST parse + import smoke test；實機驗證由 user 跑 main.py

---

## 文件維護

- 每完成一個 step 後更新「狀態」與「已完成」
- 新發現的問題記到「待辦」或「開放問題」
- 不刪除已完成項，保留歷史
