"""ROI band 的 y 範圍計算。

對 detect() 找出的 (top, bottom) 上下擴張 reserve_y 範圍，
產出給下游強化 / 搜索演算法用的 ROI band。

直接搬自 patch_code.py 的 target_Y_range，差別：
  - reserve_y 以實際 image_height 計算（修原 y_dim=955 寫死的隱性 bug）
  - 移除 sniff_phase（dead param，原始 if-else 分支已被註解掉）
  - 移除 loop / show_range（debug / viz 留給 logging / Step 5 viz）
  - 介面只吃 image_height，不再依賴 image_original 物件
"""
from typing import Tuple


def compute_target_y_range(
    target_y_range: Tuple[int, int],
    image_height: int,
    reserve_ratio: float = 50 / 955,
) -> Tuple[int, int]:
    """擴張 (top, bottom) 一段 reserve_y 餘裕。

    Args:
        target_y_range: detect() 找出的 (y_top, y_bottom)
        image_height: 影像高度（pixel）。用來計算 reserve_y 與 clamp y_max
        reserve_ratio: 擴張比例，預設 ≈ 0.052（原 50/955）

    Returns:
        (y_min, y_max) ROI band，已 clamp 到 [0, image_height]
    """
    top, bottom = target_y_range
    reserve_y = int(image_height * reserve_ratio)
    y_min = max(0, top - reserve_y)
    y_max = min(image_height, bottom + reserve_y)
    return y_min, y_max
