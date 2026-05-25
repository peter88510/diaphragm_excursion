"""Diaphragm motion curve extraction（excursion 主算法的第一步）。

從 M-mode 影像逐 x 抓 brightest peak 的 y，產生橫膈膜時間-位置軌跡，
再 wavelet 平滑出兩條版本（為波峰 / 波谷分析預留），與 peak-perspective 翻轉版。

直接搬自 stable_peak.py 的 edge_motion_curve，差別：
  - 移除 figure viz 參數（cv2.circle 等繪圖）；Step 7 viz 統整後從回傳資料畫
  - 回傳 dataclass 取代 5-tuple；多 broken_indices 欄位給 caller / debug 用
  - 跳躍閾值 120 / 補點窗 50 / wavelet level 3 改由 MotionCurveConfig 注入
  - 移除原本逐個 zero 的 print（150 frames × N broken 太吵）
    → caller 從 result.broken_indices 取 summary
  - dead vars else_pixel_idx / max_pixel 移除
  - 保留 4trough / 4crest 兩條同源 smoothed（原作者預留分化接口，按你的決定不修）
"""
from dataclasses import dataclass
from typing import Tuple

import numpy as np
from scipy.signal import find_peaks

from config import MotionCurveConfig
from algorithm.signal_processing import wavelet_denoising


@dataclass
class MotionCurveResult:
    init_diaphragm: np.ndarray       # 原始軌跡（已修補斷點）shape (W,)
    broken_indices: np.ndarray       # 修補前哪些 x 是斷點 shape (?,) int
    smoothed_trough: np.ndarray      # wavelet 平滑（給波谷分析用）
    diaphragm_p_trough: np.ndarray   # peak-perspective: h - smoothed_trough
    smoothed_crest: np.ndarray       # wavelet 平滑（給波峰分析用）
    diaphragm_p_crest: np.ndarray    # peak-perspective: h - smoothed_crest


def extract_motion_curve(
    image: np.ndarray,
    y_range: Tuple[int, int],
    config: MotionCurveConfig,
) -> MotionCurveResult:
    """從 image 限定 y 範圍內逐 x 找橫膈膜位置 + 平滑。

    Args:
        image: 2D gray uint8 影像（cropped DCM 灰階）
        y_range: (y_min, y_max) 限定搜尋範圍（避免底部雜訊與上方標尺干擾）
        config: MotionCurveConfig
    """
    h = image.shape[0]
    jump_threshold_px = round(config.jump_threshold_ratio * h)
    fix_search_window_px = round(config.fix_search_window_ratio * h)

    init_diaphragm, broken_indices = _trace_brightest(
        image, y_range, jump_threshold_px)
    _fix_broken(init_diaphragm, broken_indices, image, fix_search_window_px)

    # 兩條平滑：原作者開發時試過分化 level，後恢復同 level；保留兩個欄位接口
    smoothed_trough = wavelet_denoising(init_diaphragm, level=config.wavelet_level_trough)
    smoothed_crest = wavelet_denoising(init_diaphragm, level=config.wavelet_level_crest)

    # peak-perspective 翻轉：y' = h - y → 上下顛倒，方便用 find_peaks 找原本的「波谷」
    h = image.shape[0]
    diaphragm_p_trough = np.round(h - smoothed_trough)
    diaphragm_p_crest = np.round(h - smoothed_crest)

    return MotionCurveResult(
        init_diaphragm=init_diaphragm,
        broken_indices=broken_indices,
        smoothed_trough=smoothed_trough,
        diaphragm_p_trough=diaphragm_p_trough,
        smoothed_crest=smoothed_crest,
        diaphragm_p_crest=diaphragm_p_crest,
    )


def _trace_brightest(image, y_range, jump_threshold):
    """逐 x 抓 y_range 內最亮 peak 的 y。回傳 (raw trace, broken x indices)。"""
    min_y, max_y = y_range
    diaphragm = []
    broken = []
    tmp_x = 0
    for x in range(image.shape[1]):
        bar = image[min_y:max_y, x]
        peaks, _ = find_peaks(bar)
        max_pixel_idx = np.where(bar[peaks] == max(bar[peaks]))[0][0]
        y = peaks[max_pixel_idx] + min_y

        if x > 0:
            pre_y = diaphragm[tmp_x]
            if abs(y - pre_y) > jump_threshold:
                diaphragm.append(0)
                broken.append(x)
                continue
            tmp_x = x
        diaphragm.append(y)

    return np.array(diaphragm), np.array(broken, dtype=int)


def _fix_broken(diaphragm, broken_indices, image, search_window):
    """In-place 補回斷點：以前一點 y 為基準、往上 search_window 開始 argmax。"""
    for zero in broken_indices:
        pre = diaphragm[zero - 1]
        bar = image[pre - search_window:, zero]
        y = np.argmax(bar) + (pre - search_window)
        diaphragm[zero] = y
