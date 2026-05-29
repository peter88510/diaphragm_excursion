"""REALTIME 相鄰幀水平位移估計。

實際超音波非理想 +8px/frame：有 delay（無位移）或快進（位移大）。
estimate_shift 算相鄰兩 gray frame 的水平位移，供 REALTIME 拼接決定取右尾長度。

策略（ShiftStrategy）：
  - FIXED          : 固定 stride_pixel（legacy / fallback；驗證後移除）
  - TEMPLATE_MATCH : 取 prev 最右 column 在 curr 做 matchTemplate（TM_CCOEFF_NORMED）
                     → 整數 px。confidence = match score ∈ [-1, 1]
  - PHASE_CORRELATE: cv2.phaseCorrelate（Hanning window）→ float sub-pixel。
                     confidence ∈ [0, 1]（peak of normalized cross-power）

Sign 約定：native 估計值（raw_shift）對「時間前進 / M-mode 內容左移」為負向
（template best_x-(W-1)≤0；phase shift_x 亦負）。forward shift_px = -raw（正=前進、
0=delay、負=倒退）。stitching 取 shift_px 個右尾 column。

confidence 量綱因策略而異（見上）；min_confidence 門檻請依使用的 strategy 調整。
"""
from dataclasses import dataclass

import cv2
import numpy as np

from config.multiframe_config import ShiftStrategy


@dataclass
class ShiftResult:
    shift_px: int          # forward 位移（拼接用整數；正=前進、≤0=delay/倒退）
    raw_shift: float       # native 估計值（與實驗 code 同號，便於對照）
    confidence: float      # template score / phaseCorrelate confidence；FIXED=1.0
    found: bool            # confidence 是否達 min_confidence


def estimate_shift(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
    strategy: ShiftStrategy,
    stride_pixel: int,
    min_confidence: float,
) -> ShiftResult:
    """估計 curr 相對 prev 的 forward 水平位移。dispatch 三策略。"""
    if strategy == ShiftStrategy.FIXED:
        return ShiftResult(
            shift_px=stride_pixel, raw_shift=float(-stride_pixel),
            confidence=1.0, found=True,
        )
    if strategy == ShiftStrategy.TEMPLATE_MATCH:
        return _template_match_shift(prev_gray, curr_gray, min_confidence)
    if strategy == ShiftStrategy.PHASE_CORRELATE:
        return _phase_correlate_shift(prev_gray, curr_gray, min_confidence)
    raise ValueError(f"unknown ShiftStrategy: {strategy}")


def _template_match_shift(
    prev_gray: np.ndarray, curr_gray: np.ndarray, min_confidence: float,
) -> ShiftResult:
    """prev 最右 column 在 curr matchTemplate；forward = (W-1) - best_x。"""
    if prev_gray.shape[0] != curr_gray.shape[0]:
        raise ValueError(
            f"prev/curr 高度必須一致：{prev_gray.shape} vs {curr_gray.shape}")

    template = prev_gray[:, -1:].astype(np.float32)        # (H, 1)
    target = curr_gray.astype(np.float32)
    result = cv2.matchTemplate(target, template, cv2.TM_CCOEFF_NORMED)
    _min_v, max_v, _min_loc, max_loc = cv2.minMaxLoc(result)

    last_x = prev_gray.shape[1] - 1
    best_x = max_loc[0]
    raw = best_x - last_x          # native（同實驗 code），≤ 0
    return ShiftResult(
        shift_px=int(last_x - best_x),     # forward = -raw
        raw_shift=float(raw),
        confidence=float(max_v),
        found=bool(max_v >= min_confidence),
    )


def _phase_correlate_shift(
    prev_gray: np.ndarray, curr_gray: np.ndarray, min_confidence: float,
) -> ShiftResult:
    """cv2.phaseCorrelate（Hanning window）→ float sub-pixel；forward = -shift_x。"""
    h = min(prev_gray.shape[0], curr_gray.shape[0])
    w = min(prev_gray.shape[1], curr_gray.shape[1])
    a = prev_gray[:h, :w].astype(np.float32)
    b = curr_gray[:h, :w].astype(np.float32)
    window = cv2.createHanningWindow((w, h), cv2.CV_32F)

    (shift_x, _shift_y), confidence = cv2.phaseCorrelate(a, b, window)
    return ShiftResult(
        shift_px=int(round(-shift_x)),     # forward = -raw
        raw_shift=float(shift_x),
        confidence=float(confidence),
        found=bool(confidence >= min_confidence),
    )
