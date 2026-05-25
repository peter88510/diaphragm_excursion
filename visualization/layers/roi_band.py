"""ROI band 兩張 debug 圖：y_band overlay + enhanced 強化後圖。

  roi_band_yband    : 原灰階圖 + y_band 上下兩條水平線（綠）
  roi_band_enhanced : enhance_band 輸出的 enhanced_padded（已 zero-pad 回原圖大小）

algorithm/roi_band/ 不負責畫，本層只讀資料（image_gray / y_band / enhanced_padded）。
"""
from typing import Tuple

import cv2
import numpy as np

from config.visualization_config import VisualizationConfig
from visualization import stages
from visualization.io import debug_path, save_png, should_save_debug


# y_band 上下水平線顏色（BGR，綠色）
_YBAND_LINE_COLOR = (0, 255, 0)
_YBAND_LINE_THICKNESS = 1


def render_roi_band(
    image_gray: np.ndarray,
    y_band: Tuple[int, int],
    enhanced_padded: np.ndarray,
    cfg: VisualizationConfig,
    frame_idx: int,
) -> None:
    """存 ROI band 階段的兩張 debug 圖。"""
    if should_save_debug(cfg, stages.ROI_BAND_YBAND):
        save_png(
            _draw_y_band(image_gray, y_band),
            debug_path(cfg, stages.ROI_BAND_YBAND, frame_idx),
        )
    if should_save_debug(cfg, stages.ROI_BAND_ENHANCED):
        save_png(
            enhanced_padded,
            debug_path(cfg, stages.ROI_BAND_ENHANCED, frame_idx),
        )


def _draw_y_band(image_gray: np.ndarray, y_band: Tuple[int, int]) -> np.ndarray:
    """把 y_band 範圍以上下兩條水平線標在 gray 圖上（回傳 BGR copy）。"""
    canvas = cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR)
    y_min, y_max = y_band
    h, w = canvas.shape[:2]
    cv2.line(canvas, (0, y_min), (w - 1, y_min),
             _YBAND_LINE_COLOR, _YBAND_LINE_THICKNESS)
    cv2.line(canvas, (0, y_max), (w - 1, y_max),
             _YBAND_LINE_COLOR, _YBAND_LINE_THICKNESS)
    return canvas
