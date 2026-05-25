"""Connected components 篩選。

從 binary mask 跑 connected components，再用兩條規則分別過濾出兩組候選：

  potential_regions      : 走 curve_fit 的主候選
                           （aspect_ratio > 閾值 且 area 占比 > 閾值）

  use_segment_potentials : 給 use_segment fallback 用的候選
                           （只要 area > 閾值，較寬鬆）

兩組候選讓下游 detector 在「找不到主候選時」能退而求其次用 use_segment 路徑。

直接搬自 patch_code.py 內 detect_diaphragm 的中段：
  - 邏輯不動
  - 寫死的 area_ratio / min_use_segment_area 改為參數（由 DiaphragmDetectionConfig 注入）
  - 影像面積用 binary.shape 計算（原版用 image.shape，兩者一致；改 binary.shape 是因為這層
    本來就只看 binary，不必再傳 image）
"""
from typing import List, Tuple

import cv2
import numpy as np


# 一個 candidate = (connected component label index, y_top, y_bottom)
Candidate = Tuple[int, int, int]


def find_candidates(
    binary: np.ndarray,
    aspect_ratio_threshold: float,
    area_ratio: float,
    min_use_segment_area: int,
) -> Tuple[List[Candidate], List[Candidate], np.ndarray, int]:
    """執行 connected components 並做雙路徑過濾。

    Args:
        binary: 0/255 uint8 mask
        aspect_ratio_threshold: 寬高比門檻（橫膈膜通常水平延伸 → 比值大）
        area_ratio: 區域面積占整圖比例的門檻
        min_use_segment_area: use_segment fallback 路徑的最小面積（pixel 數）

    Returns:
        potential_regions      : 主路徑候選
        use_segment_potentials : fallback 路徑候選
        labels                 : connected components label map（給 caller 染色 / mask 反推用）
        num_labels             : labels 數量（含背景）
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=4)

    potential_regions: List[Candidate] = []
    use_segment_potentials: List[Candidate] = []

    image_area = binary.shape[0] * binary.shape[1]

    for i in range(1, num_labels):  # skip background (label 0)
        x, y, w, h, area = stats[i]
        aspect_ratio = w / h

        if aspect_ratio > aspect_ratio_threshold and area / image_area > area_ratio:
            potential_regions.append((i, y, y + h))
        if area > min_use_segment_area:
            use_segment_potentials.append((i, y, y + h))

    return potential_regions, use_segment_potentials, labels, num_labels
