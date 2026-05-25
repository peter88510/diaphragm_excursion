# visualization/ — 視覺化層

> debug per-stage + final overlay 兩條獨立 track；algorithm 層保持零副作用，所有畫圖集中在此。
> 跨層架構見 [`ARCHITECTURE.md`](../../ARCHITECTURE.md)；資料流見 [`docs/pipeline.md`](../pipeline.md) §9。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 改 viz 行為時參考；想了解 debug 圖怎麼出 |

---

## §1 模組目標

集中所有 cv2 / PIL / matplotlib 畫圖副作用，讓 algorithm 層保持純函式。

兩條獨立 track，互不混用：

| Track | 用途 | 控制 | 輸出位置 |
|---|---|---|---|
| **debug** | 每處理階段一張圖，檔名標 stage；給 debug 看演算法內部 | `cfg.save_debug` + `cfg.debug_stages` 過濾 | `output/debug/{stage}/{i:04d}.png` |
| **final** | 綜合成果圖，呈現給人看 | `cfg.save_final` + 3 個 element toggle | `output/final/{i:04d}.png` |

`cfg.enabled = False`（**default**）→ render_frame 立刻 return；零 I/O。

---

## §2 子結構

```
visualization/
├── __init__.py
├── pipeline_visualizer.py     PipelineVisualizer 主入口 + _render_final
├── io.py                       path 規則 + should_save_* gate + save_png
├── stages.py                   9 個 debug stage 字串常數 + ALL_STAGES
├── info_display.py             excursion_info_display（PIL 自訂字 markers + 文字）
└── layers/
    ├── __init__.py
    ├── segmentation.py         render_paddle_segmentation
    ├── detection.py            render_detection_pass1 + render_detection_pass2
    ├── roi_band.py             render_roi_band (y_band overlay + enhanced)
    ├── motion_curve.py         render_motion_curve (debug 用，軌跡疊圖)
    └── excursion.py            render_excursion_brightness (PIL Figure + Agg)
```

---

## §3 對外 API

```python
from config import VisualizationConfig, ExcursionConfig
from visualization.pipeline_visualizer import PipelineVisualizer

viz_cfg = VisualizationConfig(enabled=True, save_final=True, save_debug=False)
pv = PipelineVisualizer(viz_cfg, excursion_cfg)

# 每 frame 呼叫
pv.render_frame(
    frame_idx=i,
    image_gray=gray,        # debug track 用
    image_color=color,      # final track base canvas
    seg_mask=seg_mask,
    frame_result=result,    # FrameResult 含所有 stage 結果
)
```

caller（main.py）**無條件呼叫** `render_frame()`；cfg 控制是否真的畫。

---

## §4 兩 Track 設計

### Debug track

- 每個 stage 各自一張圖、各自一個目錄
- 路徑：`{output_dir}/debug/{stage}/{i:04d}.png`
- gate：`io.should_save_debug(cfg, stage)` 內部三層判斷：
  1. stage 是否在 `ALL_STAGES` 註冊（未知 stage → `ValueError`，防拼字錯誤）
  2. `cfg.enabled and cfg.save_debug`
  3. `cfg.debug_stages` None → 全部開；set → 只開指定 stage

### Final track

- 一張綜合圖
- 路徑：`{output_dir}/final/{i:04d}.png`
- gate：`io.should_save_final(cfg) = enabled and save_final`
- 3 個 element toggle 控制畫什麼（見 §6）

### 為何兩條獨立

- debug 用灰階襯底、跟著演算法視角；final 用彩色保留 DCM 原色標
- debug 是給開發人員、final 是給人看
- 強制不混用避免「demo 圖被 debug 標籤污染」

---

## §5 Debug Stages（9 個）

定義於 `visualization/stages.py`：

