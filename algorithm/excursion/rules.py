"""Excursion 波形規則：依 crossings 數量決定怎麼選 peak / trough。

直接搬自 excursion_rule.py 的 excursion_rule，邏輯不動。改：
  - start_range / end_range 由參數注入（原寫死 1 / 0）
  - 加 docstring / type hints
  - 保留原 print 與 if-not-elif 結構（與原版行為一致）

呼吸週期判讀（依 crossings 的 rise_or_decline 標籤）：
  -2 = 下降（吐氣）
   2 = 上升（吸氣）
  trend = diff(rise_or_decline)
   4 = 下降→上升（碰底 → 找波谷）
  -4 = 上升→下降（碰頂 → 找波峰）
"""
from typing import List, Tuple

import numpy as np


def excursion_rule(
    crossings: np.ndarray,
    rise_or_decline: np.ndarray,
    diaphragm_y_value: np.ndarray,
    start_range: int = 1,
    end_range: int = 0,
) -> Tuple[List[int], List[int]]:
    """根據 crossings 數量套用不同規則選 peak / trough。

    Args:
        crossings: 穿越中線的 x 位置
        rise_or_decline: 對應方向（2=上升、-2=下降）
        diaphragm_y_value: 一維時序軌跡（peak-perspective）
        start_range: 從序列前段跳過的範圍（避端點雜訊）
        end_range: 從序列後段跳過的範圍

    Returns:
        (selected_troughs, selected_crest) — 兩個 list of x indices
    """
    selected_crest: List[int] = []
    selected_troughs: List[int] = []
    in_range = np.arange(start_range, len(diaphragm_y_value) - end_range)

    # Case 1: crossings >= 3
    if len(crossings) == 3 or len(crossings) >= 4:
        trend_changes = np.diff(rise_or_decline)
        for i in range(2):  # 只取前 2 trend changes（原始邏輯，未說明）
            trend = trend_changes[i]
            start, end = crossings[i], crossings[i + 1]
            center = (start + end) / 2

            if trend == 4:  # 下降→上升 → 找波谷
                valley_in_range = [v for v in in_range if start <= v <= end]
                if valley_in_range:
                    selected_troughs.append(
                        min(valley_in_range,
                            key=lambda v: (diaphragm_y_value[v], abs(center - v))) - start_range)
            elif trend == -4:  # 上升→下降 → 找波峰
                peak_in_range = [p for p in in_range if start <= p <= end]
                if peak_in_range:
                    selected_crest.append(
                        max(peak_in_range,
                            key=lambda p: (diaphragm_y_value[p], -abs(center - p))))

    # Case 2: crossings == 1
    if len(crossings) == 1:
        # 只有一個交點：依方向往對側找最高/最低點
        trend_changes = rise_or_decline[0]
        center = crossings[0]
        factor = trend_changes // abs(trend_changes)   # +1 上升 / -1 下降

        peak_in_range = [p for p in in_range if factor * center <= factor * p]
        valley_in_range = [v for v in in_range if factor * v <= factor * center]

        if peak_in_range:
            selected_crest.append(
                max(peak_in_range,
                    key=lambda p: (diaphragm_y_value[p], -abs(center - p))))
        if valley_in_range:
            selected_troughs.append(
                min(valley_in_range,
                    key=lambda v: (diaphragm_y_value[v], abs(center - v))) - start_range)

    # Case 3: crossings == 2
    if len(crossings) == 2:
        start, end = crossings[0], crossings[1]
        center = (start + end) / 2
        if rise_or_decline[0] == -2:
            # -2 → 2 吐氣再吸氣 → crossings 裡找波谷，外找波峰
            print("[INFO] -2  2 吐氣再吸氣 crossing裡面找波谷，外找波峰")
            valley_in_range = [v for v in in_range if start <= v <= end]
            peak_in_range = [p for p in in_range if p <= start or p >= end]
            peak_in_range = [p for p in in_range if end <= p <= end + (end - start)]  # 測試中
        else:
            # 2 → -2 吸氣再吐氣 → crossings 裡找波峰，外找波谷
            print("[INFO] 2 -2 吸氣再吐氣 crossing裡面找波峰，外找波谷")
            valley_in_range = [v for v in in_range if end <= v <= end + (end - start)]  # 測試中
            peak_in_range = [p for p in in_range if start <= p <= end]

        if valley_in_range:
            selected_troughs.append(
                min(valley_in_range,
                    key=lambda v: (diaphragm_y_value[v], abs(center - v))) - start_range)
        if peak_in_range:
            selected_crest.append(
                max(peak_in_range,
                    key=lambda p: (diaphragm_y_value[p], -abs(center - p))))

    return selected_troughs, selected_crest
