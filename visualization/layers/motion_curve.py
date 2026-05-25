"""Motion curve 軌跡 debug 圖。

對應原 stable_peak.edge_motion_curve L188-211 的 cv2.circle 畫法：
  - 正常 x：黃色 (0,255,255) 半徑 1
  - broken（被 _fix_broken 修補過）：藍色 (255,0,0) 半徑 3
  - smoothed_crest：紅色 (0,0,255) 半徑 1

algorithm/motion_curve/extract.py 不負責畫，本層只讀 MotionCurveResult。
"""
import cv2
import numpy as np

from algorithm.motion_curve import MotionCurveResult
from config.visualization_config import VisualizationConfig
from visualization import stages
from visualization.io import debug_path, save_png, should_save_debug


_COLOR_NORMAL = (0, 255, 255)   # 黃
_COLOR_BROKEN = (255, 0, 0)     # 藍
_COLOR_CREST = (0, 0, 255)      # 紅


def render_motion_curve(
    image_gray: np.ndarray,
    motion_curve: MotionCurveResult,
    cfg: VisualizationConfig,
    frame_idx: int,
) -> None:
    """存 motion curve 軌跡疊在原 gray 圖上的 debug 圖。"""
    if not should_save_debug(cfg, stages.MOTION_CURVE):
        return
    canvas = cv2.cvtColor(image_gray, cv2.COLOR_GRAY2BGR)
    broken_set = set(int(i) for i in motion_curve.broken_indices)

    # 原始軌跡（含修補點）
    for x, y in enumerate(motion_curve.init_diaphragm):
        if x in broken_set:
            cv2.circle(canvas, (int(x), int(y)), radius=3,
                       color=_COLOR_BROKEN, thickness=-1)
        else:
            cv2.circle(canvas, (int(x), int(y)), radius=1,
                       color=_COLOR_NORMAL, thickness=-1)

    # smoothed_crest 平滑曲線
    for x, y in enumerate(motion_curve.smoothed_crest):
        cv2.circle(canvas, (int(x), int(y)), radius=1,
                   color=_COLOR_CREST, thickness=-1)

    save_png(canvas, debug_path(cfg, stages.MOTION_CURVE, frame_idx))