| Stage 常數 | 字串值 | 來源資料 | 輸出 |
|---|---|---|---|
| `PADDLE_SEGMENTATION` | `paddle_segmentation` | `seg_mask` (paddle raw mask) | 灰階單通道 PNG |
| `DETECTION_PASS1_OVERLAY` | `detection_pass1_overlay` | `detection.debug_overlay` | BGR color-coded |
| `DETECTION_PASS1_FILTERED` | `detection_pass1_filtered` | `detection.filtered_binary` | 灰階 |
| `DETECTION_PASS1_POTENTIAL` | `detection_pass1_potential` | `detection.potential_binary` | 灰階（fallback 時為 None → 跳過）|
| `ROI_BAND_YBAND` | `roi_band_yband` | `image_gray` + `y_band` 兩條水平線 | BGR |
| `ROI_BAND_ENHANCED` | `roi_band_enhanced` | `refined.enhanced_padded` | 灰階 |
| `DETECTION_PASS2_OVERLAY` | `detection_pass2_overlay` | `refined.padded_overlay` | BGR color-coded |
| `MOTION_CURVE` | `motion_curve` | `image_gray` + `motion_curve.init_diaphragm` + `smoothed_crest` | BGR + 圓點軌跡 |
| `EXCURSION_BRIGHTNESS` | `excursion_brightness` | `motion_curve.diaphragm_p_*` + find_peaks | matplotlib Figure PNG |

`ALL_STAGES = frozenset({...})` 用於 cfg `debug_stages` 過濾的 reference set。

### Renderer 慣例

每個 layer renderer 簽名：
```python
def render_<stage>(<data>, cfg: VisualizationConfig, frame_idx: int) -> None
```

- 內部呼叫 `should_save_debug(cfg, stage)` gate；False 立刻 return
- 自己負責 image 處理（grayscale → BGR、cv2.line 等）
- 呼叫 `io.save_png(image, debug_path(cfg, stage, frame_idx))`

---

## §6 Final Overlay 元素 + Toggles

`PipelineVisualizer._render_final(image_color, frame_result)` 流程：

```python
canvas = image_color.copy()    # base 用 as_color 保留原 DCM 色標

# 1) motion curve 軌跡（toggle 1）
if cfg.final_show_motion_curve:
    for (x, y) in motion_curve.init_diaphragm: cv2.circle(...)

# 2) markers + 文字（toggle 2 + 3 共用 excursion_info_display）
if measurements and (final_show_peak_markers or final_show_excursion_text):
    canvas = excursion_info_display(
        figure=canvas,
        peaks_info=_to_peaks_info(measurements),
        font_path=cfg.final_font_path,
        peak='ct' if final_show_peak_markers else '',
        show_text=final_show_excursion_text,
    )

return canvas
```

### Toggles（`VisualizationConfig`）

| Toggle | Default | 控制 |
|---|---|---|
| `final_show_motion_curve` | False（user 手調）| motion curve 啞黃軌跡（debug 用襯底）|
| `final_show_peak_markers` | True | crest（黃星 + label）+ trough（橘星 + label）|
| `final_show_excursion_text` | True | excursion_cm / sec / velocity 自訂字型文字 |

3 個 toggle 全關 + measurements 空 → `excursion_info_display` 不呼叫，零 PIL 轉換成本。

### Adapter — `_to_peaks_info`

`PipelineVisualizer` 內含小 helper，把 `List[PeakInfo]` 轉成 legacy dict 格式（保留 `excursion_info_display` 原 API）：

```python
{
    i: {
        "trough": {"x": ..., "y": ...},
        "crest": {"x": ..., "y": ...},
        "velocity": ...,
        "excursion": ...,
        "time_sec": ...,
    }
    for i, m in enumerate(measurements)
}
```

---

## §7 `info_display.py` 設計

### 公開入口

```python
def excursion_info_display(
    figure: np.ndarray,
    peaks_info: Dict,
    font_path: str = "./font/Altinn-DIN Bold.otf",
    peak: str = 'ct',        # '', 'c', 't', 'ct'
    show_text: bool = True,  # 控制大文字
) -> np.ndarray
```

只取 `peaks_info[0]`（multi-batch 未支援；當前 spec 也只用 batch 0）。

### Helper 拆分

