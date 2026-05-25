"""Excursion 峰值算法的使用者層 config。

對應 brightness_way 與其 helpers（find_midline / excursion_rule）。
"""
from dataclasses import dataclass


@dataclass
class ExcursionConfig:
    # find_peaks 參數
    # 相鄰峰之間的最小水平距離 = ratio × image_width
    # （原寫死 0.0333 = 50/1500，對 1500 寬影像 = 50 pixel）
    peak_min_distance_ratio: float = 0.0333
    # 突起程度閾值（原寫死 10）
    peak_prominence: int = 10

    # find_midline 參數
    # 過濾相鄰交點距離（x 軸）太近者。對 1500 寬影像 = 100 pixel
    midline_min_distance_ratio: float = 100 / 1500

    # excursion_rule 參數
    # 從 diaphragm 序列前 / 後跳過的範圍（避開端點雜訊）
    # 原註解：start=1（從 6 改 1）/ end=0（從 5 改 1）
    excursion_rule_start_range: int = 1
    excursion_rule_end_range: int = 0
