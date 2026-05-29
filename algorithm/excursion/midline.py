"""中線 (midline) 與穿越線 (crossings) 計算。

從 diaphragm 時序軌跡算出 mean midline、找出穿越中線的位置與方向。
直接搬自 excursion_rule.py 的 find_midline，邏輯不動，僅加 docstring / type hints。
"""
from typing import Tuple

import numpy as np


def find_midline(
    diaphragm_y_value: np.ndarray,
    min_distance: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """算 midline + 穿越中線的位置與升降方向。

    Args:
        diaphragm_y_value: 一維時序軌跡（已是 peak-perspective）
        min_distance: 相鄰交點距離過小者過濾掉

    Returns:
        (crossings, rise_or_decline)
        crossings: 穿越中線的 x 位置 array
        rise_or_decline: 對應的方向（2=上升, -2=下降）
    """
    midline = int(np.mean(diaphragm_y_value))

    crossings_ = np.where(
        np.diff(np.where(diaphragm_y_value - midline >= 0, 1, -1)))[0]
    rise_or_decline_ = np.diff(
        np.where(diaphragm_y_value - midline >= 0, 1, -1))[crossings_]

    # 過濾相鄰交點距離過小者
    diffs = np.diff(crossings_)
    valid_mask = np.insert(diffs > min_distance, 0, True)

    crossings = crossings_[valid_mask]
    rise_or_decline = rise_or_decline_[valid_mask]

    return crossings, rise_or_decline