| Helper | 用途 |
|---|---|
| `_draw_peak_marker(img, point, label, color, label_above)` | 實心圓點 + 垂直虛線 + 半透明底框標籤；`label_above` 控制標籤在 marker 上/下 |
| `_draw_big_text_block(img, font_path, excursion_cm, time_sec, velocity)` | PIL 自訂字型寫 cm / sec / velocity，**單次 BGR↔PIL 轉換** |

### 視覺常數（module top）

| 常數 | 值 | 用途 |
|---|---|---|
| `_CREST_COLOR` | `(0, 255, 255)` | 黃 |
| `_TROUGH_COLOR` | `(255, 128, 0)` | 橘 |
| `_DOT_RADIUS` | 2 | 圓點半徑 |
| `_BAR_LENGTH` | 50 | 虛線長度 |
| `_LABEL_BG_ALPHA` | 0.6 | 半透明底框 alpha |
| `_BIG_FONT_SIZE` | 36 | 大文字字級 |

### 設計重點

- **修兩個 bug**（Patch 9F review 階段發現）：
  - label 位置原用 `label == "Crest"` 字串比對 → 改 `label_above: bool` 旗標
  - `getTextSize` 量兩次（scale 0.6 vs 0.8）造成邊界檢查與底框尺寸不一致 → 統一 0.8
- **PIL 轉換合併**：原 3 次 BGR↔PIL → 1 次，效能與可讀性都改善
- **None guard**：`excursion_cm is None` 時跳過該行文字

---

## §8 `io.py` 路徑與 gate

| 函式 | 用途 |
|---|---|
| `final_path(cfg, frame_idx)` | `{output_dir}/final/{i:04d}.png` |
| `debug_path(cfg, stage, frame_idx)` | `{output_dir}/debug/{stage}/{i:04d}.png`；stage 名做 alnum/_-/sanitize 防路徑注入 |
| `should_save_final(cfg)` | `cfg.enabled and cfg.save_final` |
| `should_save_debug(cfg, stage)` | 三層 gate；stage 不在 `ALL_STAGES` 內 raise `ValueError` |
| `save_png(image, path)` | `mkdir parents=True` + `cv2.imwrite`；失敗 raise `IOError` |

---

## §9 依賴方向

```
visualization/                       外部依賴
├── pipeline_visualizer.py     →   algorithm.FrameResult / ExcursionConfig
│                              →   visualization.layers.* / info_display / io
├── layers/*                   →   algorithm.* (read result types)
│                              →   visualization.io / stages
├── info_display.py            →   cv2 / numpy / PIL
├── io.py                      →   cv2 / config.VisualizationConfig / visualization.stages
└── stages.py                  →   (純常數)
```

### 跨層規約（per ARCHITECTURE.md §4）

- **visualization → algorithm**：允許（讀 result types）
- **algorithm → visualization**：**禁止**（algorithm 純函式，不畫圖）
- layer 之間：每個 layer 獨立；layer 不互相 import

### Matplotlib 隔離

`excursion.py` 用 `Figure + FigureCanvasAgg` **不碰** `matplotlib.pyplot.use()` 全域 backend，避免污染其他 caller 的 matplotlib state。

---

## §10 待辦與已知限制

| 項目 | 影響範圍 | 處理計畫 |
|---|---|---|
| Multi-batch 顯示未支援 | `excursion_info_display` 只取 `peaks_info[0]` | 未來 multi-batch 需求出現再擴 |
| `info_display.py` 視覺常數 hardcode | font_size / position / stroke 等寫在常數區 | 必要時搬入 `VisualizationConfig` |
| viz 對 multi-frame stitched signal 未設計 | Step 10 Mode 1 落地後可能需要拼接區塊標記 | Patch 11C / 之後處理 |
| `model_load_caching.md` SNAPSHOT header 不符 §10.2 | 與 viz 無直接關係但 reside `docs/notes/` | PROGRESS.md 待辦 |
| Final overlay alpha / 顏色未 config 化 | hardcoded in `pipeline_visualizer.py` | 必要時搬入 cfg |

---

## §11 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§10 全部章節定義 | 文件化專案，深入 visualization 內部 |
