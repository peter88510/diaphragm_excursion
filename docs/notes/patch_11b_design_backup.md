# Patch 11B Design Backup — Global Window 拼接邏輯

> 暫存 Patch 11B 的設計討論、原始提案、修正版提案。
> 待 user 確認後執行；確認前**不可動 code**。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | SNAPSHOT |
| 版本 | 0.3 |
| 最後更新 | 2026-05-25 |
| 校對對象 | `algorithm/multiframe/global_window.py`（已實作；Patch 11B' 兩段 stitching） |
| 狀態 | implemented |
| 過期條件 | `global_window.py` 邏輯變動 / API 簽名變動 → 更新或廢棄本檔 |

---

## §1 背景

Step 10 Multi-frame Excursion Mode 1（GLOBAL_WINDOW）的拼接邏輯。
依賴 Patch 11A 已落地的 `MultiframeConfig` + `MultiframeMode` + `KeyframeStrategy`。

**已於 2026-05-25 落地為 `algorithm/multiframe/global_window.py`**；本檔保留作設計史。

**Patch 11B' 後續修正（同日落地）**：stitching 邏輯改為兩段獨立 — `first[:len_first] + second[-len_second:]`，避免原版 `first 完整 + second 右尾` 造成的 keyframe[0] 之後時段重複。具體 keyframe / pixel 數字已自 doc 移除（experiment 值會調，避免 doc rot）。

---

## §2 四個關鍵設計決定（user 答覆）

| Q | 議題 | 決定 |
|---|---|---|
| Q1 | 訊號拼接 y 值對齊 | 直接 concat；`frame[1].init_diaphragm[-stitch_length:]`（右邊界往左）；不對齊（位移只在 x 方向，y 噪音忽略） |
| Q2 | keyframe 數量 | 嚴格 2 個；不是 2 個 raise ValueError |
| Q3 | mask 拼接 | 直接 concat（與 Q1 一致），沿 x 軸 axis=1 |
| Q4 | GlobalExcursionResult 內容 | 全局 + 拼接 metadata |

---

## §3 額外設計決定（wavelet 處理）

**討論**：原本我提案「對 stitched signal 重做 wavelet」。
**user 質疑**：「wavelet_denoising 不要在拼接後再做一次，因為拼接前已經做過了」。
**結論**：採納 user 設計。直接 concat 已平滑過的 `smoothed_*` / `p_*`，**不重做 wavelet**。

理由：
- 每個 keyframe 跑 single-frame motion_curve 時已 wavelet 平滑
- 重做等於對已平滑的訊號再 over-smooth，可能損失區域 detail
- 拼接點 wavelet edge artifact 量級小（level 3 db4 影響 ~64 pixel），對 excursion 量測影響有限

連帶簡化：
- `run_global_window()` 簽名移除 `motion_curve_cfg` 與 `image_height`
- `_rebuild_smoothed()` helper 整支刪除
- 不再 `import wavelet_denoising`

---

## §4 拼接長度 default 計算

- `stitch_length_px = (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel`
- For default cfg `[87, 149]` & `stride=8`：→ `(149-87) × 8 = **496 pixel**`（spec 對齊）
- 早期 backup 寫過 `[88, 149]` → 488，那是 user 失誤的 keyframe；落地時已修正

`MultiframeConfig` 加欄位：`stitch_length_px: Optional[int] = None`（None = 自動算）。

---

## §5 修正版 11B 完整 patch 內容

### `config/multiframe_config.py` 加欄位

```python
# GLOBAL_WINDOW 拼接長度（pixel，從 frame[1] 右邊界往左取）
# None = 自動算 (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel
# spec 寫 496 (=62×8 inclusive count)，要明示請設 stitch_length_px=496
stitch_length_px: Optional[int] = None
```

### `algorithm/multiframe/global_window.py` 新檔

