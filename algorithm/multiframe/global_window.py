"""GLOBAL_WINDOW mode (Mode 1) 主算法。

從兩個 keyframe 各自的 single-frame 結果拼接 → 全局 signal → 全局 excursion。

拼接策略：
  - frame[0]: 取前 len_first 段 → first[:len_first]
              len_first = min(keyframe_indices[0] × stride_pixel, frame_width)
  - frame[1]: 取右邊界往左 len_second 段 → second[-len_second:]
              len_second = (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel
  - 直接 concat，不對齊（位移只在 x；y 追蹤噪音影響忽略）
  - 不重做 wavelet：每個 keyframe 跑 single-frame motion_curve 時已平滑過
  - 物理意義：first 段 = 「0 → keyframe[0]」時段；second 段 = 「keyframe[0] → keyframe[1]」時段

註：視窗 pixel 公式為 multi-frame 實驗結果；
    理論上 multi-frame 不會超過 2 keyframe（嚴格 2）；mask 直接 concat；全局 + metadata。
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
    first_segment_len_px: int = 0    # frame[0] 取前 N pixel
    second_segment_len_px: int = 0   # frame[1] 取右尾 M pixel
    stitch_boundary_x: int = 0       # 拼接點 x 座標（= first_segment_len_px）
    full_width: int = 0              # = first_segment_len_px + second_segment_len_px


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

    mc1, mc2 = keyframe_motion_curves
    sel1, sel2 = keyframe_selections
    frame_width = len(mc1.init_diaphragm)
    len_first = _compute_first_length(multiframe_cfg, frame_width)
    len_second = _compute_second_length(multiframe_cfg)

    stitched_init = _stitch_1d(
        mc1.init_diaphragm, mc2.init_diaphragm, len_first, len_second)
    stitched_smoothed_trough = _stitch_1d(
        mc1.smoothed_trough, mc2.smoothed_trough, len_first, len_second)
    stitched_smoothed_crest = _stitch_1d(
        mc1.smoothed_crest, mc2.smoothed_crest, len_first, len_second)
    stitched_p_trough = _stitch_1d(
        mc1.diaphragm_p_trough, mc2.diaphragm_p_trough, len_first, len_second)
    stitched_p_crest = _stitch_1d(
        mc1.diaphragm_p_crest, mc2.diaphragm_p_crest, len_first, len_second)
    stitched_mask = _stitch_mask_2d(
        sel1.diaphragm_mask, sel2.diaphragm_mask, len_first, len_second)

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
        first_segment_len_px=len_first,
        second_segment_len_px=len_second,
        stitch_boundary_x=len_first,
        full_width=len_first + len_second,
    )


# ---------- helpers ----------

def _compute_first_length(cfg: MultiframeConfig, frame_width: int) -> int:
    """first 段長度：override 或 min(kf[0] × stride, frame_width)；cap 防超寬。"""
    if cfg.stitch_length_px_first is not None:
        return min(cfg.stitch_length_px_first, frame_width)
    if len(cfg.keyframe_indices) < 1:
        raise ValueError(
            f"keyframe_indices 需至少 1 個；got {cfg.keyframe_indices}"
        )
    return min((cfg.keyframe_indices[0] + 1) * cfg.stride_pixel, frame_width)


def _compute_second_length(cfg: MultiframeConfig) -> int:
    """second 段長度：override 或 (kf[1] - kf[0]) × stride。"""
    if cfg.stitch_length_px_second is not None:
        return cfg.stitch_length_px_second
    if len(cfg.keyframe_indices) < 2:
        raise ValueError(
            f"keyframe_indices 需至少 2 個；got {cfg.keyframe_indices}"
        )
    a, b = cfg.keyframe_indices[:2]
    return (b - a) * cfg.stride_pixel


def _stitch_1d(
    first: np.ndarray,
    second: np.ndarray,
    first_length_px: int,
    second_length_px: int,
) -> np.ndarray:
    """1D signal 拼接：first[:first_length_px] + second[-second_length_px:]。"""
    if first_length_px > len(first):
        raise ValueError(
            f"first_length_px={first_length_px} > first signal len={len(first)}"
        )
    if second_length_px > len(second):
        raise ValueError(
            f"second_length_px={second_length_px} > second signal len={len(second)}"
        )
    return np.concatenate([first[:first_length_px], second[-second_length_px:]])


def _stitch_mask_2d(
    first: np.ndarray,
    second: np.ndarray,
    first_length_px: int,
    second_length_px: int,
) -> np.ndarray:
    """2D mask 沿 x 軸 (axis=1) 拼接：first[:, :len_f] + second[:, -len_s:]。"""
    if first.shape[0] != second.shape[0]:
        raise ValueError(
            f"mask height 不一致：first={first.shape}, second={second.shape}"
        )
    if first_length_px > first.shape[1]:
        raise ValueError(
            f"first_length_px={first_length_px} > first width={first.shape[1]}"
        )
    if second_length_px > second.shape[1]:
        raise ValueError(
            f"second_length_px={second_length_px} > second width={second.shape[1]}"
        )
    return np.concatenate(
        [first[:, :first_length_px], second[:, -second_length_px:]], axis=1
    )
