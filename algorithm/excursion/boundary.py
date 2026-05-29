"""用 diaphragm segmentation mask 修正 peak / trough 位置至實際邊界。

重構自舊版 root util 的 FindBoundary + find_boundary_v2，邏輯不動：
  - find_boundary_v2(roi_map, roi_position, m=1)  # m=1 找波峰 / m=-1 找波谷
  - FindBoundary(diaphragm_mask, x_crest, y_crest, x_trough, y_trough)

只搬，不重寫邏輯；加 docstring / type hints。
"""
from typing import List, Optional, Tuple

import cv2
import numpy as np


def find_boundary(
    diaphragm_mask: np.ndarray,
    selected_x_crest: List[int],
    selected_y_crest: List[int],
    selected_x_trough: List[int],
    selected_y_trough: List[int],
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """以 diaphragm_mask 為參考，把 (x, y) peak/trough 位置調整到 mask 真實邊界。

    NOTE: 原命名 selected_y_ctest 有 typo（ctest -> crest），這裡修正。
    diaphragm_mask 是「包含斷掉橫膈膜、不只 target」的完整 binary。

    Args:
        diaphragm_mask: 2D binary mask
        selected_x_crest: 波峰 x 座標 list（用第 0 個）
        selected_y_crest: 波峰 y 座標 list（用第 0 個）
        selected_x_trough: 波谷 x 座標 list（用第 0 個）
        selected_y_trough: 波谷 y 座標 list（用第 0 個）

    Returns:
        (crest_position, trough_position)：兩個 (x, y) tuple，已對齊 mask 邊界
    """
    left_roi = min(selected_x_trough[0], selected_x_crest[0])
    right_roi = max(selected_x_trough[0], selected_x_crest[0]) + 1
    top_roi = min(selected_y_crest[0], selected_y_trough[0]) - 25
    bottom_roi = max(selected_y_crest[0], selected_y_trough[0]) + 25

    roi_map = diaphragm_mask[top_roi:bottom_roi, left_roi:right_roi]

    # crest：往上找
    roi_position_c = (selected_x_crest[0] - left_roi, selected_y_crest[0] - top_roi)
    boundary_crest = _find_boundary_v2(roi_map=roi_map, roi_position=roi_position_c, m=1)

    # trough：往下找
    roi_position_t = (selected_x_trough[0] - left_roi, selected_y_trough[0] - top_roi)
    boundary_trough = _find_boundary_v2(roi_map=roi_map, roi_position=roi_position_t, m=-1)

    # 還原原圖座標
    crest_position = (boundary_crest[0] + left_roi, boundary_crest[1] + top_roi)
    trough_position = (boundary_trough[0] + left_roi, boundary_trough[1] + top_roi)

    return crest_position, trough_position


def _find_boundary_v2(
    roi_map: np.ndarray,
    roi_position: Tuple[int, int],
    m: int = 1,
) -> Tuple[int, int]:
    """在 ROI 內找跟 roi_position 同 contour 的點，取最上 / 最下。

    Args:
        roi_map: ROI 內的 binary mask
        roi_position: (x, y) 起點
        m: 1 = 往上找最小 y（波峰）；-1 = 往下找最大 y（波谷）
    """
    contours, _ = cv2.findContours(
        roi_map, mode=cv2.RETR_EXTERNAL, method=cv2.CHAIN_APPROX_NONE)

    max_y = m * 10000000  # 起始值
    best_point: Optional[Tuple[int, int]] = None

    target_contour = next(
        (contour for contour in contours
         if any((x, y) == roi_position for x, y in contour[:, 0])),
        None,
    )

    n_neighbor = 0  # 只限制 x == roi_position[0]，原本是 roi_map.shape[1] // 2 已關閉
    if target_contour is not None:
        for point in target_contour:
            x, y = point[0]
            if roi_position[0] - n_neighbor <= x <= roi_position[0] + n_neighbor:
                # m=1: 找最小 y；m=-1: 找最大 y
                if y * m <= max_y * m:
                    max_y = y
                    best_point = (x, y)
    else:
        best_point = roi_position

    return best_point