```python
"""GLOBAL_WINDOW mode (Mode 1) 主算法。

從兩個 keyframe 各自的 single-frame 結果拼接 → 全局 signal → 全局 excursion。

拼接策略（Q1 確認）：
  - frame[0]: 完整 init_diaphragm / smoothed_* / p_* / mask
  - frame[1]: 取右邊界往左 stitch_length_px 段
  - 直接 concat，不對齊（位移只在 x；y 追蹤噪音影響忽略）
  - 不重做 wavelet：每個 keyframe 跑 single-frame motion_curve 時已平滑過

嚴格 2 keyframe（Q2）；mask 直接 concat（Q3）；全局 + metadata（Q4）。
"""
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from algorithm.excursion import (
    ExcursionResult,
    PeakInfo,
    brightness_way,
    compute_peak_info,
)
from algorithm.motion_curve import MotionCurveResult
from algorithm.roi_band import TargetSelection
from config.excursion_config import ExcursionConfig
from config.multiframe_config import MultiframeConfig


@dataclass
class GlobalExcursionResult:
    # 全局 stitched signals（直接 concat keyframe 已平滑結果）
    stitched_init_diaphragm: np.ndarray         # (W_full,)
    stitched_smoothed_trough: np.ndarray        # (W_full,)
    stitched_smoothed_crest: np.ndarray         # (W_full,)
    stitched_p_trough: np.ndarray               # (W_full,) peak-perspective
    stitched_p_crest: np.ndarray                # (W_full,)
    stitched_diaphragm_mask: np.ndarray         # (H, W_full)

    # 全局 excursion
    excursion: ExcursionResult
    measurements: List[PeakInfo] = field(default_factory=list)

    # 拼接 metadata
    keyframe_indices: List[int] = field(default_factory=list)
    stitch_length_px: int = 0
    stitch_boundary_x: int = 0       # 拼接點 x 座標（= 第一段寬度）
    first_keyframe_width: int = 0
    full_width: int = 0


def run_global_window(
    keyframe_motion_curves: List[MotionCurveResult],
    keyframe_selections: List[TargetSelection],
    multiframe_cfg: MultiframeConfig,
    excursion_cfg: ExcursionConfig,
    scale_y: Optional[float] = None,
) -> GlobalExcursionResult:
    """Mode 1 主入口。

    依賴：兩個 keyframe 已跑完 single-frame motion_curve（含 wavelet 平滑）
    與 target_selection（含 diaphragm_mask）。本函式只負責拼接 + 全局 excursion。
    """
    if len(keyframe_motion_curves) != 2 or len(keyframe_selections) != 2:
        raise ValueError(
            "GLOBAL_WINDOW 目前只支援嚴格 2 個 keyframe；"
            f"got {len(keyframe_motion_curves)} motion curves / "
            f"{len(keyframe_selections)} selections"
        )

    stitch_len = _compute_stitch_length(multiframe_cfg)
    mc1, mc2 = keyframe_motion_curves
    sel1, sel2 = keyframe_selections

    stitched_init = _stitch_1d(mc1.init_diaphragm, mc2.init_diaphragm, stitch_len)
    stitched_smoothed_trough = _stitch_1d(
        mc1.smoothed_trough, mc2.smoothed_trough, stitch_len)
    stitched_smoothed_crest = _stitch_1d(
        mc1.smoothed_crest, mc2.smoothed_crest, stitch_len)
    stitched_p_trough = _stitch_1d(
        mc1.diaphragm_p_trough, mc2.diaphragm_p_trough, stitch_len)
    stitched_p_crest = _stitch_1d(
        mc1.diaphragm_p_crest, mc2.diaphragm_p_crest, stitch_len)
    stitched_mask = _stitch_mask_2d(
        sel1.diaphragm_mask, sel2.diaphragm_mask, stitch_len)

    excursion = brightness_way(
        diaphragm_mask=stitched_mask,
        diaphragm_p_4crest=stitched_p_crest,
        diaphragm_p_4trough=stitched_p_trough,
        diaphragm_ori_y_value=stitched_init,
        config=excursion_cfg,
    )

    measurements = [
        compute_peak_info(
            crest=batch.crest_position,
            trough=batch.trough_position,
            scale_y=scale_y,
        )
        for batch in excursion.batches
    ]

    first_width = len(mc1.init_diaphragm)
    return GlobalExcursionResult(
        stitched_init_diaphragm=stitched_init,
        stitched_smoothed_trough=stitched_smoothed_trough,
        stitched_smoothed_crest=stitched_smoothed_crest,
        stitched_p_trough=stitched_p_trough,
        stitched_p_crest=stitched_p_crest,
        stitched_diaphragm_mask=stitched_mask,
        excursion=excursion,
        measurements=measurements,
        keyframe_indices=list(multiframe_cfg.keyframe_indices),
        stitch_length_px=stitch_len,
        stitch_boundary_x=first_width,
        first_keyframe_width=first_width,
        full_width=first_width + stitch_len,
    )


# ---------- helpers ----------

def _compute_stitch_length(cfg: MultiframeConfig) -> int:
    """從 stitch_length_px override 或 (keyframe diff × stride) 推導。"""
    if cfg.stitch_length_px is not None:
        return cfg.stitch_length_px
    if len(cfg.keyframe_indices) < 2:
        raise ValueError(
            f"keyframe_indices 需至少 2 個；got {cfg.keyframe_indices}"
        )
    a, b = cfg.keyframe_indices[:2]
    return (b - a) * cfg.stride_pixel


def _stitch_1d(
    first: np.ndarray,
    second: np.ndarray,
    stitch_length_px: int,
) -> np.ndarray:
    """1D signal 拼接：first 完整 + second 右邊界往左 stitch_length_px。"""
    if stitch_length_px > len(second):
        raise ValueError(
            f"stitch_length_px={stitch_length_px} > second signal len={len(second)}"
        )
    return np.concatenate([first, second[-stitch_length_px:]])


def _stitch_mask_2d(
    first: np.ndarray,
    second: np.ndarray,
    stitch_length_px: int,
) -> np.ndarray:
    """2D mask 沿 x 軸 (axis=1) 拼接。"""
    if first.shape[0] != second.shape[0]:
        raise ValueError(
            f"mask height 不一致：first={first.shape}, second={second.shape}"
        )
    if stitch_length_px > second.shape[1]:
        raise ValueError(
            f"stitch_length_px={stitch_length_px} > second width={second.shape[1]}"
        )
    return np.concatenate([first, second[:, -stitch_length_px:]], axis=1)
```

