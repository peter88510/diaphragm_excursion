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

### Step 9 — Size Normalization Audit（**規劃中**）
- **狀態**：⬜ 未開始
- **動機**：許多演算法參數歷史上 hardcode 在 single-frame DICOM `1500 × 950` 尺寸；部分已 ratio 化但未全面盤點
- **受影響範圍（已知）**：ROI、tracking window、search margin、smoothing 區間、excursion 計算
- **拆解（草案）**：
  - **Patch A**：grep 全 repo 抓出 hardcode pixel constants → 產出清單（哪個 module 已 ratio、哪個還沒）
  - **Patch B**：擬定 unified normalization strategy（image-relative ratio / metadata-driven）
  - **Patch C-N**：按優先序逐項 ratio 化（每個 module 一 patch）
- **連動議題**：
  - **Multi-frame resize 決策**：是否將 multi-frame 統一 resize 至 1500×950？
    - Pros：single/multi 共用一套 pipeline、降低參數維護成本、tracking/ROI 一致
    - Cons：physical pixel spacing 失真、excursion physical distance 需推算回真實尺寸
  - **Visualization output resize**：是否讓 viz 輸出可獨立 resize（demo / realtime 用）？
    - 必須與 algorithm processing size **嚴格分離**，避免 viz resize 汙染核心計算

### Step 10 — Multi-frame Excursion 模式擴充（**規劃中**）
- **狀態**：⬜ 未開始
- **本質**：multi-frame = 多次 single-frame 結果組合
- **拆解為兩種模式**：

#### 模式狀態總覽

| Mode | 整合進度 | 對應 patch |
|---|---|---|
| `LEGACY` | ✅ 已整合進 main.py | 11A（cfg） + 11C-LEGACY（main 接 `legacy_frame_indices`） |
| `GLOBAL_WINDOW` | ⬜ 設計 backup 中 | 11B（拼接邏輯）+ 11C-GW（main 整合）|
| `REALTIME` | ⬜ 探索階段 | 未來 |

#### 模式一：Global Window 拼接
- **目的**：固定視窗策略建立完整 global signal，套既有 excursion 演算法
- **已知條件**：
  - 視窗約 88 frames（理想無 delay 時，前後 frame 位移約 8 pixel）
  - 剩餘視窗：62 frames ≈ 496 pixel 位移
- **流程**：擷取 frame 88 與 frame 149 → 各跑 single-frame 演算法 → frame 149 後半 496 pixel 訊號拼接至前段 → 形成 global signal → 套 excursion 演算法
- **依賴**：Step 9 size normalization 完成度（拼接需 size 一致）

#### 模式二：Real-time Incremental
- **目的**：模擬 real-time 演示；frame 持續輸入時即時更新 excursion
- **目前實作基礎**：每 frame 已有 shift_x 計算
- **核心問題**：
  - 第一幀為畫面起始，不參與位移；第二幀起每幀新進約 8 pixel
  - 現有 single-frame 演算法預期完整視窗（如 704 pixel），realtime 每次只新增 8 pixel → 格式不符
  - 完整第一視窗（704 pixel）累積後才穩定；但 realtime 需求是「未滿視窗也得更新」
- **設計待解**：
  - incremental signal update strategy
  - partial window handling
  - rolling excursion calculation
  - realtime-compatible signal normalization
- **狀態**：探索 / 設計階段，未動工

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

---

## 📝 待辦 / 後續 patch（先記下，不影響當前順序）

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

1. **當前狀態**：
   - Step 7（viz 統整 9A-9G）全部完成 — Step 7 viz 已驗證
   - Step 9（ratio化 10A-10C）全部完成 — **等待 2026-05-25（週一）實機驗證**
   - CLAUDE.md v1.1 與 Claude memory 機制建立完成
   - Step 9 / Step 10 規劃已整入本檔（取自 `下一步.txt` / `下下一步.txt`）

⚠️ **2026-05-25 週一驗證項**：跑 `python main.py`，預期 log 與 Patch 9G 後 byte-identical（標準 1500×955 影像）。Step 9 三 patch 對 canonical 尺寸 round() 還原為原 hardcode pixel 值，理論上零行為差異。**已驗證通過**。

📌 **Patch 11C-LEGACY 已落地**：main.py 接 `bundle.multiframe.legacy_frame_indices` 過濾 for-loop。預設 None=全跑（與舊行為一致）；設成 `[140]` 等 list 就只跑指定 frame。GLOBAL_WINDOW / REALTIME mode 設成會 raise NotImplementedError（明確告知未整合）。
2. **驗證指令**（Step 7 收尾未驗）：
   - 預設關 viz 跑一次：`python main.py`，log 應與 Patch 8 完全一致（零 `output/` 副作用）
   - 開 viz 跑一次：手動把 `viz_cfg = VisualizationConfig()` 改成 `VisualizationConfig(enabled=True, save_final=True, save_debug=True)`，看 `output/final/` 與 `output/debug/{stage}/` 內容
3. **目前 repo 狀態**：
   - root：`main.py` / `utils.py` / `CLAUDE.md` / `PROGRESS.md` + 個人筆記（`下一步.txt` / `下下一步.txt` / `過去專案參考md/`）
   - 架構分層：`input/` + `algorithm/` + `config/` + `visualization/` + `paddleseglibs/`
   - 尚未 `git init`；user 即將上 git 開始增量開發
4. **候選下一步（順序建議）**：
   - **A. Step 7 實機驗證**（建議先做）：跑 viz on/off 兩次確認
   - **B. 上 git**（建議在 A 之後）：第一次 commit 整個 refactor 里程碑 + CLAUDE.md v1
   - **C. Step 9 — Size Normalization Audit**（Patch A：grep 盤點 hardcode pixel）
   - **D. Step 10 — Multi-frame Mode 1**（依賴 C 完成度）
   - **E. Step 10 — Multi-frame Mode 2**（探索階段，長期）
   - **F. Sniff 路徑 `segment_way`**（會啟用 scale_x → time/velocity）
   - **G. Step 8 — byte-equivalence 驗證 script 實跑**（暫緩中）
5. **既有規約**：CLAUDE.md（本 repo）+ 母 CLAUDE.md 重點繼承；patch confirm-then-execute；commit/push 由用戶 `/commit` 觸發

---

## 文件維護

- 每完成一個 step 後更新「狀態」與「已完成」
- 新發現的問題記到「待辦」或「開放問題」
- 不刪除已完成項，保留歷史