### `algorithm/multiframe/__init__.py` 加 export

```diff
 from algorithm.multiframe.frame_selection import (
     get_keyframe_indices,
     get_legacy_frame_indices,
 )
+from algorithm.multiframe.global_window import (
+    GlobalExcursionResult,
+    run_global_window,
+)

-__all__ = ["get_legacy_frame_indices", "get_keyframe_indices"]
+__all__ = [
+    "get_legacy_frame_indices",
+    "get_keyframe_indices",
+    "run_global_window",
+    "GlobalExcursionResult",
+]
```

---

## §6 風險與未決事項

- **edge artifact**：frame[0] 右邊界 wavelet edge effect 出現在 stitched signal 中段（約 x=1500 處）；level 3 db4 影響 ~64 pixel；對 excursion 量測影響可能有限，實機驗證後決定是否加 boundary smoothing
- **拼接 length 預設 488 vs spec 496**：差 8 pixel；user 可顯式設 `stitch_length_px=496`
- **未驗證**：multi-frame DCM 真實資料；11C main.py 整合時提供

---

## §7 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | 0.1 | 初版建立（含原始 + 修正版提案、Q&A 討論、wavelet 設計決定） | Patch 11B backup；待 user 確認執行 |
| 2026-05-25 | 0.2 | 標狀態 implemented；§4 default 488 → 496；§1 加修正備註 `[88,149]` → `[87,149]` | Patch 11B 邏輯落地 |
| 2026-05-25 | 0.3 | §1 加 11B' 修正紀錄（兩段 stitching）；具體數字移除（experiment 值） | Patch 11B'：first/second 拆兩段獨立、frame_width cap |
